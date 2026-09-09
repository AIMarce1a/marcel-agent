"""Pure, deterministic selection of a Marcel worker and router model.

This module is deliberately not a router client: it reads only caller-supplied
configuration and a ``GET /v1/models``-style catalogue and makes no network,
credential, or LLM calls.  The returned namespaced model id is therefore safe
to pass to either ``delegate_task`` or a Marcel Router client.

The small public API is :func:`route_request`, which returns a
:class:`RouteDecision`, and :func:`resolve_route`, which raises
:class:`RoutingError` on the same failure.  Request keys are intentionally
plain dictionaries so adapters do not need to import Marcel runtime classes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from tools.delegate_worker_registry import WorkerConfigError, parse_workers


@dataclass(frozen=True)
class RouteDecision:
    """A serialisable routing decision (or an explainable non-selection)."""

    worker_id: Optional[str] = None
    model_id: Optional[str] = None
    provider: Optional[str] = None
    reason: Optional[str] = None
    candidates_considered: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.reason is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "worker_id": self.worker_id, "model_id": self.model_id,
            "provider": self.provider, "reason": self.reason,
            "candidates_considered": list(self.candidates_considered),
        }


class RoutingError(ValueError):
    """Raised by :func:`resolve_route` when no safe route can be selected."""


def _strings(value: Any) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(str(item).strip().lower() for item in value if str(item).strip())


def _capabilities(value: Any) -> frozenset[str]:
    """Accept both OpenAPI boolean maps and compact local capability lists."""
    if isinstance(value, Mapping):
        return frozenset(str(key).strip().lower() for key, enabled in value.items() if enabled is True)
    return _strings(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _models(catalog: Any) -> list[dict[str, Any]]:
    """Normalize router's OpenAI ``data`` shape and useful local variants."""
    raw = catalog.get("data") if isinstance(catalog, Mapping) else catalog
    if isinstance(catalog, Mapping) and raw is None:
        raw = catalog.get("models")
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, Mapping):
            continue
        model_id = _text(row.get("id"))
        # Router IDs are deliberately namespaced; accepting aliases would make
        # provider dispatch ambiguous.
        if "/" not in model_id or model_id.startswith("/") or model_id.endswith("/"):
            continue
        meta = row.get("marcel")
        meta = meta if isinstance(meta, Mapping) else {}
        result.append({"id": model_id, "meta": meta})
    return result


