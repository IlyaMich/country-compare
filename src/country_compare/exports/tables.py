from __future__ import annotations

from pathlib import Path

import pandas as pd


def export_table_csv(
    dataframe: pd.DataFrame,
    output_path: str | Path,
    *,
    index: bool = False,
    create_parent_dirs: bool = True,
) -> Path:
    """
    Export a tabular result dataframe to CSV.

    This helper is intentionally small and framework-neutral so it can be used by
    scripts, CLI commands, services, and future UI download flows.
    """
    resolved_path = Path(output_path)

    if create_parent_dirs:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

    dataframe.to_csv(resolved_path, index=index)
    return resolved_path


def export_tables_csv(
    tables: dict[str, pd.DataFrame],
    output_dir: str | Path,
    *,
    index: bool = False,
) -> dict[str, Path]:
    """
    Export multiple named dataframe tables to one directory.

    Keys may be filenames with or without the .csv suffix.
    """
    resolved_dir = Path(output_dir)
    resolved_dir.mkdir(parents=True, exist_ok=True)

    exported: dict[str, Path] = {}

    for name, dataframe in tables.items():
        filename = name if name.endswith(".csv") else f"{name}.csv"
        exported[name] = export_table_csv(
            dataframe,
            resolved_dir / filename,
            index=index,
            create_parent_dirs=False,
        )

    return exported
