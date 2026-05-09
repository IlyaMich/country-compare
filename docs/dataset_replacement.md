# Dataset artifact replacement and rollback

Country Compare public-beta API deployments use immutable, read-only processed
dataset artifacts. The running API does not ingest, refresh, replace, or mutate
datasets. Dataset replacement is an offline operator workflow followed by a
backend process restart or redeploy.

## Artifact set

A complete processed dataset release consists of these files:

```text
data/processed/metrics.parquet
data/processed/metrics_manifest.json
data/processed/catalog.json
```

| Artifact | Purpose |
|---|---|
| `metrics.parquet` | Canonical processed metric dataset used by comparison, scoring, prediction, metadata, and UI workflows. |
| `metrics_manifest.json` | Dataset identity and validation metadata, including row count and content hash. |
| `catalog.json` | Precomputed metadata catalog used by API metadata endpoints for countries, metrics, years, categories, and dataset summary. |

Keep these three files together as one versioned dataset artifact set. Do not
replace only one file in production unless you are intentionally recovering from
a failed or partial deployment.

## Runtime behavior

The API is read-only.

It does not expose:

```text
dataset refresh endpoints
ingestion endpoints
admin replacement endpoints
cache invalidation endpoints
write endpoints
```

The API also uses a process-local dataframe cache. After replacing deployed
dataset files, restart or redeploy the backend process so the new dataset is
loaded.

In Docker deployments, `config/` and `data/processed/` should be mounted
read-only for the backend API.

## Recommended replacement workflow

Use this workflow for every dataset replacement:

```text
1. Generate candidate artifacts offline.
2. Validate the candidate dataset and config.
3. Review dataset identity and basic metadata.
4. Back up the currently deployed artifact set.
5. Replace the deployed artifact set.
6. Restart or redeploy the backend.
7. Verify /health, /ready, metadata, and one comparison request.
8. Keep the previous artifact set available for rollback.
```

## 1. Generate candidate artifacts offline

For the standard local data generation path, run:

```bash
python scripts/update_parquet_data_wb.py --skip-audit
```

This should produce or update:

```text
data/processed/metrics.parquet
data/processed/metrics_manifest.json
data/processed/catalog.json
```

If you already have a processed `metrics.parquet` file and only need to rebuild
the metadata catalog, run:

```bash
python scripts/generate_metadata_catalog.py \
  --dataset-path data/processed/metrics.parquet
```

Expected output:

```text
data/processed/catalog.json
```

## 2. Validate candidate artifacts

Run the standard validation commands from the repository root:

```bash
country-compare validate-data
country-compare validate-config
```

For API deployments, also validate readiness after starting the backend against
the candidate files:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
curl -i http://localhost:8000/health
curl -i http://localhost:8000/ready
curl -i http://localhost:8000/api/v1/metadata/dataset
```

Expected behavior:

```text
/health returns 200
/ready returns 200
/api/v1/metadata/dataset returns exists=true and row_count > 0
```

If `/health` passes but `/ready` fails, the process is alive but the dataset,
manifest, catalog, or config is not ready for traffic.

## 3. Review dataset identity

Inspect the manifest before promotion:

```bash
python - <<'PY'
import json
from pathlib import Path

manifest = json.loads(Path("data/processed/metrics_manifest.json").read_text())
for key in (
    "dataset_version",
    "created_at",
    "dataset_file",
    "row_count",
    "sha256",
    "schema_version",
):
    print(f"{key}: {manifest.get(key)}")
PY
```

Inspect the catalog summary:

```bash
python - <<'PY'
import json
from pathlib import Path

catalog = json.loads(Path("data/processed/catalog.json").read_text())
print("schema_version:", catalog.get("schema_version"))
print("identity:", catalog.get("identity"))
print("dataset:", catalog.get("dataset"))
print("countries:", len(catalog.get("countries", [])))
print("metrics:", len(catalog.get("metrics", [])))
print("years:", len(catalog.get("years", [])))
print("categories:", len(catalog.get("categories", [])))
PY
```

The manifest hash and catalog identity should describe the same dataset release.

## 4. Back up the current deployed artifact set

Before replacing production artifacts, save the existing set together.

Bash:

```bash
backup_dir="backups/datasets/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
cp data/processed/metrics.parquet "$backup_dir/metrics.parquet"
cp data/processed/metrics_manifest.json "$backup_dir/metrics_manifest.json"
cp data/processed/catalog.json "$backup_dir/catalog.json"
echo "$backup_dir"
```

Windows PowerShell:

```powershell
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = "backups/datasets/$timestamp"
New-Item -ItemType Directory -Force $backupDir | Out-Null
Copy-Item data/processed/metrics.parquet "$backupDir/metrics.parquet"
Copy-Item data/processed/metrics_manifest.json "$backupDir/metrics_manifest.json"
Copy-Item data/processed/catalog.json "$backupDir/catalog.json"
Write-Output $backupDir
```

## 5. Replace deployed artifacts

For a local Docker Compose deployment, replace the files on the host under:

```text
data/processed/
```

The backend container sees these files at:

```text
/app/data/processed/
```

Recommended host-side replacement from a candidate directory:

```bash
cp candidate/metrics.parquet data/processed/metrics.parquet
cp candidate/metrics_manifest.json data/processed/metrics_manifest.json
cp candidate/catalog.json data/processed/catalog.json
```

Windows PowerShell:

```powershell
Copy-Item candidate/metrics.parquet data/processed/metrics.parquet
Copy-Item candidate/metrics_manifest.json data/processed/metrics_manifest.json
Copy-Item candidate/catalog.json data/processed/catalog.json
```

For production platforms, prefer the platform’s atomic artifact promotion
mechanism when available. The important rule is that the backend should observe a
matching `metrics.parquet`, `metrics_manifest.json`, and `catalog.json` from the
same dataset release.

## 6. Restart or redeploy

Restart the backend after replacing files. This is required because the API uses
a process-local dataset cache.

Default Docker Compose:

```bash
docker compose up -d --force-recreate backend
```

Backend-only Compose:

```bash
docker compose -f compose.api.yml up -d --force-recreate backend
```

A full rebuild is not required when only mounted data files changed, but it is
safe:

```bash
docker compose up --build
```

## 7. Post-replacement verification

Run operational checks:

```bash
curl -i http://localhost:8000/health
curl -i http://localhost:8000/ready
curl -i -H "X-Request-ID: dataset-check-1" \
  http://localhost:8000/api/v1/metadata/dataset
