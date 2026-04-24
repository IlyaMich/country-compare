from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> int:
    app_path = Path(__file__).resolve().parents[1] / "ui" / "app.py"
    resolved_argv = list(sys.argv[1:] if argv is None else argv)
    return subprocess.call(
        [sys.executable, "-m", "streamlit", "run", str(app_path), *resolved_argv]
    )


if __name__ == "__main__":
    raise SystemExit(main())