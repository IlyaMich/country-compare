from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from data_update_service.infrastructure.kafka import (
    ConfluentKafkaConsumer,
    ConfluentKafkaProducer,
    KafkaConsumer,
    KafkaProducer,
)
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.runner import RunnerDependencies, run_refresh_job
from data_update_service.settings import DataUpdateSettings
from data_update_service.worker.dlq import inspect_dlq_messages
from data_update_service.worker.publisher import publish_refresh_command

ACQUISITION_MODE_CHOICES = ("local", "remote", "auto")


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value!r}")


def build_parser() -> argparse.ArgumentParser:
    settings = DataUpdateSettings.from_env()
    parser = argparse.ArgumentParser(
        description="Country Compare data update service CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    refresh = subparsers.add_parser(
        "refresh", help="Run a data refresh through the shared runner"
    )
    refresh.add_argument("--source-family", default=settings.default_source_family)
    refresh.add_argument(
        "--manifest-path", type=Path, default=settings.default_manifest_path
    )
    refresh.add_argument(
        "--mode",
        choices=("full_refresh", "source_only", "validate_only"),
        default="full_refresh",
    )
    refresh.add_argument(
        "--acquisition-mode",
        choices=ACQUISITION_MODE_CHOICES,
        default="local",
        help="How source files are acquired before the manifest pipeline runs.",
    )
    refresh.add_argument("--dry-run", type=_parse_bool, default=True)
    refresh.add_argument("--publish", type=_parse_bool, default=False)
    refresh.add_argument("--promote", type=_parse_bool, default=False)
    refresh.add_argument(
        "--promotion-channel", choices=("staging", "prod"), default="staging"
    )
    refresh.add_argument("--requested-by", default="cli")
    refresh.add_argument("--artifact-root", type=Path, default=settings.artifact_root)
    refresh.add_argument("--audit-root", type=Path, default=settings.audit_root)
    refresh.add_argument("--workspace-root", type=Path, default=settings.workspace_root)
    refresh.add_argument("--max-attempts", type=int, default=settings.max_attempts)
    refresh.add_argument("--output-json", type=Path, default=None)

    publish = subparsers.add_parser(
        "publish-command",
        help="Publish a RefreshCommand to the Kafka command topic",
    )
    inspect_dlq = subparsers.add_parser(
        "inspect-dlq",
        help="Inspect messages from the Kafka DLQ topic",
    )
    inspect_dlq.add_argument(
        "--kafka-bootstrap-servers",
        default=settings.kafka_bootstrap_servers,
    )
    inspect_dlq.add_argument("--kafka-dlq-topic", default=settings.kafka_dlq_topic)
    inspect_dlq.add_argument(
        "--consumer-group",
        default=settings.kafka_dlq_consumer_group,
    )
    inspect_dlq.add_argument("--max-messages", type=int, default=10)
    inspect_dlq.add_argument("--timeout-seconds", type=float, default=1.0)
    inspect_dlq.add_argument("--max-empty-polls", type=int, default=2)
    inspect_dlq.add_argument("--commit", type=_parse_bool, default=False)
    inspect_dlq.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
    )
    inspect_dlq.add_argument("--output-json", type=Path, default=None)
    publish.add_argument("--source-family", default=settings.default_source_family)
    publish.add_argument(
        "--manifest-path", type=Path, default=settings.default_manifest_path
    )
    publish.add_argument(
        "--mode",
        choices=("full_refresh", "source_only", "validate_only"),
        default="full_refresh",
    )
    publish.add_argument(
        "--acquisition-mode",
        choices=ACQUISITION_MODE_CHOICES,
        default="local",
        help="How the worker should acquire sources before running the pipeline.",
    )
    publish.add_argument("--dry-run", type=_parse_bool, default=True)
    publish.add_argument("--publish", type=_parse_bool, default=False)
    publish.add_argument("--promote", type=_parse_bool, default=False)
    publish.add_argument(
        "--promotion-channel", choices=("staging", "prod"), default="staging"
    )
    publish.add_argument("--requested-by", default="cli")
    publish.add_argument("--max-attempts", type=int, default=settings.max_attempts)
    publish.add_argument(
        "--kafka-bootstrap-servers", default=settings.kafka_bootstrap_servers
    )
    publish.add_argument("--kafka-command-topic", default=settings.kafka_command_topic)
    publish.add_argument("--output-json", type=Path, default=None)
    return parser


