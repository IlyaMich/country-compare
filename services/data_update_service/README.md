# Country Compare Data Update Service

This service is the operational data-refresh subsystem for Country Compare.

Milestone 1 intentionally includes only the shared refresh runner, CLI adapter,
filesystem artifact package writer, and unit tests. Kafka, Postgres, MinIO/S3,
private admin API endpoints, retries, DLQ handling, and dataset promotion are
added in later milestones.

## Local dry run

Install the main Country Compare package first, then install this service:

```bash
python -m pip install -e ".[dev]"
python -m pip install -e "services/data_update_service[dev]"
```

Run a dry-run refresh:

```bash
python -m data_update_service.cli refresh \
  --source-family world_bank \
  --manifest-path config/source_manifests/world_bank_real_data.yaml \
  --mode full_refresh \
  --dry-run true \
  --publish false \
  --promote false \
  --promotion-channel staging
```

The runner reuses `country_compare.pipelines.runners.run_processing_manifest()`
so CI and later Kafka workers can call the same orchestration path.

## Make targets

From `services/data_update_service`:

```bash
make install-dev
make test
make lint
make format-check
make typecheck
make check
make run
```

`make run` executes the Milestone 1 dry-run CLI path from the repository root.
Use `make refresh-artifact` to publish a local immutable filesystem artifact package.

Common overrides:

```bash
make run MANIFEST_PATH=config/source_manifests/world_bank_real_data.yaml
make refresh-artifact ARTIFACT_ROOT=data/artifacts/data_update PROMOTION_CHANNEL=staging
```

