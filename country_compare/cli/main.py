from __future__ import annotations

import argparse
from pathlib import Path
from collections.abc import Sequence

from country_compare.cli.config import validate_config
from country_compare.cli.data import validate_data
from country_compare.cli.demo import explain_demo_placeholder
from country_compare.cli.ui import main as run_ui
from country_compare.pipelines.runners import run_processing_manifest
from country_compare.settings import load_app_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="country-compare")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ui_parser = subparsers.add_parser("ui", help="Run the Streamlit UI.")
    ui_parser.add_argument("streamlit_args", nargs=argparse.REMAINDER)

    config_parser = subparsers.add_parser(
        "validate-config", help="Validate metrics and scoring config files."
    )
    config_parser.add_argument("--metrics", type=Path, default=None)
    config_parser.add_argument("--scoring", type=Path, default=None)

    data_parser = subparsers.add_parser(
        "validate-data", help="Validate the canonical metric dataset."
    )
    data_parser.add_argument("--store-backend", default=None)
    data_parser.add_argument("--store-path", type=Path, default=None)

    update_parser = subparsers.add_parser("update-data", help="Run a manifest-driven data update.")
    update_parser.add_argument("--manifest", type=Path, required=True)

    subparsers.add_parser("demo", help="Show the current demo command status.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_app_settings()

    if args.command == "ui":
        return run_ui(args.streamlit_args)

    if args.command == "validate-config":
        validate_config(
            args.metrics or settings.paths.metrics_config_path,
            args.scoring or settings.paths.scoring_config_path,
        )
        print("Configuration is valid.")
        return 0

    if args.command == "validate-data":
        row_count = validate_data(
            store_backend=args.store_backend or settings.paths.store_backend,
            store_path=args.store_path or settings.paths.store_path,
        )
        print(f"Canonical dataset is valid. Rows: {row_count}")
        return 0

    if args.command == "update-data":
        result = run_processing_manifest(args.manifest)
        ok = bool(getattr(result, "ok", False))
        row_count = len(getattr(result, "canonical_dataframe", []))
        print(f"Processing run complete. ok={ok} rows={row_count}")
        return 0 if ok else 1

    if args.command == "demo":
        print(explain_demo_placeholder())
        return 2

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())