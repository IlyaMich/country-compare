from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path


def export_markdown_summary(
    output_path: str | Path,
    *,
    title: str,
    sections: Mapping[str, str | Sequence[str]],
    create_parent_dirs: bool = True,
) -> Path:
    """Write a simple Markdown summary report."""
    resolved_path = Path(output_path)

    if create_parent_dirs:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [f"# {title}", ""]

    for heading, content in sections.items():
        lines.extend([f"## {heading}", ""])

        if isinstance(content, str):
            lines.extend([content, ""])
            continue

        for item in content:
            lines.append(f"- {item}")
        lines.append("")

    resolved_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return resolved_path
