# Marcel

Marcel is an autonomous, client-configurable agent framework for orchestrating capable AI work.
It provides memory, schedules, messaging gateways, skills, plugins, and concurrent delegation
through a business-oriented orchestration layer.

## Current foundation

- OpenAI-compatible Marcel Router contract for chat, model discovery, images, video, and jobs.
- Configurable orchestrator plus an unbounded registry of named workers.
- Worker-specific provider, model, tools/toolsets, concurrency, iteration, timeout, fallback, and
  budget metadata.
- Deterministic `cheapest_capable` routing configuration.
- BYOK support for customer-owned OpenAI-compatible endpoints.
- Google Workspace OAuth metadata and generic IMAP/SMTP account profiles.
- Secret references only: API keys, passwords, refresh tokens, and client secrets are not written
  into YAML.
- Durable memory-maintenance schedule, enabled every six hours by default.
- Quiet defaults: tool progress off and STT transcript echo disabled.

## Router contract

The router contract is documented in:

- [docs/marcel-router.md](docs/marcel-router.md)
- [docs/marcel-router-openapi.yaml](docs/marcel-router-openapi.yaml)

MVP endpoints:

```text
GET  /health
GET  /v1/models
POST /v1/chat/completions
```

Planned media endpoints:

```text
POST /v1/images/generations
POST /v1/videos/generations
GET  /v1/jobs/{job_id}
```

Marcel normally chooses a concrete namespaced model such as `provider/model` before calling the
router. The router does not silently replace the selected model.

## Development setup

```bash
cd marcel-agent
uv sync
uv run marcel setup marcel
uv run marcel
```

## Configuration shape

The Marcel wizard writes to native runtime sections:

- `marcel` — brand, router mode, orchestrator, and routing policy.
- `providers` and `model` — active OpenAI-compatible endpoint and orchestrator model.
- `delegation.workers` — named worker registry.
- `accounts.profiles` — Google Workspace or IMAP/SMTP metadata.
- `memory.maintenance` — six-hour maintenance policy and cron job name.

Example:

```yaml
marcel:
  agent_name: Marcel
  router:
    mode: byok
    base_url: https://models.customer.example/v1
    key_env: CUSTOMER_MODEL_API_KEY
  orchestrator:
    provider: marcel-byok
    model: openai/gpt-5
  routing:
    strategy: cheapest_capable

delegation:
  workers:
    research:
      activity: search
      provider: marcel-byok
      model: google/gemini-flash
      toolsets: [web, documents]
      max_concurrency: 4
      fallback_models: [openai/gpt-5-mini]
      budget:
        max_requests: 100
```

Actual secret values belong in environment variables or the deployment secret manager. YAML stores
only references such as `${CUSTOMER_MODEL_API_KEY}`.

## Worker dispatch

Models can dispatch a configured worker through `delegate_task(worker="research", ...)`. Resolution
precedence is:

```text
delegation defaults < named worker < trusted call overrides
```

Worker registries have no fixed size limit. Runtime execution remains bounded by configured
concurrency, provider quotas, available resources, and budgets.

## Test the router

Run the complete compatibility suite offline:

```bash
uv run marcel-router-validate \
  --fixture tests/fixtures/marcel_router_validator.json
```

When a real router is available:

```bash
export MARCEL_ROUTER_API_KEY="..."
uv run marcel-router-validate --base-url https://router.example
```

For CI or machine-readable diagnostics, add `--json`. The validator checks health, catalog metadata,
normal chat, SSE streaming, tool calls, structured JSON, authentication errors, and invalid-model
errors. The API key is read from the environment and is never written to a fixture or report.

Deterministic routing fixtures are available in `tests/fixtures/marcel_routing_config.json` and
`tests/fixtures/marcel_router_catalog.json`.

## Defaults introduced by Marcel

```yaml
display:
  tool_progress: "off"

stt:
  echo_transcripts: false

memory:
  maintenance:
    enabled: true
    interval_hours: 6
    timezone: UTC
    run_only_when_changed: true
```

The setup wizard creates or updates a persistent cron job named
`marcel-memory-maintenance`. It can also disable the job.

## Naming and mascot

Marcel's visual identity uses an original monkey mascot. Do not copy costumes, props, poses, or
other protected visual elements associated with the character Marcel from *Friends*.

## License

Marcel retains the upstream MIT license and attribution. See [LICENSE](LICENSE) and
[UPSTREAM.md](UPSTREAM.md).