def _number(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _limit(meta: Mapping[str, Any], *names: str) -> Optional[float]:
    for name in names:
        found = _number(meta.get(name))
        if found is not None:
            return found
    limits = meta.get("limits")
    if isinstance(limits, Mapping):
        for name in names:
            found = _number(limits.get(name))
            if found is not None:
                return found
    return None


def _cost(model: Mapping[str, Any], request: Mapping[str, Any]) -> float:
    """Estimated request cost; unknown pricing sorts after known pricing."""
    pricing = model["meta"].get("pricing")
    if not isinstance(pricing, Mapping):
        return float("inf")
    # Router catalogues commonly use either per-token or per-million-token
    # price labels.  Both are supported without guessing a currency.
    input_price = _number(pricing.get(
        "input_per_million", pricing.get("input_cost_per_million", pricing.get("input"))))
    output_price = _number(pricing.get(
        "output_per_million", pricing.get("output_cost_per_million", pricing.get("output"))))
    if input_price is None and output_price is None:
        return float("inf")
    # With no requested sizes, compare a stable one-million-token unit price
    # instead of making every known model cost zero and accidentally ranking by
    # name alone.
    input_tokens = _number(request.get("context_tokens", request.get("input_tokens")))
    output_tokens = _number(request.get("output_tokens", request.get("max_output_tokens")))
    input_tokens = 1_000_000 if input_tokens is None else input_tokens
    output_tokens = 1_000_000 if output_tokens is None else output_tokens
    # Explicit per-token values can opt in with unit="token".
    divisor = 1 if pricing.get("unit") == "token" else 1_000_000
    return ((input_price or 0) * input_tokens + (output_price or 0) * output_tokens) / divisor


def _model_failure(model: Mapping[str, Any], request: Mapping[str, Any], require_tools: bool) -> Optional[str]:
    meta = model["meta"]
    required_caps = _strings(request.get("capabilities"))
    required_modalities = _strings(request.get("modalities"))
    if not required_modalities:
        activity = _text(request.get("activity") or request.get("orchestrator_activity")).lower()
        required_modalities = frozenset({"image" if activity == "image" else "video" if activity == "video" else "text"})
    if require_tools and _strings(request.get("toolsets")):
        required_caps = required_caps | frozenset({"tools"})
    capabilities = _capabilities(meta.get("capabilities"))
    modalities = _strings(meta.get("modalities"))
    # tool_calling is a conventional router spelling; normalize it to tools.
    if "tool_calling" in capabilities:
        capabilities = capabilities | frozenset({"tools"})
    missing = required_caps - capabilities
    if missing:
        return "missing capability " + ", ".join(sorted(missing))
    missing = required_modalities - modalities
    if missing:
        return "missing modality " + ", ".join(sorted(missing))
    context_need = _number(request.get("context_tokens", request.get("input_tokens")))
    context_limit = _limit(meta, "context_window", "context_length", "max_context_tokens")
    if context_need is not None and (context_limit is None or context_limit < context_need):
        return f"insufficient context ({int(context_limit or 0)} < {int(context_need)})"
    output_need = _number(request.get("output_tokens", request.get("max_output_tokens")))
    output_limit = _limit(meta, "max_output_tokens", "output_tokens")
    if output_need is not None and (output_limit is None or output_limit < output_need):
        return f"insufficient output limit ({int(output_limit or 0)} < {int(output_need)})"
    return None


def _worker_failure(worker: Mapping[str, Any], request: Mapping[str, Any]) -> Optional[str]:
    enabled = _strings(request.get("enabled_toolsets"))
    required = _strings(request.get("toolsets"))
    worker_toolsets = _strings(worker.get("toolsets"))
    # An omitted enabled_toolsets means the caller did not impose a runtime
    # restriction.  When supplied, both requested and worker toolsets must fit.
    if enabled and not (required | worker_toolsets).issubset(enabled):
        missing = (required | worker_toolsets) - enabled
        return "requires disabled toolset " + ", ".join(sorted(missing))
    return None


def _select_worker(workers: Mapping[str, Mapping[str, Any]], request: Mapping[str, Any]) -> tuple[Optional[dict[str, Any]], str]:
    explicit = _text(request.get("worker"))
    if explicit:
        worker = workers.get(explicit)
        if worker is None:
            return None, f"unknown worker '{explicit}'"
        failure = _worker_failure(worker, request)
        return (dict(worker), failure or "") if not failure else (None, f"worker '{explicit}' {failure}")

    activity = _text(request.get("activity") or request.get("orchestrator_activity")).lower() or "general"
    exact = [dict(w) for w in workers.values() if _text(w.get("activity")).lower() == activity]
    general = [dict(w) for w in workers.values() if _text(w.get("activity")).lower() == "general"]
    possible = exact or general
    eligible = [w for w in possible if not _worker_failure(w, request)]
    if not eligible:
        failures = [
            f"{w['id']} {_worker_failure(w, request)}"
            for w in possible
            if _worker_failure(w, request)
        ]
        detail = "; ".join(failures)
        suffix = f": {detail}" if detail else ""
        return None, f"no enabled worker for activity '{activity}'{suffix}"
    # Names make selection stable even when YAML mapping order changes.
    return sorted(eligible, key=lambda item: item["id"])[0], ""


def route_request(config: Mapping[str, Any], catalog: Any, request: Optional[Mapping[str, Any]] = None) -> RouteDecision:
    """Choose a worker then a concrete router model without side effects.

    ``config`` reads ``marcel.routing`` and ``delegation.workers``.  ``request``
    accepts ``activity``, ``worker``, ``model``, ``toolsets``,
    ``enabled_toolsets``, ``capabilities``, ``modalities``, ``context_tokens``,
    and ``output_tokens``. Explicit worker/model values are pins, never silent
    fallbacks.  A worker's primary ``model`` is preferred; its
    ``fallback_models`` are tried only if that primary cannot satisfy the
    request.  Unpinned candidates use ``cheapest_capable`` and id tie-breaking.
    """
    request = request or {}
    if not isinstance(config, Mapping) or not isinstance(request, Mapping):
        return RouteDecision(reason="config and request must be mappings")
    marcel = config.get("marcel")
    routing = marcel.get("routing") if isinstance(marcel, Mapping) and isinstance(marcel.get("routing"), Mapping) else {}
    strategy = _text(routing.get("strategy") or "cheapest_capable")
    if strategy != "cheapest_capable":
        return RouteDecision(reason=f"unsupported Marcel routing strategy '{strategy}'")
    try:
        workers = parse_workers((config.get("delegation") or {}).get("workers")
                                if isinstance(config.get("delegation"), Mapping) else None)
    except WorkerConfigError as exc:
        return RouteDecision(reason=f"invalid delegation workers: {exc}")
    worker, failure = _select_worker(workers, request)
    if worker is None:
        return RouteDecision(reason=failure)
    models = _models(catalog)
    if not models:
        return RouteDecision(worker_id=worker["id"], reason="catalog has no namespaced router models")

    explicit_model = _text(request.get("model"))
    allow_override = routing.get("allow_model_override", True) is not False
    if explicit_model and not allow_override:
        return RouteDecision(worker_id=worker["id"], reason="model override is disabled by marcel.routing")
    model_by_id = {model["id"]: model for model in models}
    require_tools = routing.get("require_tool_support", True) is not False
    if explicit_model:
        candidates = [model_by_id[explicit_model]] if explicit_model in model_by_id else []
        if not candidates:
            return RouteDecision(worker_id=worker["id"], reason=f"explicit model '{explicit_model}' is not in catalog")
    else:
        pinned = [_text(worker.get("model"))] + [_text(x) for x in worker.get("fallback_models", [])]
        pinned = [x for x in pinned if x]
        candidates = [model_by_id[x] for x in pinned if x in model_by_id] if pinned else models
        if pinned and not candidates:
            return RouteDecision(worker_id=worker["id"], reason="worker model and fallback_models are not in catalog",
                                 candidates_considered=tuple(pinned))
    considered = tuple(model["id"] for model in candidates)
    eligible = [(model, _model_failure(model, request, require_tools)) for model in candidates]
    eligible_models = [model for model, why in eligible if why is None]
    if not eligible_models:
        details = "; ".join(f"{model['id']}: {why}" for model, why in eligible)
        return RouteDecision(worker_id=worker["id"], reason=f"no capable model ({details})",
                             candidates_considered=considered)
    # Worker fallback order expresses availability preference.  For a worker
    # with no pin, rank the catalogue globally by estimated cost then id.
    if not explicit_model and _text(worker.get("model")):
        selected = eligible_models[0]
    else:
        selected = min(eligible_models, key=lambda model: (_cost(model, request), model["id"]))
    return RouteDecision(worker_id=worker["id"], model_id=selected["id"],
                         provider=selected["id"].split("/", 1)[0],
                         candidates_considered=considered)


def resolve_route(config: Mapping[str, Any], catalog: Any, request: Optional[Mapping[str, Any]] = None) -> RouteDecision:
    """Return a successful decision or raise a credential-free ``RoutingError``."""
    decision = route_request(config, catalog, request)
    if not decision.ok:
        raise RoutingError(decision.reason or "no Marcel route")
    return decision