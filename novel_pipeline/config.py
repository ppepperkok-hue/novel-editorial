"""Central configuration: paths, env loading, and pipeline constants."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

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
N8N_WORKFLOW_DAILY = os.environ.get("N8N_WORKFLOW_DAILY", "SkLUnm3uRyBSY84F")
N8N_WORKFLOW_WEEKLY = os.environ.get("N8N_WORKFLOW_WEEKLY", "TAScPjj0Oqtz1uy7")
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
]


def load_env():
    """Load ~/.n8n/.env into a dict (without mutating os.environ), merged
    with already-set process environment variables."""
    env = {}
    if N8N_ENV_FILE.exists():
        for line in N8N_ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k, v in os.environ.items():
        env.setdefault(k, v)
    return env


def env_value(key, default=""):
    return load_env().get(key, default)
