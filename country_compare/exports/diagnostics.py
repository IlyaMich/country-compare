from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any


def export_diagnostics_json(
    diagnostics: Any,
    output_path: str | Path,
    *,
    create_parent_dirs: bool = True,
    indent: int = 2,
) -> Path:
    """Export diagnostics or metadata as JSON."""
    resolved_path = Path(output_path)

    if create_parent_dirs:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

    resolved_path.write_text(
        json.dumps(_to_jsonable(diagnostics), indent=indent, sort_keys=True),
        encoding="utf-8",
    )
    return resolved_path


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}

    if isinstance(value, list | tuple | set):
        return [_to_jsonable(item) for item in value]

    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump(mode="json"))

    if hasattr(value, "to_dict"):
        return _to_jsonable(value.to_dict())

    return value
