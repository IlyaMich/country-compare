from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.runner import RunnerDependencies, run_refresh_job
from data_update_service.settings import DataUpdateSettings


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
    settings = DataUpdateSettings()
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
    refresh.add_argument("--dry-run", type=_parse_bool, default=True)
    refresh.add_argument("--publish", type=_parse_bool, default=False)
    refresh.add_argument("--promote", type=_parse_bool, default=False)
    refresh.add_argument(
        "--promotion-channel", choices=("staging", "prod"), default="staging"
    )
    refresh.add_argument("--requested-by", default="cli")
    refresh.add_argument("--artifact-root", type=Path, default=settings.artifact_root)
    refresh.add_argument("--audit-root", type=Path, default=settings.audit_root)
    refresh.add_argument("--max-attempts", type=int, default=settings.max_attempts)
    refresh.add_argument("--output-json", type=Path, default=None)
    return parser


def run_refresh_from_args(args: argparse.Namespace) -> int:
    command = RefreshCommand.create(
        source_family=args.source_family,
        manifest_path=args.manifest_path,
        mode=args.mode,
        dry_run=args.dry_run,
        publish=args.publish,
        promote=args.promote,
        promotion_channel=args.promotion_channel,
        requested_by=args.requested_by,
        max_attempts=args.max_attempts,
    )
    settings = DataUpdateSettings(
        artifact_root=args.artifact_root,
        audit_root=args.audit_root,
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "refresh":
        return run_refresh_from_args(args)
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
