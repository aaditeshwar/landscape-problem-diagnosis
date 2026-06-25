import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
METADATA_DIR = ROOT / "metadata"
load_dotenv(ROOT / ".env")

LOG_DIR = os.getenv("LOG_DIR", str(ROOT / "logs"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/?directConnection=true")
DB_NAME = os.getenv("MONGO_DB", "diagnosis_db")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_REASON_MODEL = os.getenv("OLLAMA_REASON_MODEL", "qwen2.5:14b")
OLLAMA_FOLLOWUP_MODEL = os.getenv("OLLAMA_FOLLOWUP_MODEL", "llama3.1:8b")
OLLAMA_CHAT_TIMEOUT = float(os.getenv("OLLAMA_CHAT_TIMEOUT", "600"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "8192"))
EMBED_CHAR_LIMIT = int(os.getenv("OLLAMA_EMBED_CHAR_LIMIT", "6000"))

# Diagnosis LLM: ollama (local) or anthropic (Claude API)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
_ANTHROPIC_DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
ANTHROPIC_MODEL = _ANTHROPIC_DEFAULT_MODEL
ANTHROPIC_REASON_MODEL = os.getenv("ANTHROPIC_REASON_MODEL", _ANTHROPIC_DEFAULT_MODEL)
ANTHROPIC_FOLLOWUP_MODEL = os.getenv("ANTHROPIC_FOLLOWUP_MODEL", _ANTHROPIC_DEFAULT_MODEL)
ANTHROPIC_MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "8192"))
ANTHROPIC_REVIEWER_MAX_TOKENS = int(os.getenv("ANTHROPIC_REVIEWER_MAX_TOKENS", "16384"))
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    if o.strip()
]

# Context cluster raster (signal editor) — see .env.example
CLUSTER_COG_URL = os.getenv("CLUSTER_COG_URL", "").strip()
CLUSTER_COG_VIEWER_URL = os.getenv("CLUSTER_COG_VIEWER_URL", "").strip()

_allowed_reviewers_raw = os.getenv("ALLOWED_REVIEWERS", "ALL").strip()
ALLOWED_REVIEWERS_ALL = not _allowed_reviewers_raw or _allowed_reviewers_raw.upper() == "ALL"
ALLOWED_REVIEWERS = (
    []
    if ALLOWED_REVIEWERS_ALL
    else [name.strip() for name in _allowed_reviewers_raw.split(",") if name.strip()]
)
