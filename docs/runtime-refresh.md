# Runtime configuration, dependency caching, and refresh behavior

This repository intentionally uses process-local settings and dependency caches.
The supported refresh mechanism is a process or container restart. Do not rely on
editing environment variables in a running process to change behavior.

## Backend API (`country_compare`)

The backend API reads API settings during `create_app()` startup. Forecast LLM
settings are read from environment by the LLM forecast integration when needed,
but backend-to-LLM readiness is cached to prevent `/ready/llm` from hammering the
private LLM service.

The backend LLM readiness cache/circuit breaker is controlled by:

| Variable | Default | Description |
| --- | ---: | --- |
| `COUNTRY_COMPARE_LLM_READY_CACHE_TTL_SECONDS` | `10` | Short TTL for successful and failed `/ready/llm` remote checks. |
| `COUNTRY_COMPARE_LLM_READY_FAILURE_THRESHOLD` | `3` | Consecutive remote failures before the cooldown opens. |
| `COUNTRY_COMPARE_LLM_READY_FAILURE_COOLDOWN_SECONDS` | `30` | How long remote checks are skipped after repeated failures. |

Refresh story:

1. Change environment variables, mounted config, or secrets.
2. Restart the API process/container.
3. Confirm `/health`, `/ready`, and `/ready/llm` after startup.

Unit tests may call `reset_llm_readiness_state_for_tests()` to clear the
process-local readiness cache/circuit state. Production code should not call test
reset helpers.

## LLM forecast service

`ServiceSettings.from_env()` reads LLM forecast service settings at startup.
`create_app()` configures metric histogram buckets from the resolved settings.
Changing histogram bucket variables requires a service restart because Prometheus
histogram bucket shape is part of the metric time series identity.

Configurable bucket variables:

| Variable | Default |
| --- | --- |
| `LLM_HTTP_DURATION_BUCKETS` | `0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,2.5,5,10` |
| `LLM_FORECAST_DURATION_BUCKETS` | `0.05,0.1,0.25,0.5,1,2.5,5,10,30` |
| `LLM_PROVIDER_DURATION_BUCKETS` | `0.05,0.1,0.25,0.5,1,2.5,5,10,30` |
| `LLM_QUEUE_WAIT_BUCKETS` | `0.001,0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,2.5,5` |

Bucket values must be comma-separated, positive, and strictly increasing.

Refresh story:

1. Change service environment variables or secrets.
2. Restart the LLM service process/container.
3. Confirm `/health`, `/ready`, `/v1/capabilities`, and `/metrics`.

## Diagnostic payload policy

User-facing response payloads must contain short, actionable messages that do not
include raw exception text, upstream hostnames, provider payloads, tokens, API
keys, stack traces, or environment values.

Operator diagnostics should be represented as safe codes or pointers such as
`failure_reason_code`, `diagnostic_messages.operator`, and request IDs. Full
technical detail belongs in structured logs.

## Future admin refresh endpoint

A live admin refresh endpoint is intentionally not implemented. If one is added,
it must be protected by strong internal-only authentication, must clear all
relevant process-local caches atomically, and must document which dependencies
are safe to rebuild without a full process restart.