from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent


def _resolve_project_root(package_root: Path) -> Path:
    """Resolve the repository root for both root and /src package layouts."""

    package_parent = package_root.parent

    if package_parent.name == "src":
        return package_parent.parent

    return package_parent


PROJECT_ROOT = _resolve_project_root(PACKAGE_ROOT)

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EXAMPLES_DATA_DIR = DATA_DIR / "examples"

CONFIG_DIR = PROJECT_ROOT / "config"
METRICS_CONFIG_PATH = CONFIG_DIR / "metrics.yaml"
SCORING_CONFIG_PATH = CONFIG_DIR / "scoring_profiles.yaml"
