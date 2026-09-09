"""Offline-capable compatibility checks for the Marcel Router v1 contract.

Run ``marcel-router-validate --fixture router.json`` for a deterministic
fixture run, or set the named environment variable and pass ``--base-url`` for
an actual router.  Fixture files are JSON and contain an ordered ``responses``
list; each item has ``method``, ``path``, ``status``, optional ``headers``, and
``body`` (an object or string).  They deliberately have no credential field.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: str


class Transport(Protocol):
    def request(self, method: str, path: str, headers: dict[str, str],
                body: dict[str, Any] | None = None) -> Response: ...


class UrlTransport:
    """Small stdlib transport, intentionally avoiding an SDK-specific client."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, headers: dict[str, str],
                body: dict[str, Any] | None = None) -> Response:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base_url + path, data=data, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as result:
                return Response(result.status, {k.lower(): v for k, v in result.headers.items()},
                                result.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return Response(error.code, {k.lower(): v for k, v in error.headers.items()},
                            error.read().decode("utf-8"))


class FixtureTransport:
    """Ordered fake transport for CLI fixtures and unit tests."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[str, str, dict[str, str], dict[str, Any] | None]] = []

    def request(self, method: str, path: str, headers: dict[str, str],
                body: dict[str, Any] | None = None) -> Response:
        if not self.responses:
            raise AssertionError(f"fixture has no response for {method} {path}")
        item = self.responses.pop(0)
        if item.get("method", method).upper() != method.upper() or item.get("path", path) != path:
            raise AssertionError(f"fixture expected {item.get('method')} {item.get('path')}, got {method} {path}")
        self.requests.append((method, path, headers, body))
        content = item.get("body", "")
        return Response(int(item.get("status", 200)),
                        {str(k).lower(): str(v) for k, v in item.get("headers", {}).items()},
                        content if isinstance(content, str) else json.dumps(content))


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append(Check(name, status, detail))

    @property
    def ok(self) -> bool:
        return not any(check.status == "fail" for check in self.checks)

    def as_dict(self) -> dict[str, Any]:
        counts = {state: sum(c.status == state for c in self.checks)
                  for state in ("pass", "fail", "skip")}
        return {"ok": self.ok, "summary": counts,
                "checks": [check.__dict__ for check in self.checks]}


class RouterValidator:
    """Validate the contract portions clients rely on, not implementation details."""

    def __init__(self, transport: Transport, token: str | None) -> None:
        self.transport, self.token, self.report = transport, token, Report()
        self.models: list[dict[str, Any]] = []

    def _headers(self, authenticated: bool = True) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if authenticated and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _json(self, response: Response) -> dict[str, Any]:
        try:
            value = json.loads(response.body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError("JSON response must be an object")
        return value

    @staticmethod
    def _error(value: dict[str, Any]) -> bool:
        error = value.get("error")
        return isinstance(error, dict) and isinstance(error.get("message"), str) and isinstance(error.get("type"), str)

    def _check(self, name: str, action) -> Any:
        try:
            result = action()
            self.report.add(name, "pass")
            return result
        except Exception as exc:  # A report should include every independently runnable check.
            self.report.add(name, "fail", str(exc))
            return None

    def _model(self, capability: str = "chat") -> dict[str, Any] | None:
        for model in self.models:
            caps = model.get("marcel", {}).get("capabilities", {})
            if caps.get(capability) is True:
                return model
        return None

    def _completion(self, model: dict[str, Any], **extra: Any) -> Response:
        payload = {"model": model["id"], "messages": [{"role": "user", "content": "compatibility probe"}]}
        payload.update(extra)
        return self.transport.request("POST", "/v1/chat/completions", self._headers(), payload)

    def run(self) -> Report:
        def health() -> None:
            response = self.transport.request("GET", "/health", self._headers(False))
            value = self._json(response)
            if response.status != 200 or value.get("status") != "ok" or not isinstance(value.get("version"), str):
                raise ValueError("expected 200 health object with status=ok and version")
        self._check("health", health)

        def catalog() -> list[dict[str, Any]]:
            response = self.transport.request("GET", "/v1/models", self._headers())
            value = self._json(response)
            data = value.get("data")
            if response.status != 200 or value.get("object") != "list" or not isinstance(data, list) or not data:
                raise ValueError("expected non-empty OpenAI model list")
            for model in data:
                if not isinstance(model, dict) or not isinstance(model.get("id"), str) or "/" not in model["id"]:
                    raise ValueError("model IDs must be namespaced provider/model")
                marcel = model.get("marcel")
                if (not isinstance(marcel, dict)
                        or not isinstance(marcel.get("provider"), str)
                        or not isinstance(marcel.get("capabilities"), dict)
                        or not isinstance(marcel.get("modalities"), list)):
                    raise ValueError("models require marcel provider, modalities, and capabilities metadata")
            return data
        self.models = self._check("model catalog", catalog) or []

        chat_model = self._model()
        if not chat_model:
            self.report.add("non-stream chat", "skip", "no catalog model advertises chat")
            self.report.add("SSE streaming", "skip", "no catalog model advertises chat")
            self.report.add("tool calling", "skip", "no catalog model advertises chat")
            self.report.add("structured JSON output", "skip", "no catalog model advertises chat")
        else:
            def nonstream() -> None:
                response = self._completion(chat_model, stream=False)
                value = self._json(response)
                usage = value.get("usage", {})
                if response.status != 200 or value.get("object") != "chat.completion" or not isinstance(value.get("choices"), list):
                    raise ValueError("expected chat.completion with choices")
                if not all(isinstance(usage.get(key), int) for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
                    raise ValueError("completion lacks integer token usage")
            self._check("non-stream chat", nonstream)

            stream_model = self._model("streaming")
            if stream_model:
                def streaming() -> None:
                    response = self._completion(stream_model, stream=True, stream_options={"include_usage": True})
                    events = [line[6:] for line in response.body.splitlines() if line.startswith("data: ")]
                    if response.status != 200 or not events or events[-1] != "[DONE]":
                        raise ValueError("SSE must end with data: [DONE]")
                    content_type = response.headers.get("content-type", "")
                    if content_type and "text/event-stream" not in content_type.lower():
                        raise ValueError("stream response has non-SSE content type")
                    chunks = [json.loads(event) for event in events[:-1]]
                    if not chunks or not all(item.get("object") == "chat.completion.chunk" for item in chunks):
                        raise ValueError("SSE data events must be completion chunks")
                self._check("SSE streaming", streaming)
            else:
                self.report.add("SSE streaming", "skip", "no catalog model advertises streaming")

            tool_model = self._model("tools")
            if tool_model:
                def tools() -> None:
                    tool = {"type": "function", "function": {"name": "echo", "parameters": {"type": "object"}}}
                    initial = self._completion(tool_model, tools=[tool], tool_choice="required")
                    first = self._json(initial)
                    calls = first.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
                    if initial.status != 200 or not calls or not isinstance(calls[0].get("id"), str):
                        raise ValueError("expected function tool call")
                    json.loads(calls[0].get("function", {}).get("arguments", ""))
                    followup = self._completion(tool_model, messages=[
                        {"role": "user", "content": "compatibility probe"},
                        {"role": "assistant", "tool_calls": calls},
                        {"role": "tool", "tool_call_id": calls[0]["id"], "content": "{\"ok\":true}"},
                    ])
                    if followup.status != 200 or self._json(followup).get("object") != "chat.completion":
                        raise ValueError("tool result follow-up did not complete")
                self._check("tool calling", tools)
            else:
                self.report.add("tool calling", "skip", "no catalog model advertises tools")

            json_model = self._model("json_schema")
            if json_model:
                def structured() -> None:
                    response = self._completion(json_model, response_format={"type": "json_object"})
                    value = self._json(response)
                    content = value.get("choices", [{}])[0].get("message", {}).get("content")
                    if response.status != 200 or not isinstance(content, str):
                        raise ValueError("expected assistant JSON content")
                    json.loads(content)
                self._check("structured JSON output", structured)
            else:
                self.report.add("structured JSON output", "skip", "no catalog model advertises json_schema")

        def auth_error() -> None:
            response = self.transport.request("GET", "/v1/models", self._headers(False))
            if response.status != 401 or not self._error(self._json(response)):
                raise ValueError("expected 401 OpenAI error envelope without bearer token")
        self._check("authentication error envelope", auth_error)

        if chat_model:
            def request_error() -> None:
                response = self.transport.request("POST", "/v1/chat/completions", self._headers(), {
                    "model": "invalid/does-not-exist", "messages": [{"role": "user", "content": "probe"}],
                })
                if response.status < 400 or not self._error(self._json(response)):
                    raise ValueError("expected typed error envelope for invalid model")
            self._check("request error envelope", request_error)
        return self.report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Marcel Router OpenAI compatibility.")
    parser.add_argument("--base-url", help="Router origin, e.g. https://router.example")
    parser.add_argument("--fixture", help="Offline ordered JSON response fixture")
    parser.add_argument("--auth-env", default="MARCEL_ROUTER_API_KEY",
                        help="environment variable containing the bearer token (never a token value)")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--json", action="store_true", dest="json_output", help="emit JSON report")
    args = parser.parse_args(argv)
    if bool(args.base_url) == bool(args.fixture):
        parser.error("provide exactly one of --base-url or --fixture")
    if args.fixture:
        try:
            fixture = json.loads(open(args.fixture, encoding="utf-8").read())
            transport: Transport = FixtureTransport(fixture["responses"])
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            parser.error(f"invalid fixture: {exc}")
        token = os.environ.get(args.auth_env, "fixture-token")
    else:
        token = os.environ.get(args.auth_env)
        if not token:
            parser.error(f"{args.auth_env} is not set (pass its name with --auth-env)")
        transport = UrlTransport(args.base_url, args.timeout)
    report = RouterValidator(transport, token).run()
    if args.json_output:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        for check in report.checks:
            suffix = f": {check.detail}" if check.detail else ""
            print(f"{check.status.upper():4} {check.name}{suffix}")
        print(f"{'PASS' if report.ok else 'FAIL'} — {len(report.checks)} checks")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())