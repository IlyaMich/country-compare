from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_HELP_TEXT = """\
usage: country-compare-ui [OPTIONS] [-- STREAMLIT_ARGS...]

Launch the Country Compare Streamlit UI.

Options:
  -h, --help          Show this concise help message and exit.
  --streamlit-help    Show Streamlit's full `streamlit run` help.

Examples:
  country-compare-ui
  country-compare-ui -- --server.port 8502
  country-compare-ui -- --server.address 0.0.0.0
  country-compare-ui --streamlit-help

Notes:
  Any arguments after `--` are forwarded to Streamlit.
"""


def _app_path() -> Path:
    return Path(__file__).resolve().parents[1] / "ui" / "app.py"


def _normalize_streamlit_args(args: list[str]) -> list[str]:
    if args and args[0] == "--":
        return args[1:]
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if any(arg in {"-h", "--help"} for arg in args):
        print(_HELP_TEXT)
        return 0

    if "--streamlit-help" in args:
        completed = subprocess.run(
            [sys.executable, "-m", "streamlit", "run", "--help"],
            check=False,
        )
        return completed.returncode

    streamlit_args = _normalize_streamlit_args(args)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            *streamlit_args,
            str(_app_path()),
        ],
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
