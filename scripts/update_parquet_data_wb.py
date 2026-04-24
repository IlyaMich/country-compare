from __future__ import annotations

import argparse
from pathlib import Path

from country_compare.config.loader import load_metrics_config
from country_compare.data.stores.registry import create_metric_store
from country_compare.paths import CONFIG_DIR, METRICS_CONFIG_PATH
from country_compare.pipelines.runners import run_processing_manifest


DEFAULT_MANIFEST_PATH = CONFIG_DIR / "source_manifests" / "world_bank_real_data.yaml"
DEFAULT_AUDIT_DIR = CONFIG_DIR.parent / "data" / "audit" / "world_bank_update"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the processed parquet metric dataset from a manifest-driven raw-source refresh."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Path to the source manifest YAML.",
    )
    parser.add_argument(
        "--metrics-config",
        type=Path,
        default=METRICS_CONFIG_PATH,
        help="Path to metrics.yaml used for config validation.",
    )
    parser.add_argument(
        "--skip-config-validation",
        action="store_true",
        help="Disable config/dataframe consistency validation for this run.",
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Do not write audit artifacts for this run.",
    )
    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=DEFAULT_AUDIT_DIR,
        help="Directory used for audit artifacts when audit writing is enabled.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.manifest.exists():
        template_hint = args.manifest.with_suffix(".template.yaml")
        raise SystemExit(
            "Manifest file not found: "
            f"{args.manifest}\n"
            "Create it from the provided template first. Suggested starting point: "
            f"{template_hint}"
        )

    metrics_config = None
    validate_against_config = not args.skip_config_validation
    if validate_against_config:
        if not args.metrics_config.exists():
            raise SystemExit(f"metrics config not found: {args.metrics_config}")
        metrics_config = load_metrics_config(args.metrics_config)

    store = create_metric_store("parquet")

    result = run_processing_manifest(
        args.manifest,
        store=store,
        publish=True,
        write_metric_dataset=False,
        validate_against_config=validate_against_config,
        metrics_config=metrics_config,
        write_audit_artifacts=not args.skip_audit,
        output_dir=args.audit_dir,
    )

    if not result.ok:
        message = result.error or "processing failed"
        if result.validation_report is not None and result.validation_report.error_messages:
            message = f"{message}\nValidation errors: {result.validation_report.error_messages}"
        raise SystemExit(message)

    dataframe = result.canonical_dataframe
    if dataframe is None:
        raise SystemExit("processing finished without a canonical dataframe")

    print("rows:", len(dataframe.index))
    print("countries:", dataframe["country_code"].nunique())
    print("metrics:", dataframe["metric_id"].nunique())
    print("years:", sorted(dataframe["year"].astype(int).unique().tolist()))

    if result.publication_report is not None:
        print("published:", result.publication_report.ok)
        print("target_path:", result.publication_report.target_path)

    if result.audit_report is not None:
        print("audit_written:", result.audit_report.written)
        print("audit_dir:", result.audit_report.output_dir)

    for source_result in result.source_results:
        if not source_result.ok:
            print(f"FAILED: {source_result.source_id} -> {source_result.error}")


if __name__ == "__main__":
    main()
