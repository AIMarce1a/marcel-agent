"""Deterministic contract-validator tests; no socket or external SDK required."""

import unittest

from marcel_cli.marcel_router_validator import FixtureTransport, RouterValidator


def _completion(content="hello"):
    return {"id": "c", "object": "chat.completion", "created": 1, "model": "demo/chat",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


class RouterValidatorTests(unittest.TestCase):
    def test_complete_fixture_passes_and_uses_no_network(self):
        model = {"id": "demo/chat", "object": "model", "created": 1, "owned_by": "demo",
                 "marcel": {"provider": "demo", "modalities": ["text"],
                            "capabilities": {"chat": True, "streaming": True, "tools": True, "json_schema": True}}}
        tool_call = {"id": "call_1", "type": "function", "function": {"name": "echo", "arguments": "{}"}}
        responses = [
            {"method": "GET", "path": "/health", "body": {"status": "ok", "version": "1.0.0"}},
            {"method": "GET", "path": "/v1/models", "body": {"object": "list", "data": [model]}},
            {"method": "POST", "path": "/v1/chat/completions", "body": _completion()},
            {"method": "POST", "path": "/v1/chat/completions", "body": 'data: {"object":"chat.completion.chunk","choices":[]}\n\ndata: [DONE]\n\n'},
            {"method": "POST", "path": "/v1/chat/completions", "body": _completion()},
            {"method": "POST", "path": "/v1/chat/completions", "body": _completion()},
            {"method": "POST", "path": "/v1/chat/completions", "body": _completion('{"ok": true}')},
            {"method": "GET", "path": "/v1/models", "status": 401, "body": {"error": {"message": "missing", "type": "authentication_error"}}},
            {"method": "POST", "path": "/v1/chat/completions", "status": 404, "body": {"error": {"message": "unknown", "type": "invalid_request_error"}}},
        ]
        # Substitute the first tool response with an actual tool-call completion.
        responses[4]["body"] = _completion()
        responses[4]["body"]["choices"][0]["message"] = {"role": "assistant", "tool_calls": [tool_call]}
        transport = FixtureTransport(responses)
        report = RouterValidator(transport, "test-token").run()
        self.assertTrue(report.ok)
        self.assertFalse(transport.responses)
        self.assertNotIn("Authorization", transport.requests[-2][2])

    def test_invalid_sse_is_reported_without_raising(self):
        transport = FixtureTransport([
            {"body": {"status": "ok", "version": "1"}},
            {"body": {"object": "list", "data": [{"id": "x/y", "marcel": {"provider": "x", "modalities": ["text"], "capabilities": {"chat": True, "streaming": True}}}]}},
            {"body": _completion()},
            {"body": "data: nope\n\n"},
            {"status": 401, "body": {"error": {"message": "no", "type": "authentication_error"}}},
            {"status": 400, "body": {"error": {"message": "bad", "type": "invalid_request_error"}}},
        ])
        report = RouterValidator(transport, "token").run()
        self.assertFalse(report.ok)
        self.assertEqual(next(c.status for c in report.checks if c.name == "SSE streaming"), "fail")