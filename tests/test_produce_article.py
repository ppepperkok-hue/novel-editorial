"""Tests for the generic article producer (tools/produce_article.py)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novel_editorial import db
from tools import app_settings, produce_article, producers


class ProduceArticleTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.conn = db.connect(self.db_path)
        self.old_out = app_settings.get_str(self.conn, "article_output_dir", "")
        self.out_dir = os.path.join(self.tmpdir, "articles")

    def tearDown(self):
        self.conn.close()

    def _run(self, dry_run=False, boss_instruction="测试主题：AI 写作的未来"):
        return produce_article.produce_article(
            self.conn,
            target=500,
            trigger="manual",
            dry_run=dry_run,
            db_path=self.db_path,
            workday_run_id="workday-test-article",
            lock_held=True,
            boss_instruction=boss_instruction,
            plan={"focus": "按主题写作"},
        )

    def test_dry_run_returns_placeholder_without_files(self):
        r = self._run(dry_run=True)
        self.assertTrue(r["ok"])
        self.assertTrue(r["dry_run"])
        self.assertEqual(r["published"], 0)
        self.assertEqual(r["files"], [])
        self.assertEqual(r["steps"][0]["step"], "plan")
        self.assertEqual(len(r["steps"]), 4)

    def test_real_chain_writes_markdown(self):
        def fake_run(agent, task, **kwargs):
            if agent == "planner":
                text = json.dumps(
                    {"title": "测试文章", "angle": "角度",
                     "structure": ["开场", "主体"], "key_points": []},
                    ensure_ascii=False,
                )
            elif agent == "reviewer":
                text = json.dumps(
                    {"passed": True, "issues": [], "suggestions": []},
                    ensure_ascii=False,
                )
            else:
                text = f"{agent} 输出的正文内容。"
            return {"ok": True, "text": text, "used_knowledge": [], "attempts": 1}

        app_settings.set_many(self.conn, {"article_output_dir": self.out_dir})
        with mock.patch("tools.agent_tool_loop.run", side_effect=fake_run):
            r = self._run(dry_run=False)
        self.assertTrue(r["ok"])
        self.assertEqual(r["published"], 1)
        self.assertEqual(len(r["files"]), 1)
        path = Path(r["files"][0])
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")
        self.assertIn("测试文章", content)
        self.assertIn("正文内容", content)

    def test_write_failure_does_not_save_file(self):
        calls = {"n": 0}

        def fake_run(agent, task, **kwargs):
            calls["n"] += 1
            if agent == "writer":
                return {"ok": False, "text": "", "error": "mock writer error",
                        "used_knowledge": [], "attempts": 1}
            return {"ok": True, "text": "占位", "used_knowledge": [], "attempts": 1}

        app_settings.set_many(self.conn, {"article_output_dir": self.out_dir})
        with mock.patch("tools.agent_tool_loop.run", side_effect=fake_run):
            r = self._run(dry_run=False)
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], "failed")
        self.assertEqual(r["files"], [])
        self.assertIn("mock writer error", r["error"])
        self.assertEqual(r["steps"][1]["step"], "write")
        self.assertIn("mock writer error", r["steps"][1]["error"])
        self.assertFalse(os.path.exists(self.out_dir) and os.listdir(self.out_dir))

    def test_slug_sanitizes_dangerous_chars(self):
        self.assertEqual(produce_article._slug("../evil/名字"), "evil-名字")
        self.assertEqual(produce_article._slug("   "), "article")

    def test_producer_registry_has_article(self):
        self.assertIn("article", producers.PRODUCERS)
        self.assertIn("novel", producers.PRODUCERS)
        self.assertIn("none", producers.PRODUCERS)


class WorkdayProducerSwitchTests(unittest.TestCase):
    def test_workday_plan_uses_configured_producer(self):
        from tools import workday

        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "t.db")
        conn = db.connect(db_path)
        try:
            app_settings.set_many(conn, {"workday_producer": "article"})
            r = workday.open(
                conn, trigger="manual", mode="write",
                dry_run=True, db_path=db_path,
            )
            self.assertTrue(r["ok"])
            self.assertEqual(r["plan"]["producer"], "article")

            app_settings.set_many(conn, {"workday_producer": ""})
            r2 = workday.open(
                conn, trigger="manual", mode="write",
                dry_run=True, db_path=db_path,
            )
            self.assertTrue(r2["ok"])
            self.assertEqual(r2["plan"]["producer"], "novel")
        finally:
            conn.close()