```

Verify that the `X-Request-ID` response header is present.

Run metadata selector checks:

```bash
curl -i http://localhost:8000/api/v1/metadata/countries
curl -i http://localhost:8000/api/v1/metadata/metrics
curl -i http://localhost:8000/api/v1/metadata/years
```

Run one comparison check with valid country and metric IDs from your metadata:

```bash
curl -i -X POST http://localhost:8000/api/v1/compare/single-metric \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: dataset-comparison-check-1" \
  -d '{
    "country_codes": ["USA", "FRA"],
    "metric_id": "gdp_per_capita",
    "year_strategy": "latest_per_metric",
    "top_n": 2
  }'
```

Adjust `country_codes` and `metric_id` to values available in your dataset.

Expected behavior:

```text
HTTP 200
response body has ok=true
response includes X-Request-ID
main result table has row_count > 0
```

## 8. Rollback workflow

Rollback is the same operation as replacement, using the previous complete
artifact set.

Bash:

```bash
cp backups/datasets/<previous-version>/metrics.parquet data/processed/metrics.parquet
cp backups/datasets/<previous-version>/metrics_manifest.json data/processed/metrics_manifest.json
cp backups/datasets/<previous-version>/catalog.json data/processed/catalog.json
docker compose up -d --force-recreate backend
```

Backend-only Compose:

```bash
docker compose -f compose.api.yml up -d --force-recreate backend
```

Then verify:

```bash
curl -i http://localhost:8000/health
curl -i http://localhost:8000/ready
curl -i http://localhost:8000/api/v1/metadata/dataset
```

## Troubleshooting

### `/health` passes but `/ready` fails

The process is alive, but the API is not ready for traffic.

Check:

```bash
ls -l data/processed
ls -l config
```

Expected files:

```text
data/processed/metrics.parquet
data/processed/metrics_manifest.json
data/processed/catalog.json
config/metrics.yaml
config/scoring_profiles.yaml
```

### Metadata looks stale after replacing files

Restart or redeploy the backend. The API caches the canonical dataframe per
process and only invalidates that cache on process restart.

```bash
docker compose up -d --force-recreate backend
```

### Dataset path points to `site-packages`

Inside a production-installed container, default relative paths can resolve under
Python `site-packages` if runtime path environment variables are missing.

Verify container paths:

```bash
docker compose exec backend sh -lc 'python - <<PY
from country_compare.services.app_context import AppContext
ctx = AppContext.from_env()
print("metrics:", ctx.metrics_config_path)
print("scoring:", ctx.scoring_config_path)
print("store:", ctx.store_path)
PY'
```

Expected paths:

```text
/app/config/metrics.yaml
/app/config/scoring_profiles.yaml
/app/data/processed/metrics.parquet
```

If the paths point to `site-packages`, set these environment variables in the
container:

```text
COUNTRY_COMPARE_METRICS_CONFIG=/app/config/metrics.yaml
COUNTRY_COMPARE_SCORING_CONFIG=/app/config/scoring_profiles.yaml
COUNTRY_COMPARE_STORE_PATH=/app/data/processed/metrics.parquet
```

### Catalog is missing

Regenerate it from the processed dataset:

```bash
python scripts/generate_metadata_catalog.py \
  --dataset-path data/processed/metrics.parquet
```

Restart the backend after adding the catalog.

### Comparison smoke check fails

Confirm that the metric and country codes exist:

```bash
curl http://localhost:8000/api/v1/metadata/countries
curl http://localhost:8000/api/v1/metadata/metrics
```

Then retry with valid values from those responses.

## Public-beta policy

For public beta:

```text
dataset replacement is offline-only
API containers mount processed data read-only
no API endpoint refreshes or mutates data
new artifacts are activated by restart/redeploy
rollback uses the previous complete artifact set
```