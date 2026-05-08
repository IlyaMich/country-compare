from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCH_DIRS = (ROOT / "src", ROOT / "tests", ROOT / "scripts")


def main() -> int:
    failures: list[str] = []
    for path in _iter_python_files():
        text = path.read_text(encoding="utf-8")
        forbidden = "src." + "country_compare"
        if forbidden in text:
            failures.append(f"{path.relative_to(ROOT)} imports {forbidden}")
    if failures:
        print("Static guard failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Static guards passed.")
    return 0


def _iter_python_files():
    for directory in SEARCH_DIRS:
        if not directory.exists():
            continue
        yield from directory.rglob("*.py")


if __name__ == "__main__":
    raise SystemExit(main())
