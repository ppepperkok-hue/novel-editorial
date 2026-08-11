"""S11 tests: review rejection -> writer reply -> rewrite -> re-review."""

import json
import os
import tempfile
import unittest
from unittest import mock

from novel_pipeline import db
from tools import editorial_daily, mailroom

LONG = "他推开门走进院子，风从巷口吹来，远处传来吆喝声。" * 100


class ReviewRetryTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.conn = db.connect(self.db_path)
        self.ctx = editorial_daily._Ctx(1, self.db_path, dry_run=False)
        self.outline = {
            "premise": "p",
            "genre": "都市",
            "title": "书",
            "keywords": "k",
            "bible": {},
            "chapter1": {"title": "第一章", "outline": "o"},
            "chapter2": {"title": "第二章", "outline": "o"},
        }
        self.guard = {"constraints": [], "character_beats": {}}
        self.meta = {"protagonist": "林舟", "start_num": 1}
        self.chapter = self.outline["chapter1"]

    def tearDown(self):
        self.conn.close()

    def _failed_gate(self):
        return {
            "passed": False,
            "errors": ["审稿未过"],
            "review": {"passed": False, "issues": ["逻辑承接生硬"]},
            "reader": None,
            "editor": None,
        }

    def test_retry_passes_and_sends_messages(self):
        calls = []

        def fake_agent(ctx, node, task, target_words=None):
            calls.append(node)
            if node == "写手A":
                if task.startswith("审稿打回"):
                    return json.dumps({"intent": "重写承接", "plan": "补过渡段落"})
                return LONG
            if node == "润色A":
                return LONG
            if node == "审稿A":
                return json.dumps({"passed": True, "issues": []})
            return json.dumps({})

        with mock.patch("tools.editorial_daily._agent", side_effect=fake_agent):
            gate, editor_text, review_text = editorial_daily._review_retry(
                self.ctx, self.conn, 0, self.outline, self.guard, self.meta,
                2000, None, "A", self.chapter, LONG, self._failed_gate(), "{}",
            )
        self.assertTrue(gate["passed"])
        self.assertEqual(editor_text, LONG)
        # reviewer -> writer rejection + writer -> reviewer reply
        all_msgs = mailroom.list_messages(self.conn, agent="writer")["messages"]
        self.assertEqual(len(all_msgs), 2)
        self.assertEqual(
            [m["subject"] for m in all_msgs].count("审稿打回"), 1
        )
        self.assertEqual(
            [m["subject"] for m in all_msgs].count("返工说明"), 1
        )

    def test_retry_exhausts_and_keeps_original_gate(self):
        calls = []

        def fake_agent(ctx, node, task, target_words=None):
            calls.append(node)
            if node == "写手A":
                return json.dumps({"intent": "改", "plan": "改"}) if task.startswith("审稿打回") else LONG
            if node == "润色A":
                return LONG
            if node == "审稿A":
                return json.dumps({"passed": False, "issues": ["还是不行"]})
            return json.dumps({})

        with mock.patch("tools.editorial_daily._agent", side_effect=fake_agent):
            gate, editor_text, _review = editorial_daily._review_retry(
                self.ctx, self.conn, 0, self.outline, self.guard, self.meta,
                2000, None, "A", self.chapter, LONG, self._failed_gate(), "{}",
            )
        self.assertFalse(gate["passed"])
        self.assertEqual(editor_text, LONG)

    def test_retry_disabled_returns_unchanged(self):
        with mock.patch("tools.editorial_daily.config.REVIEW_RETRY_MAX", 0):
            with mock.patch(
                "tools.editorial_daily._agent",
                side_effect=AssertionError("retry must be disabled"),
            ):
                gate, editor_text, review_text = editorial_daily._review_retry(
                    self.ctx, self.conn, 0, self.outline, self.guard, self.meta,
                    2000, None, "A", self.chapter, LONG, self._failed_gate(), "{}",
                )
        self.assertFalse(gate["passed"])
        self.assertEqual(editor_text, LONG)
        self.assertEqual(mailroom.list_messages(self.conn, agent="writer")["messages"], [])

    def test_compliance_block_never_rewrites(self):
        gate = {
            "passed": False,
            "errors": ["合规拦截：冰毒"],
            "review": None,
            "reader": None,
            "editor": None,
        }
        with mock.patch(
            "tools.editorial_daily._agent",
            side_effect=AssertionError("compliance block must not rewrite"),
        ):
            new_gate, editor_text, _review = editorial_daily._review_retry(
                self.ctx, self.conn, 0, self.outline, self.guard, self.meta,
                2000, None, "A", self.chapter, LONG, gate, "{}",
            )
        self.assertIs(new_gate, gate)
        self.assertEqual(editor_text, LONG)

    def test_dry_run_sends_no_messages(self):
        ctx = editorial_daily._Ctx(1, self.db_path, dry_run=True)

        def fake_agent(c, node, task, target_words=None):
            if node == "写手A" and task.startswith("审稿打回"):
                return json.dumps({"intent": "改", "plan": "改"})
            if node == "审稿A":
                return json.dumps({"passed": True, "issues": []})
            return LONG

        with mock.patch("tools.editorial_daily._agent", side_effect=fake_agent):
            gate, _editor, _review = editorial_daily._review_retry(
                ctx, self.conn, 0, self.outline, self.guard, self.meta,
                2000, None, "A", self.chapter, LONG, self._failed_gate(), "{}",
            )
        self.assertTrue(gate["passed"])
        self.assertEqual(mailroom.list_messages(self.conn, agent="writer")["messages"], [])


if __name__ == "__main__":
    unittest.main()
