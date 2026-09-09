# Marcel Router MVP contract

## Scope and compatibility

Marcel Router exposes an OpenAI-compatible API at `/v1`. The normative wire
contract is [`marcel-router-openapi.yaml`](marcel-router-openapi.yaml), OpenAPI
3.1. This document defines the MVP behavior that accompanies that schema. The
router is a contract and client-routing layer; it does not require changes to
the imported Marcel runtime.

MVP endpoints are `GET /health`, `GET /v1/models`,
`POST /v1/chat/completions`, `POST /v1/images/generations`,
`POST /v1/videos/generations`, and `GET /v1/jobs/{job_id}`. Health is
unauthenticated. Every `/v1` operation requires the authorization described
below. Unknown models and jobs return the standard OpenAI-shaped error object.

## Authentication and BYOK

Clients send `Authorization: Bearer <Marcel API key>` to the router. Missing or
invalid credentials return `401` with `{ "error": { "message", "type", ... } }`.
Provider credentials are not sent as a replacement for the Marcel bearer token.

Bring-your-own-key (BYOK) is compatible with this contract: a Marcel
installation may resolve provider credentials from its configured secure
credential store for the authenticated principal. It must not expose those
credentials in model listings, responses, job records, error messages, or
client-visible routing metadata. A provider that is unavailable to the
principal, including because its BYOK credential is absent, is omitted from
`/v1/models`; an explicit request for it fails with a typed error rather than
silently falling back to another provider.

## Models and deterministic routing

Every model identifier is namespaced: `provider/model`, for example
`openai/gpt-4o-mini`. The slash is required. Unnamespaced aliases are not part
of the MVP. `GET /v1/models` returns only models usable by the caller and adds
a `marcel` object containing the provider, supported modalities/capabilities,
and, where known, context/output limits and pricing metadata.

Routing is deterministic and performed by the client: it selects one listed
namespaced ID based only on locally available inputs (requested capability,
policy, cost/latency preferences, and the stable model metadata), then sends
that exact ID. The router dispatches to that namespace's provider and does not
perform hidden retries, cross-provider fallback, or model substitution. This
makes routing auditable and keeps the same client inputs and model catalogue
decision reproducible. Clients should record the selected ID and catalogue
version/snapshot when reproducibility matters.

## Chat, tools, structured output, and streaming

`/v1/chat/completions` accepts OpenAI message arrays, sampling options, OpenAI
function tools, `tool_choice`, and `response_format` (`text`, `json_object`, or
`json_schema`). Tool arguments are JSON encoded in
`message.tool_calls[].function.arguments`; a client executes them and submits a
subsequent `tool` message with the matching `tool_call_id`. Capability support
is advertised in `model.marcel.capabilities`; asking an unsupported model for a
feature is a `400`, not a degraded response.

With `stream: false` the endpoint returns one `chat.completion` with `usage`
(`prompt_tokens`, `completion_tokens`, and `total_tokens`). With `stream: true`
it returns SSE. Each event is `data: <JSON ChatCompletionChunk>` and completion
is `data: [DONE]`; tool-call deltas can be split and are joined by `index`.
When `stream_options.include_usage` is true, the terminal chunk includes usage.

Image generation may complete immediately or return a `202` job. Video
generation returns a `202` job. Poll `GET /v1/jobs/{job_id}` until its terminal
status is `succeeded`, `failed`, or `cancelled`. Failed jobs include the same
error shape used by HTTP failures.

## Errors and versioning

All non-success API errors use
`{ "error": { "message": "...", "type": "...", "param": null, "code": null } }`.
`400`, `401`, `404`, `429`, and `500` have their conventional meanings; callers
must not infer a fallback provider from any error.

The API version is the `/v1` path major version. Additive fields, optional
metadata, models, and capabilities may be introduced within v1; clients must
ignore fields they do not understand. Removing or changing a required field,
altering endpoint semantics, or changing deterministic-routing rules requires a
new path major version. `/health.version` reports the deployed contract version.