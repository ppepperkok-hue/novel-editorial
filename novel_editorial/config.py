"""Central configuration: paths, env loading, and pipeline constants."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env_int(key, default):
    try:
        return int(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default

AGENTS_DIR = ROOT / "prompts" / "agents"
N8N_DIR = ROOT / "n8n"
TOOLS_DIR = ROOT / "tools"
TMP_DIR = ROOT / "n8n_tmp"
EXPORTS_DIR = ROOT / "exports"
DATA_DIR = ROOT / "demo_data"

WORKFLOW_JSON = N8N_DIR / "novel_workflow.json"
WEEKLY_WORKFLOW_JSON = N8N_DIR / "architect_weekly.json"
VALIDATE_JS = TOOLS_DIR / "validate_workflow_deep.mjs"
ALERTS_LOG = ROOT / "alerts.log"
HOT_TOPICS_JSON = ROOT / "hot_topics.json"
READER_CSV = DATA_DIR / "reader_stats.csv"
DB_PATH = ROOT / "demo.db"

N8N_BASE = os.environ.get("N8N_BASE", "http://127.0.0.1:5678")
N8N_WORKFLOW_DAILY = os.environ.get("N8N_WORKFLOW_DAILY", "your-daily-workflow-id")
N8N_WORKFLOW_WEEKLY = os.environ.get("N8N_WORKFLOW_WEEKLY", "your-weekly-workflow-id")
N8N_WORKFLOW_KEEPER = os.environ.get("N8N_WORKFLOW_KEEPER", "your-keeper-workflow-id")
N8N_ENV_FILE = Path.home() / ".n8n" / ".env"

AGENT_NAMES = [
    "planner",
    "guard",
    "writer",
    "editor",
    "reviewer",
    "reader",
    "memory",
    "work_meta",
    "eic",
    "ending_judge",
    "knowledge_keeper",
]

# Editorial context injection (S3): how much collaboration context each LLM
# call carries. Truncation bounds the token overhead; see the master plan.
AGENT_CTX_MESSAGES = _env_int("AGENT_CTX_MESSAGES", 8)
AGENT_CTX_MEMORIES = _env_int("AGENT_CTX_MEMORIES", 3)
AGENT_CTX_RELATIONS = _env_int("AGENT_CTX_RELATIONS", 3)
AGENT_CTX_PROMISES = _env_int("AGENT_CTX_PROMISES", 3)
AGENT_CTX_ACTIONS = _env_int("AGENT_CTX_ACTIONS", 3)
AGENT_CTX_TRUNCATE = _env_int("AGENT_CTX_TRUNCATE", 200)
DISPATCH_MODE = os.environ.get("DISPATCH_MODE", "editorial")
REVIEW_RETRY_MAX = _env_int("REVIEW_RETRY_MAX", 1)
MEETING_MODE = os.environ.get("MEETING_MODE", "rounds")
CLAIM_INJECT = os.environ.get("CLAIM_INJECT", "on") != "off"
TOPIC_REQUEST_ACTIONS = os.environ.get("TOPIC_REQUEST_ACTIONS", "on") != "off"
TASK_RESPONSE_MODE = os.environ.get("TASK_RESPONSE_MODE", "on")
RELATION_WEIGHT = os.environ.get("RELATION_WEIGHT", "on") != "off"
AGENCY_ENABLED = os.environ.get("AGENCY_ENABLED", "on") != "off"
REWORK_MAX = _env_int("REWORK_MAX", 1)
MEMORY_CATEGORY_MAP = {
    "writer": ("plot", "character", "feedback", "opinion"),
    "reviewer": ("feedback", "quality", "collaboration"),
    "reader": ("feedback", "quality"),
    "eic": ("meeting", "decision", "collaboration"),
    "planner": ("plot", "character", "decision"),
    "guard": ("world", "character", "feedback"),
    "editor": ("feedback", "quality"),
    "memory": (),
    "work_meta": (),
    "ending_judge": ("plot", "character"),
    "knowledge_keeper": (),
}


def _strip_inline_comment(value):
    """Cut a trailing ``#`` comment that follows whitespace.

    A ``#`` glued to the value (token/URL) is kept, so ``a=b#c`` stays
    ``b#c`` while ``a=b # c`` becomes ``b``.
    """
    cut = len(value)
    for sep in (" #", "\t#"):
        idx = value.find(sep)
        if idx != -1:
            cut = min(cut, idx)
    return value[:cut].strip() if cut < len(value) else value.strip()


def load_env():
    """Load ~/.n8n/.env into a dict (without mutating os.environ), merged
    with already-set process environment variables."""
    # Process environment wins; ~/.n8n/.env only fills missing keys.
    # This matches preflight.load_env and keeps explicit env overrides usable.
    env = dict(os.environ)
    if N8N_ENV_FILE.exists():
        for line in N8N_ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), _strip_inline_comment(v))
    return env


def env_value(key, default=""):
    return load_env().get(key, default)
