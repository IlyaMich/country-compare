
# API operational settings

The FastAPI backend is a read-only transport adapter. These settings harden only
HTTP transport behavior; comparison, scoring, prediction, config, and data logic
remain in framework-neutral service/domain layers.

## Environment and authentication

`COUNTRY_COMPARE_API_ENV` accepts `development`, `test`, or `production`. If it is
unset, the API behaves as `development`. `COUNTRY_COMPARE_ENV` is also accepted as
a fallback.

Authentication is enabled whenever `COUNTRY_COMPARE_API_KEY` is set. Protected
endpoints accept either `X-API-Key: <key>` or `Authorization: Bearer <key>`.

In production, `COUNTRY_COMPARE_API_AUTH_REQUIRED` defaults to `true`, so startup
fails if `COUNTRY_COMPARE_API_KEY` is missing. In development/test, auth is not
required by default so local workflows can run without a key.

The API key is never logged, included in OpenAPI examples, or returned in errors.

## Docs exposure

`COUNTRY_COMPARE_API_ENABLE_DOCS` controls `/docs`, `/redoc`, and
`/openapi.json`. The default is enabled outside production and disabled in
production. `COUNTRY_COMPARE_API_PROTECT_DOCS` defaults to `true` in production
and `false` otherwise. When docs are protected, they use the same API-key
middleware as other protected routes.

## Metrics endpoint

`COUNTRY_COMPARE_API_ENABLE_METRICS` controls the read-only `/metrics` endpoint.
It is disabled by default. `COUNTRY_COMPARE_API_PROTECT_METRICS` controls whether
`/metrics` requires the API key; it defaults to protected in production.

The built-in exporter emits Prometheus-compatible process-local metrics:

- `country_compare_api_requests_total{method,path,status}`
- `country_compare_api_request_duration_seconds` histogram
- `country_compare_api_exceptions_total{exception_type,status,error_code}`
- `country_compare_api_auth_failures_total{reason}`

Route labels are normalized from FastAPI route templates where available. Query
strings and raw URLs are not used as labels.

## Path protection rules

`COUNTRY_COMPARE_API_PROTECTED_PREFIXES` defaults to `/api/v1,/ready`.
`COUNTRY_COMPARE_API_PUBLIC_PATHS` defaults to `/health,/docs,/redoc,/openapi.json`.
Docs and metrics protection settings take precedence over public-path defaults.

## Runtime path settings

The service runtime resolves `AppContext` paths to absolute paths before services use them.
Required configuration files are validated at context initialization:

- `COUNTRY_COMPARE_CONFIG_DIR`
- `COUNTRY_COMPARE_DATA_DIR`
- `COUNTRY_COMPARE_METRICS_CONFIG`
- `COUNTRY_COMPARE_SCORING_CONFIG`
- `COUNTRY_COMPARE_STORE_PATH`
- `COUNTRY_COMPARE_AUDIT_DIR`
- `COUNTRY_COMPARE_EXPORT_DIR`

`COUNTRY_COMPARE_METRICS_CONFIG` and `COUNTRY_COMPARE_SCORING_CONFIG` override
`COUNTRY_COMPARE_CONFIG_DIR` when both are set. `COUNTRY_COMPARE_AUDIT_DIR` and
`COUNTRY_COMPARE_EXPORT_DIR` override `COUNTRY_COMPARE_DATA_DIR` when both are set.

## Logging

Structured access logs include request id, method, normalized path, status, and
duration. Security logs include missing/invalid key events without request
bodies, query strings, authorization headers, bearer tokens, or API keys.

Settings:

- `COUNTRY_COMPARE_API_CONFIGURE_LOGGING` default `true`
- `COUNTRY_COMPARE_API_LOG_LEVEL` default `INFO`, validated against Python log levels
- `COUNTRY_COMPARE_API_LOG_FORMAT` `json` or `plain`, default `json`
- `COUNTRY_COMPARE_API_LOG_PROPAGATE` default `false`
- `COUNTRY_COMPARE_API_LOG_CLEAR_HANDLERS` default `false`

Existing handlers are preserved unless clear-handlers is explicitly enabled.

## Numeric bounds

API-side request limits still default to the current values, but env overrides now
fail fast if they are non-integer, non-positive, or exceed these upper bounds:

| Setting | Default | Upper bound |
|---|---:|---:|
| `COUNTRY_COMPARE_API_MAX_RECORDS` | 500 | 10000 |
| `COUNTRY_COMPARE_API_MAX_COUNTRIES` | 50 | 250 |
| `COUNTRY_COMPARE_API_MAX_METRICS` | 50 | 500 |
| `COUNTRY_COMPARE_API_MAX_HORIZON_YEARS` | 10 | 50 |
| `COUNTRY_COMPARE_API_MAX_HOLDOUT_YEARS` | 10 | 50 |
| `COUNTRY_COMPARE_API_MAX_TOP_N` | 100 | 500 |

## Example local development

```bash
COUNTRY_COMPARE_API_ENV=development
COUNTRY_COMPARE_API_ENABLE_DOCS=true
COUNTRY_COMPARE_API_ENABLE_METRICS=true
COUNTRY_COMPARE_API_PROTECT_METRICS=false
```

## Example production

```bash
COUNTRY_COMPARE_API_ENV=production
COUNTRY_COMPARE_API_KEY=replace-with-secret
COUNTRY_COMPARE_API_ENABLE_DOCS=false
COUNTRY_COMPARE_API_ENABLE_METRICS=true
COUNTRY_COMPARE_API_PROTECT_METRICS=true
COUNTRY_COMPARE_API_LOG_FORMAT=json
COUNTRY_COMPARE_API_LOG_LEVEL=INFO
```
