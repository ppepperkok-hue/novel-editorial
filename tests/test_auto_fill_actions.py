import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_editorial import db  # noqa: E402
from novel_editorial.services import activity  # noqa: E402
from tools import auto_fill_actions  # noqa: E402


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class AutoFillActionsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.path = os.path.join(tmp, "t.db")
        self.conn = db.connect(self.path)
        cur = self.conn.execute(
            "INSERT INTO novels(title,genre,premise,status) VALUES('测试书','都市','测试','publishing')"
        )
        self.novel_id = cur.lastrowid
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _add_chapter(self, status="published"):
        cur = self.conn.execute(
            "INSERT INTO chapters(novel_id,seq,outline,status,title,published_at) "
            "VALUES(?,?,?,?,?,?)",
            (self.novel_id, 1, "大纲", status, "第一章 开头", _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def _add_action(self, task, novel_id=None):
        r = activity.create_action(
            self.conn,
            "guard",
            task,
            novel_id=novel_id if novel_id is not None else self.novel_id,
        )
        return r["id"]

    def test_rules_fill_publish_action(self):
        cid = self._add_chapter()
        self.conn.execute(
            "INSERT INTO publish_logs(chapter_id,platform,action,result,created_at) "
            "VALUES(?,?,?,?,?)",
            (cid, "fanqie", "publish_article", "success", _now()),
        )
        self.conn.commit()
        aid = self._add_action("把今天的两章发布到番茄")
        res = auto_fill_actions.run(self.path, novel_id=self.novel_id, use_llm=False)
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["done"]), 1)
        self.assertEqual(res["done"][0]["id"], aid)
        rows = activity.list_actions(self.conn, status="done")
        self.assertEqual(len(rows), 1)
        self.assertIn("发布", rows[0]["result"])

    def test_knowledge_rule_fills_setting_action(self):
        self.conn.execute(
            "INSERT INTO novel_knowledge(novel_id,category,entity,content,version,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (self.novel_id, "world_rule", "灵气", "浓度三层", 2, _now()),
        )
        self.conn.commit()
        aid = self._add_action("把新加的灵气浓度设定写进设定库")
        res = auto_fill_actions.run(self.path, novel_id=self.novel_id, use_llm=False)
        self.assertEqual([d["id"] for d in res["done"]], [aid])
        rows = activity.list_actions(self.conn, status="done")
        self.assertIn("设定知识库", rows[0]["result"])

    def test_no_evidence_keeps_pending(self):
        aid = self._add_action("给主角安排一次成长转折")
        res = auto_fill_actions.run(self.path, novel_id=self.novel_id, use_llm=False)
        self.assertEqual(res["done"], [])
        self.assertEqual([k["id"] for k in res["kept_pending"]], [aid])
        self.assertEqual(
            activity.list_actions(self.conn, status="pending")[0]["id"], aid
        )

    def test_llm_decision_updates_with_result(self):
        self._add_chapter()
        aid = self._add_action("发布第一章")
        payload = {
            "text": json.dumps(
                [{"id": aid, "status": "done", "result": "今日第 1 章已上线"}],
                ensure_ascii=False,
            ),
            "usage": {},
            "model": "mock",
        }
        with mock.patch(
            "tools.auto_fill_actions.chat_deepseek", return_value=payload
        ) as chat:
            res = auto_fill_actions.run(self.path, novel_id=self.novel_id)
        self.assertEqual(res["method"], "llm")
        self.assertEqual(len(res["done"]), 1)
        chat.assert_called_once()
        rows = activity.list_actions(self.conn, status="done")
        self.assertEqual(rows[0]["result"], "今日第 1 章已上线")

    def test_llm_failure_falls_back_to_rules(self):
        self._add_chapter()
        aid = self._add_action("发布本章")
        with mock.patch(
            "tools.auto_fill_actions.chat_deepseek",
            side_effect=RuntimeError("api down"),
        ):
            res = auto_fill_actions.run(self.path, novel_id=self.novel_id)
        self.assertEqual(res["method"], "rules")
        self.assertEqual([d["id"] for d in res["done"]], [aid])

    def test_llm_garbage_falls_back_to_rules(self):
        self._add_chapter()
        self._add_action("发布本章")
        with mock.patch(
            "tools.auto_fill_actions.chat_deepseek",
            return_value={"text": "不是 JSON", "usage": {}, "model": "mock"},
        ):
            res = auto_fill_actions.run(self.path, novel_id=self.novel_id)
        self.assertEqual(res["method"], "rules")
        self.assertEqual(len(res["done"]), 1)

    def test_dry_run_keeps_pending(self):
        self._add_chapter()
        aid = self._add_action("发布本章")
        res = auto_fill_actions.run(
            self.path, novel_id=self.novel_id, use_llm=False, dry_run=True
        )
        self.assertEqual(len(res["done"]), 1)
        self.assertTrue(res["dry_run"])
        self.assertEqual(
            activity.list_actions(self.conn, status="pending")[0]["id"], aid
        )

    def test_global_action_fills_too(self):
        self._add_chapter()
        aid = self._add_action("发布本章", novel_id=0)
        res = auto_fill_actions.run(self.path, novel_id=self.novel_id, use_llm=False)
        self.assertEqual([d["id"] for d in res["done"]], [aid])

    def test_no_pending_returns_zero(self):
        res = auto_fill_actions.run(self.path, novel_id=self.novel_id, use_llm=False)
        self.assertEqual(res["checked"], 0)
        self.assertEqual(res["method"], "none")


if __name__ == "__main__":
    unittest.main()
