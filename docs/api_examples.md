# API examples

This optional helper document collects copy/paste requests for local testing. The canonical API contract is in `api.md`.

Set a base URL:

```bash
BASE_URL=http://localhost:8000
```

Metadata:

```bash
curl -s "$BASE_URL/api/v1/metadata/dataset"
curl -s "$BASE_URL/api/v1/metadata/countries"
curl -s "$BASE_URL/api/v1/metadata/metrics"
curl -s "$BASE_URL/api/v1/metadata/profiles"
curl -s "$BASE_URL/api/v1/metadata/prediction-methods"
```

Readiness:

```bash
curl -s "$BASE_URL/health"
curl -s "$BASE_URL/ready"
curl -s "$BASE_URL/ready/llm"
```

Authenticated request when `COUNTRY_COMPARE_API_KEY` is set:

```bash
curl -s "$BASE_URL/api/v1/metadata/dataset" \
  -H "Authorization: Bearer $COUNTRY_COMPARE_API_KEY" \
  -H "X-Request-ID: local-demo-1"
```
