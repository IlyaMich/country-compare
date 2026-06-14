from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from data_update_service.infrastructure.kafka import InMemoryKafkaProducer, KafkaMessage
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.runner import RunnerDependencies
from data_update_service.worker.events import DeadLetterEvent, RefreshStatusEvent
from data_update_service.worker.handlers import (
    RefreshCommandWorkerHandler,
    WorkerEventPublisher,
)


class FakePipelineResult:
    def __init__(
        self,
        *,
        ok: bool,
        dataframe: pd.DataFrame | None = None,
        error: str | None = None,
    ) -> None:
        self.ok = ok
        self.canonical_dataframe = dataframe
        self.error = error
        self.validation_report = {"ok": ok}
        self.warnings: list[str] = []


class FakePipelineRunner:
    def __init__(self, result: FakePipelineResult) -> None:
        self.result = result

    def run(self, command: RefreshCommand, *, audit_dir: Path) -> FakePipelineResult:
        del command, audit_dir
        return self.result


class FakeDiffGenerator:
    def generate(self, dataframe: pd.DataFrame) -> Any:
        from data_update_service.orchestration.diff import generate_diff_report

        return generate_diff_report(dataframe)


@dataclass(frozen=True, slots=True)
class FakeArtifact:
    dataset_version: str = "world_bank_2026-06-13T00-08-30Z_abcdef1"
    artifact_uri: str = "file:///tmp/artifact"
    parquet_sha256: str = "abcdef1234567890"
    validation_report_path: Path = Path("/tmp/artifact/validation_report.json")
    diff_report_json_path: Path = Path("/tmp/artifact/diff_report.json")


class FakeArtifactStore:
    def publish_package(self, **kwargs: Any) -> FakeArtifact:
        del kwargs
        return FakeArtifact()


def _command(
    tmp_path: Path, *, dry_run: bool = True, publish: bool = False
) -> RefreshCommand:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("sources: []\n", encoding="utf-8")
    return RefreshCommand.create(
        source_family="world_bank",
        manifest_path=manifest_path,
        dry_run=dry_run,
        publish=publish,
        command_id="cmd-test",
        job_id="job-test",
        idempotency_key="world_bank:full:test",
        correlation_id="corr-test",
    )


def _dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"country_code": "ISR", "metric_id": "gdp", "year": 2024},
            {"country_code": "FRA", "metric_id": "gdp", "year": 2025},
        ]
    )


def _handler(
    tmp_path: Path, producer: InMemoryKafkaProducer
) -> RefreshCommandWorkerHandler:
    dependencies = RunnerDependencies(
        pipeline_runner=FakePipelineRunner(
            FakePipelineResult(ok=True, dataframe=_dataframe())
        ),
        diff_generator=FakeDiffGenerator(),
        artifact_store=FakeArtifactStore(),
        audit_root=tmp_path / "audit",
    )
    return RefreshCommandWorkerHandler(
        event_publisher=WorkerEventPublisher(
            producer=producer,
            status_topic="status-topic",
            dlq_topic="dlq-topic",
        ),
        dependencies=dependencies,
    )


def test_worker_handler_processes_valid_command_and_emits_status_events(
    tmp_path,
) -> None:
    producer = InMemoryKafkaProducer()
    handler = _handler(tmp_path, producer)
    command = _command(tmp_path)
    message = KafkaMessage(
        topic="commands-topic",
        key="world_bank",
        value=command.model_dump_json().encode("utf-8"),
    )

    result = handler.process_message(message)

    assert result.status == "processed"
    assert result.ack is True
    assert result.job_id == command.job_id
    assert [item.topic for item in producer.messages] == [
        "status-topic",
        "status-topic",
    ]

    first_event = RefreshStatusEvent.model_validate_json(producer.messages[0].value)
    final_event = RefreshStatusEvent.model_validate_json(producer.messages[1].value)
    assert first_event.status == "accepted"
    assert final_event.status == "dry_run_completed"
    assert final_event.details["row_count"] == 2


def test_worker_handler_sends_invalid_command_to_dlq() -> None:
    producer = InMemoryKafkaProducer()
    handler = RefreshCommandWorkerHandler(
        event_publisher=WorkerEventPublisher(
            producer=producer,
            status_topic="status-topic",
            dlq_topic="dlq-topic",
        )
    )
    message = KafkaMessage(
        topic="commands-topic", key="world_bank", value=b'{"bad": "payload"}'
    )

    result = handler.process_message(message)

    assert result.status == "invalid_command_dlq"
    assert result.ack is True
    assert [item.topic for item in producer.messages] == ["dlq-topic"]
    dlq_event = DeadLetterEvent.model_validate_json(producer.messages[0].value)
    assert dlq_event.error_code == "invalid_refresh_command"
    assert dlq_event.original_topic == "commands-topic"
    assert dlq_event.raw_payload == '{"bad": "payload"}'


def test_worker_handler_sends_failed_refresh_result_to_dlq(tmp_path) -> None:
    producer = InMemoryKafkaProducer()
    handler = _handler(tmp_path, producer)
    command = RefreshCommand.create(
        source_family="world_bank",
        manifest_path=tmp_path / "missing.yaml",
        dry_run=True,
        publish=False,
        command_id="cmd-missing",
        job_id="job-missing",
        idempotency_key="world_bank:full:missing",
        correlation_id="corr-missing",
    )
    message = KafkaMessage(
        topic="commands-topic",
        key="world_bank",
        value=command.model_dump_json().encode("utf-8"),
    )

    result = handler.process_message(message)

    assert result.status == "failed_result_dlq"
    assert result.error_code == "manifest_not_found"
    assert [item.topic for item in producer.messages] == [
        "status-topic",
        "status-topic",
        "dlq-topic",
    ]
    dlq_event = DeadLetterEvent.model_validate_json(producer.messages[2].value)
    assert dlq_event.job_id == command.job_id
    assert dlq_event.error_code == "manifest_not_found"