def _command_from_args(args: argparse.Namespace) -> RefreshCommand:
    return RefreshCommand.create(
        source_family=args.source_family,
        manifest_path=args.manifest_path,
        mode=args.mode,
        acquisition_mode=getattr(args, "acquisition_mode", "local"),
        dry_run=args.dry_run,
        publish=args.publish,
        promote=args.promote,
        promotion_channel=args.promotion_channel,
        requested_by=args.requested_by,
        max_attempts=args.max_attempts,
    )


def run_refresh_from_args(args: argparse.Namespace) -> int:
    command = _command_from_args(args)
    settings = DataUpdateSettings(
        artifact_root=args.artifact_root,
        audit_root=args.audit_root,
        workspace_root=args.workspace_root,
        max_attempts=args.max_attempts,
    )
    result = run_refresh_job(command, RunnerDependencies.local_defaults(settings))
    payload: dict[str, Any] = result.model_dump(mode="json")
    output = json.dumps(payload, indent=2, sort_keys=True)
    print(output)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(output + "\n", encoding="utf-8")
    return 0 if result.ok else 1


def publish_command_from_args(
    args: argparse.Namespace,
    *,
    producer: KafkaProducer | None = None,
) -> int:
    command = _command_from_args(args)
    resolved_producer = producer or ConfluentKafkaProducer(
        bootstrap_servers=args.kafka_bootstrap_servers,
    )
    metadata = publish_refresh_command(
        command=command,
        producer=resolved_producer,
        topic=args.kafka_command_topic,
    )
    payload: dict[str, Any] = {
        "published": True,
        "topic": metadata.topic,
        "key": metadata.key,
        "command_id": metadata.command_id,
        "job_id": metadata.job_id,
        "source_family": metadata.source_family,
        "acquisition_mode": command.acquisition_mode,
    }
    output = json.dumps(payload, indent=2, sort_keys=True)
    print(output)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(output + "\n", encoding="utf-8")
    return 0


def inspect_dlq_from_args(
    args: argparse.Namespace,
    *,
    consumer: KafkaConsumer | None = None,
) -> int:
    resolved_consumer = consumer or ConfluentKafkaConsumer(
        bootstrap_servers=args.kafka_bootstrap_servers,
        group_id=args.consumer_group,
        topics=[args.kafka_dlq_topic],
        auto_offset_reset="earliest",
    )

    try:
        result = inspect_dlq_messages(
            consumer=resolved_consumer,
            max_messages=args.max_messages,
            timeout_seconds=args.timeout_seconds,
            max_empty_polls=args.max_empty_polls,
            commit=args.commit,
        )
    finally:
        if consumer is None:
            resolved_consumer.close()

    payload: dict[str, Any] = {
        "topic": args.kafka_dlq_topic,
        "consumer_group": args.consumer_group,
        "committed": args.commit,
        **result.as_dict(),
    }

    if args.format == "text":
        output = _format_dlq_inspection_text(payload)
    else:
        output = json.dumps(payload, indent=2, sort_keys=True)

    print(output)

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return 0


def _format_dlq_inspection_text(payload: dict[str, Any]) -> str:
    messages = payload["messages"]
    lines = [
        f"DLQ topic: {payload['topic']}",
        f"Consumer group: {payload['consumer_group']}",
        f"Messages: {payload['count']}",
        f"Committed: {payload['committed']}",
    ]

    for index, message in enumerate(messages, start=1):
        event = message.get("event") or {}
        lines.extend(
            [
                "",
                f"[{index}] key={message.get('key')} "
                f"partition={message.get('partition')} offset={message.get('offset')}",
                f"    error_code={event.get('error_code') or message.get('parse_error')}",
                f"    error_message={event.get('error_message')}",
                f"    job_id={event.get('job_id')}",
                f"    command_id={event.get('command_id')}",
                f"    source_family={event.get('source_family')}",
                f"    original_topic={event.get('original_topic')}",
                f"    created_at={event.get('created_at')}",
            ]
        )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "refresh":
        return run_refresh_from_args(args)
    if args.command == "publish-command":
        return publish_command_from_args(args)
    if args.command == "inspect-dlq":
        return inspect_dlq_from_args(args)
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
