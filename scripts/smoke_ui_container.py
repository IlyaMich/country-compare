from __future__ import annotations

import argparse
import time
import urllib.error
import urllib.request


class SmokeFailure(RuntimeError):
    """Raised when the UI container smoke test fails."""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test a running Country Compare UI container."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8501",
        help="Base URL for the UI container.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=90.0,
        help="Maximum time to wait for Streamlit health.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=5.0,
        help="Per-request timeout.",
    )

    args = parser.parse_args()

    _wait_for_streamlit(
        base_url=args.base_url,
        wait_seconds=args.wait_seconds,
        timeout_seconds=args.timeout_seconds,
    )

    print("UI container smoke checks passed.")
    return 0


def _wait_for_streamlit(
    *,
    base_url: str,
    wait_seconds: float,
    timeout_seconds: float,
) -> None:
    health_url = f"{base_url.rstrip('/')}/_stcore/health"
    deadline = time.time() + wait_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                health_url,
                timeout=timeout_seconds,
            ) as response:
                if response.status != 200:
                    raise SmokeFailure(
                        "Streamlit health endpoint returned " f"HTTP {response.status}."
                    )

                return
        except (
            OSError,
            SmokeFailure,
            urllib.error.URLError,
        ) as exc:
            last_error = exc
            time.sleep(2)

    raise SmokeFailure(
        "UI did not become healthy within " f"{wait_seconds} seconds: {last_error!r}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
