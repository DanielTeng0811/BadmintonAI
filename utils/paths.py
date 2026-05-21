"""
Centralized project paths for BadmintonAI.
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

DOCS_DIR = PROJECT_ROOT / "docs"
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
EVALUATION_DIR = PROJECT_ROOT / "evaluation"
EVALUATION_QUESTIONS_DIR = EVALUATION_DIR / "questions"
EVALUATION_QUESTIONS_FILE = EVALUATION_QUESTIONS_DIR / "test_question_modified.json"

LOG_DIR = PROJECT_ROOT / "logs"
LLM_DEBUG_LOG = LOG_DIR / "llm_debug_log.txt"


def ensure_runtime_dirs():
    """Create writable runtime directories used by the app."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
