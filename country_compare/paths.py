from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EXAMPLES_DATA_DIR = DATA_DIR / "examples"

CONFIG_DIR = PROJECT_ROOT / "config"
METRICS_CONFIG_PATH = CONFIG_DIR / "metrics.yaml"
SCORING_CONFIG_PATH = CONFIG_DIR / "scoring.yaml"
