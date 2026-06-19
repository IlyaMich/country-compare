# Country Compare Data Update Service

This service is the operational data-refresh subsystem for Country Compare.

It owns refresh orchestration, Kafka worker execution, retry/DLQ handling, source acquisition, immutable artifact publication, dataset registry writes, channel promotion, and dataset lifecycle events.

The shared execution entrypoint is:

```text
run_refresh_job(command, deps)
```

It is used by:

```text
CLI refresh
Kafka worker refresh
future private data-update API refresh
```

## Documentation

See:

```text
docs/data_update_service.md
```

## Install

From the repository root:

```bash
python -m pip install -e ".[dev,ml]"
python -m pip install -e "services/data_update_service[dev,kafka,postgres,s3]"
```

## Checks

From `services/data_update_service`:

```bash
python -m ruff check src/data_update_service tests
python -m black --check src/data_update_service tests
python -m mypy src/data_update_service
python -m pytest
```

Or:

```bash
make check
```

## Local dry run

From the repository root:

```bash
python -m data_update_service.cli refresh \
  --source-family world_bank \
  --manifest-path config/source_manifests/world_bank_real_data.yaml \
  --mode full_refresh \
  --acquisition-mode remote \
  --dry-run true \
  --publish false \
  --promote false \
  --promotion-channel staging
```

## Compose smoke

Start the committed local Kafka/Postgres/MinIO worker stack:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.data-update.yml \
  --profile data-update \
  up --build \
  data-update-kafka \
  data-update-kafka-init \
  data-update-postgres \
  data-update-minio \
  data-update-minio-init \
  data-update-worker \
  data-update-retry-relay
```

Run the repeatable smoke script:

```bash
python scripts/smoke_data_update_compose.py
```

The smoke publishes a remote World Bank refresh command, waits for completion, verifies the `dataset_versions` row, verifies the `staging` channel, and checks the expected MinIO artifact files.

## Operational notes

Remote acquisition is the preferred container smoke path. It does not require local raw data mounted into the worker container.

For `ACQUISITION_MODE=local` inside the worker container, the expected raw files must exist inside the container under paths such as:

```text
/app/data/raw/compensation_employees_lcu/wb_compensation_employees_lcu.csv
```

For local acquisition testing, mount raw data read-only:

```yaml
data-update-worker:
  volumes:
    - ./data/raw:/app/data/raw:ro
```

Without this mount, local acquisition can fail before artifact publication with a `source_acquisition_failed` error. This is expected.

## Kafka topics

Refresh topics:

```text
country-compare.data-refresh.commands.v1
country-compare.data-refresh.status.v1
country-compare.data-refresh.retry.5m.v1
country-compare.data-refresh.retry.1h.v1
country-compare.data-refresh.dlq.v1
```

Dataset lifecycle event topics:

```text
country-compare.dataset.versions.v1
country-compare.dataset.promotions.v1
```

## Current scope

The private data-update admin API is still a later implementation slice.

Manual/admin operation currently uses:

```text
CLI refresh
CLI publish-command
Kafka worker
Postgres inspection
DLQ inspection
```

The future API should produce Kafka commands and read durable state from Postgres. It should not run long refresh work inside the API process.
