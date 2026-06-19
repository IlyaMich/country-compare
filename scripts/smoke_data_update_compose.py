from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COMPOSE_COMMAND = shlex.split(
    os.environ.get("COUNTRY_COMPARE_COMPOSE_COMMAND", "podman compose")
)

COMPOSE_BASE = [
    *COMPOSE_COMMAND,
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

CHECK_WORKER_PUBLIC_NETWORK_CODE = r"""
from urllib.request import urlopen

url = "https://api.worldbank.org/v2/en/country/all/indicator/GC.XPN.COMP.CN?source=2&downloadformat=csv"
response = urlopen(url, timeout=60)
print(f"status={response.status}")
print(f"content_type={response.headers.get('content-type')}")
print(f"first_bytes={response.read(20)!r}")
"""

ENSURE_MINIO_BUCKET_CODE = r"""
import os
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

endpoint_url = os.environ["DATA_UPDATE_ARTIFACT_ENDPOINT_URL"]
bucket = os.environ["DATA_UPDATE_ARTIFACT_BUCKET"]
region = os.environ.get("DATA_UPDATE_ARTIFACT_REGION", "us-east-1")
access_key = os.environ["DATA_UPDATE_ARTIFACT_ACCESS_KEY_ID"]
secret_key = os.environ["DATA_UPDATE_ARTIFACT_SECRET_ACCESS_KEY"]

s3 = boto3.client(
    "s3",
    endpoint_url=endpoint_url,
    region_name=region,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    config=Config(s3={"addressing_style": "path"}),
)

deadline = time.monotonic() + 120

while True:
    try:
        s3.list_buckets()
        break
    except Exception as exc:
        if time.monotonic() >= deadline:
            raise RuntimeError("Timed out waiting for MinIO") from exc
        time.sleep(2)

try:
    s3.head_bucket(Bucket=bucket)
    print(f"bucket_exists={bucket}")
except ClientError as exc:
    error_code = str(exc.response.get("Error", {}).get("Code", ""))
    if error_code in {"404", "NoSuchBucket", "NotFound"}:
        s3.create_bucket(Bucket=bucket)
        print(f"bucket_created={bucket}")
    else:
        raise

s3.head_bucket(Bucket=bucket)
"""

VERIFY_MINIO_OBJECT_CODE = r"""
import os
import sys

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

bucket = sys.argv[1]
key = sys.argv[2]

endpoint_url = os.environ["DATA_UPDATE_ARTIFACT_ENDPOINT_URL"]
region = os.environ.get("DATA_UPDATE_ARTIFACT_REGION", "us-east-1")
access_key = os.environ["DATA_UPDATE_ARTIFACT_ACCESS_KEY_ID"]
secret_key = os.environ["DATA_UPDATE_ARTIFACT_SECRET_ACCESS_KEY"]

s3 = boto3.client(
    "s3",
    endpoint_url=endpoint_url,
    region_name=region,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    config=Config(s3={"addressing_style": "path"}),
)

try:
    s3.head_object(Bucket=bucket, Key=key)
except ClientError as exc:
    raise RuntimeError(f"Missing object: s3://{bucket}/{key}") from exc

print(f"object_exists=s3://{bucket}/{key}")
"""


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

        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: {' '.join(args)}"
        )

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


def extract_json_object(output: str) -> dict[str, object]:
    lines = output.splitlines()

    for index, line in enumerate(lines):
        if line.strip().startswith("{"):
            return json.loads("\n".join(lines[index:]))

    raise ValueError(f"No JSON object found in output:\n{output}")


def run_python_in_data_update_image(code: str, *args: str) -> str:
    return compose(
        [
            "run",
            "--rm",
            "--no-deps",
            "data-update-worker",
            "python",
            "-c",
            code,
            *args,
        ],
        capture=True,
    )


def ensure_minio_bucket() -> None:
    output = run_python_in_data_update_image(ENSURE_MINIO_BUCKET_CODE)

    if output.strip():
        print(output.strip())


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

    return extract_json_object(output)


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

        status, output_dataset_version, error_code, error_message = job_row.split(
            "|",
            3,
        )
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
        key = f"{prefix}/{filename}"
        output = run_python_in_data_update_image(
            VERIFY_MINIO_OBJECT_CODE,
            bucket,
            key,
        )

        if output.strip():
            print(output.strip())


def check_worker_public_network() -> None:
    output = run_python_in_data_update_image(CHECK_WORKER_PUBLIC_NETWORK_CODE)
    if output.strip():
        print(output.strip())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the data-update compose smoke test."
    )
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
    ensure_minio_bucket()
    check_worker_public_network()

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