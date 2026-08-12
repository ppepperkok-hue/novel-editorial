"""运行全部测试（仅标准库，无需安装依赖）。"""

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


class EnvConfigContractTests(unittest.TestCase):
    """Guard the .env.example <-> config.py contract (R12-E-02)."""

    # Keys read outside novel_editorial/config.py: key -> (file, evidence).
    # Evidence is the literal string that must occur in the file; dynamic
    # keys (LLM_MODEL_*) use the prefix built by the consumer.
    EXTERNAL_CONSUMERS = {
        "LLM_API_KEY": ("novel_editorial/llm_client.py", "LLM_API_KEY"),
        "LLM_BASE_URL": ("novel_editorial/llm_client.py", "LLM_BASE_URL"),
        "LLM_MODEL_PLANNING": ("novel_editorial/llm_client.py", "LLM_MODEL_"),
        "LLM_MODEL_WRITING": ("novel_editorial/llm_client.py", "LLM_MODEL_"),
        "LLM_MODEL_EDITING": ("novel_editorial/llm_client.py", "LLM_MODEL_"),
        "LLM_MODEL_REVIEWING": ("novel_editorial/llm_client.py", "LLM_MODEL_"),
        "LLM_MODEL_MEMORY": ("novel_editorial/llm_client.py", "LLM_MODEL_"),
        "DEEPSEEK_API_KEY": ("novel_editorial/llm_client.py", "DEEPSEEK_API_KEY"),
        "TOMATO_COOKIE": ("novel_editorial/monitor.py", "TOMATO_COOKIE"),
        "TOMATO_CSRF_TOKEN": ("novel_editorial/monitor.py", "TOMATO_CSRF_TOKEN"),
        "FANQIE_COOKIE": ("tools/publish_stock.py", "FANQIE_COOKIE"),
        "FANQIE_CSRF_TOKEN": ("tools/publish_stock.py", "FANQIE_CSRF_TOKEN"),
        "FANQIE_BOOK_ID": ("tools/publish_stock.py", "FANQIE_BOOK_ID"),
        "MEETING_HEARTBEAT_TIMEOUT_MINUTES": (
            "novel_editorial/services/meeting_session.py",
            "MEETING_HEARTBEAT_TIMEOUT_MINUTES",
        ),
        "N8N_EMAIL": ("tools/n8n_api.py", "N8N_EMAIL"),
        "N8N_TMP_PW": ("tools/n8n_api.py", "N8N_TMP_PW"),
        "N8N_API_KEY": ("novel_editorial/services/n8n.py", "N8N_API_KEY"),
        "N8N_WORKFLOW_TRIGGER": ("tools/n8n_api.py", "N8N_WORKFLOW_TRIGGER"),
        "PANEL_TOKEN": ("novel_editorial/web_api.py", "PANEL_TOKEN"),
        "PYTHON_EXE": ("scripts/install_daily_task.ps1", "PYTHON_EXE"),
        "PYTHONW_EXE": ("scripts/install_daily_task.ps1", "PYTHONW_EXE"),
        "PIPELINE_ROOT": ("tools/validate_workflow_deep.mjs", "PIPELINE_ROOT"),
        "NOVEL_PREMISE": ("n8n/novel_workflow.json", "NOVEL_PREMISE"),
        "NOVEL_KEYWORDS": ("n8n/novel_workflow.json", "NOVEL_KEYWORDS"),
        "NOVEL_GENRE": ("n8n/novel_workflow.json", "NOVEL_GENRE"),
        "COST_PRO_PER_1K": ("novel_editorial/llm_client.py", "COST_PRO_PER_1K"),
        "COST_FLASH_PER_1K": ("novel_editorial/llm_client.py", "COST_FLASH_PER_1K"),
        "CHROME_EXE": ("tools/launch_headless_chrome.ps1", "CHROME_EXE"),
    }

    @staticmethod
    def _env_example_entries():
        entries = {}
        for raw in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip():
                entries[key.strip()] = value.strip()
        return entries

    @staticmethod
    def _config_consumed_keys():
        tree = ast.parse(
            (ROOT / "novel_editorial" / "config.py").read_text(encoding="utf-8")
        )
        consumed = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            is_os_get = (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and isinstance(func.value, ast.Attribute)
                and func.value.attr == "environ"
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "os"
            )
            is_env_int = isinstance(func, ast.Name) and func.id == "_env_int"
            if not (is_os_get or is_env_int):
                continue
            key_node = node.args[0]
            if not isinstance(key_node, ast.Constant) or not isinstance(
                key_node.value, str
            ):
                continue
            default = None
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                default = node.args[1].value
            consumed[key_node.value] = default
        return consumed

    def test_env_example_keys_are_all_consumed(self):
        entries = self._env_example_entries()
        consumed = self._config_consumed_keys()
        actual = set(entries)
        expected = set(consumed) | set(self.EXTERNAL_CONSUMERS)
        self.assertEqual(
            len(entries),
            len(actual),
            "duplicate KEY= lines in .env.example",
        )
        self.assertEqual(
            actual,
            expected,
            "env contract drift: every .env.example key must be consumed by "
            "config.py or registered in EXTERNAL_CONSUMERS, and every "
            "registered/config key must stay in .env.example",
        )
        for key, (rel, evidence) in self.EXTERNAL_CONSUMERS.items():
            self.assertIn(
                evidence,
                (ROOT / rel).read_text(encoding="utf-8"),
                f"consumer file for {key} no longer references it",
            )

    def test_config_defaults_match_env_example(self):
        entries = self._env_example_entries()
        mismatches = []
        for key, default in self._config_consumed_keys().items():
            if default is None or key not in entries:
                continue
            if str(default) != entries[key]:
                mismatches.append(f"{key}: config={default!r} example={entries[key]!r}")
        self.assertEqual(mismatches, [])


loader = unittest.TestLoader()
suite = unittest.TestSuite([
    loader.discover(str(ROOT / "tests"), pattern="test_*.py"),
    loader.discover(str(ROOT / "tests"), pattern="*_test.py"),
])
# R12-E-02: the .env.example <-> config.py contract guard lives in this file so
# a broken env contract fails the standard `python run_tests.py` run too.
suite.addTests(loader.loadTestsFromTestCase(EnvConfigContractTests))
if suite.countTestCases() == 0:
    print("ERROR: no tests discovered under tests/ (fake green guard)", file=sys.stderr)
    sys.exit(1)
result = unittest.TextTestRunner(verbosity=2, buffer=True).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
