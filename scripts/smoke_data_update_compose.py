from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COMPOSE_BASE = [
    "docker",
    "compose",
    "-f",
    "docker-compose.yml",
    "-f",
    "docker-compose.data-update.yml",
    "--profile",
    "data-update",
]

STACK_SERVICES = [
    "data-update-postgres",
    "data-update-kafka",
    "data-update-kafka-init",
    "data-update-minio",
    "data-update-minio-init",
    "data-update-worker",
    "data-update-retry-relay",
]

EXPECTED_ARTIFACT_FILES = [
    "metrics.parquet",
    "metrics_manifest.json",
    "catalog.json",
    "validation_report.json",
    "diff_report.json",
    "diff_report.md",
    "source_audit.json",
    "refresh_command.json",
    "refresh_result.json",
]

FAILURE_STATUSES = {
    "failed_retryable",
    "failed_non_retryable",
    "dlq",
}


def run(args: list[str], *, capture: bool = False) -> str:
    print("+", " ".join(args), flush=True)
    completed = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=capture,
        check=False,
    )
    if completed.returncode != 0:
        if capture:
            print(completed.stdout)
            print(completed.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {' '.join(args)}")
    return completed.stdout if capture else ""


def compose(args: list[str], *, capture: bool = False) -> str:
    return run([*COMPOSE_BASE, *args], capture=capture)


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def psql(query: str) -> str:
    return compose(
        [
            "exec",
            "-T",
            "data-update-postgres",
            "psql",
            "-U",
            "country_compare",
            "-d",
            "country_compare",
            "-At",
            "-F",
            "|",
            "-c",
            query,
        ],
        capture=True,
    ).strip()


def publish_remote_command() -> dict[str, object]:
    output = compose(
        [
            "run",
            "--rm",
            "--no-deps",
            "data-update-worker",
            "python",
            "-m",
            "data_update_service.cli",
            "publish-command",
            "--source-family",
            "world_bank",
            "--manifest-path",
            "config/source_manifests/world_bank_real_data.yaml",
            "--mode",
            "full_refresh",
            "--acquisition-mode",
            "remote",
            "--dry-run",
            "false",
            "--publish",
            "true",
            "--promote",
            "true",
            "--promotion-channel",
            "staging",
            "--requested-by",
            "compose-smoke",
            "--kafka-bootstrap-servers",
            "data-update-kafka:9092",
            "--kafka-command-topic",
            "country-compare.data-refresh.commands.v1",
        ],
        capture=True,
    )
    return json.loads(output)


def wait_for_dataset(job_id: str, timeout_seconds: int) -> tuple[str, str]:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        job_row = psql(
            """
            SELECT
              status,
              COALESCE(output_dataset_version, ''),
              COALESCE(error_code, ''),
              COALESCE(error_message, '')
            FROM data_refresh_jobs
            WHERE job_id = %s
            """
            % sql_literal(job_id)
        )

        if not job_row:
            time.sleep(5)
            continue

        status, output_dataset_version, error_code, error_message = job_row.split("|", 3)
        print(f"job_id={job_id} status={status}")

        if status in FAILURE_STATUSES:
            raise RuntimeError(
                "Refresh job failed: "
                f"status={status} error_code={error_code} error_message={error_message}"
            )

        if status == "completed":
            dataset_row = psql(
                """
                SELECT dataset_version, artifact_uri
                FROM dataset_versions
                WHERE dataset_version = %s
                   OR created_by_job_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """
                % (sql_literal(output_dataset_version), sql_literal(job_id))
            )
            if dataset_row:
                dataset_version, artifact_uri = dataset_row.split("|", 1)
                return dataset_version, artifact_uri

        if status == "completed_no_changes":
            raise RuntimeError(
                "Smoke expected a published artifact, but the job completed with no changes."
            )

        time.sleep(5)

    raise TimeoutError(f"Timed out waiting for job completion: {job_id}")


def verify_staging_channel(dataset_version: str) -> None:
    channel_version = psql(
        """
        SELECT dataset_version
        FROM dataset_channels
        WHERE channel = 'staging'
        """
    )

    if channel_version != dataset_version:
        raise RuntimeError(
            "Staging channel did not point at the new dataset version: "
            f"expected={dataset_version} actual={channel_version}"
        )


def verify_minio_artifacts(artifact_uri: str) -> None:
    if not artifact_uri.startswith("s3://"):
        raise RuntimeError(f"Expected s3:// artifact URI, got: {artifact_uri}")

    bucket_and_prefix = artifact_uri.removeprefix("s3://").strip("/")
    bucket, prefix = bucket_and_prefix.split("/", 1)
    prefix = prefix.rstrip("/")

    for filename in EXPECTED_ARTIFACT_FILES:
        target = f"local/{bucket}/{prefix}/{filename}"
        compose(
            [
                "run",
                "--rm",
                "--no-deps",
                "data-update-minio-init",
                (
                    "mc alias set local http://data-update-minio:9000 minio minio123 >/dev/null "
                    f"&& mc stat {target} >/dev/null"
                ),
            ],
            capture=True,
        )
        print(f"verified s3://{bucket}/{prefix}/{filename}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the data-update compose smoke test.")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Stop the data-update stack and remove volumes before starting.",
    )
    parser.add_argument(
        "--down",
        action="store_true",
        help="Stop the data-update stack after the smoke completes.",
    )
    args = parser.parse_args()

    if args.reset:
        compose(["down", "-v", "--remove-orphans"])

    compose(["up", "-d", "--build", *STACK_SERVICES])

    try:
        publish_result = publish_remote_command()
        job_id = str(publish_result["job_id"])
        print(json.dumps(publish_result, indent=2, sort_keys=True))

        dataset_version, artifact_uri = wait_for_dataset(
            job_id=job_id,
            timeout_seconds=args.timeout_seconds,
        )
        verify_staging_channel(dataset_version)
        verify_minio_artifacts(artifact_uri)

        print(
            json.dumps(
                {
                    "ok": True,
                    "job_id": job_id,
                    "dataset_version": dataset_version,
                    "artifact_uri": artifact_uri,
                    "promotion_channel": "staging",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    finally:
        if args.down:
            compose(["down", "--remove-orphans"])


if __name__ == "__main__":
    raise SystemExit(main())