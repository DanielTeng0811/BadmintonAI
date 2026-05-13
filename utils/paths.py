"""
Centralized filesystem paths for BadmintonAI.
"""
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
METADATA_DIR = DATA_DIR / "metadata"

RAW_DATA_CSV = RAW_DATA_DIR / "all_dataset.csv"
PROCESSED_CSV = PROCESSED_DATA_DIR / "processed_new_3.csv"
PROCESSED_DB = PROCESSED_DATA_DIR / "processed_new_3.db"
COLUMN_DEFINITION_FILE = METADATA_DIR / "column_definition.json"
COURT_PLACE_FILE = METADATA_DIR / "court_place.txt"

LOG_DIR = PROJECT_ROOT / "logs"
LLM_DEBUG_LOG = LOG_DIR / "llm_debug_log.txt"

NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
EVALUATION_DIR = PROJECT_ROOT / "evaluation"
EVALUATION_QUESTIONS_FILE = EVALUATION_DIR / "questions" / "test_question_modified.json"


def ensure_runtime_dirs():
    """Create directories that are written at runtime."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
