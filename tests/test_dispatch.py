"""S10 tests: chief-editor dispatch (fixed default, editorial advisory)."""

import json
import os
import tempfile
import unittest
from unittest import mock

from novel_pipeline import db
from tools import editorial_daily, mailroom


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.conn = db.connect(self.db_path)
        self.ctx = editorial_daily._Ctx(1, self.db_path, dry_run=False)
        self.stock = {"stock": 0, "target": 2, "need": 2}

    def tearDown(self):
        self.conn.close()

    def _dispatch_json(self):
        return json.dumps(
            {
                "chapters": 2,
                "focus": "强化章末钩子",
                "assignments": [
                    {"agent": "writer", "task": "写今天两章", "note": "钩子要够"},
                    {"agent": "reviewer", "task": "重点查逻辑承接", "note": ""},
                ],
            },
            ensure_ascii=False,
        )

    def test_fixed_mode_is_noop(self):
        with mock.patch("tools.editorial_daily.config.DISPATCH_MODE", "fixed"):
            with mock.patch(
                "tools.editorial_daily._agent",
                side_effect=AssertionError("fixed mode must not call the editor"),
            ):
                result = editorial_daily._dispatch(self.ctx, self.conn, self.stock)
        self.assertEqual(result["mode"], "fixed")
        self.assertIsNone(result["dispatch"])

    def test_editorial_broadcasts_assignments(self):
        with mock.patch("tools.editorial_daily.config.DISPATCH_MODE", "editorial"):
            with mock.patch(
                "tools.editorial_daily._agent", return_value=self._dispatch_json()
            ):
                result = editorial_daily._dispatch(self.ctx, self.conn, self.stock)
        self.assertEqual(result["mode"], "editorial")
        self.assertFalse(result["degraded"])
        self.assertEqual(result["dispatch"]["chapters"], 2)
        writer_msgs = mailroom.list_messages(self.conn, agent="writer")["messages"]
        self.assertEqual(len(writer_msgs), 1)
        self.assertEqual(writer_msgs[0]["from_agent"], "eic")
        self.assertIn("写今天两章", writer_msgs[0]["body"])
        self.assertEqual(self.ctx.warnings, [])

    def test_editorial_degrades_on_agent_failure(self):
        with mock.patch("tools.editorial_daily.config.DISPATCH_MODE", "editorial"):
            with mock.patch("tools.editorial_daily._agent", return_value=None):
                result = editorial_daily._dispatch(self.ctx, self.conn, self.stock)
        self.assertTrue(result["degraded"])
        self.assertTrue(any("分派失败" in w for w in self.ctx.warnings))
        self.assertEqual(mailroom.list_messages(self.conn, agent="writer")["messages"], [])

    def test_editorial_degrades_on_unparseable_output(self):
        with mock.patch("tools.editorial_daily.config.DISPATCH_MODE", "editorial"):
            with mock.patch("tools.editorial_daily._agent", return_value="不是 JSON"):
                result = editorial_daily._dispatch(self.ctx, self.conn, self.stock)
        self.assertTrue(result["degraded"])
        self.assertTrue(any("不可解析" in w for w in self.ctx.warnings))

    def test_dry_run_skips_broadcast_but_keeps_dispatch(self):
        ctx = editorial_daily._Ctx(1, self.db_path, dry_run=True)
        with mock.patch("tools.editorial_daily.config.DISPATCH_MODE", "editorial"):
            with mock.patch(
                "tools.editorial_daily._agent", return_value=self._dispatch_json()
            ):
                result = editorial_daily._dispatch(ctx, self.conn, self.stock)
        self.assertFalse(result["degraded"])
        self.assertEqual(result["dispatch"]["chapters"], 2)
        self.assertEqual(mailroom.list_messages(self.conn, agent="writer")["messages"], [])

    def _ctx_with_dispatch(self, dispatch):
        ctx = editorial_daily._Ctx(1, self.db_path, dry_run=True)
        ctx.writing_context = "前情提要"
        ctx.dispatch = dispatch
        return ctx

    def _writer_fixture(self):
        meta = {"protagonist": "林舟"}
        outline = {
            "genre": "都市",
            "keywords": "旧书店",
            "bible": {
                "characters": [{"name": "林舟", "role": "主角"}],
                "relationships": [],
                "world_rules": ["旧书店只在夜间开门"],
            },
            "chapter1": {"title": "开篇", "emotion": "好奇", "position": "开篇"},
            "chapter2": {"title": "试探", "emotion": "紧张", "position": "推进"},
        }
        guard = {"constraints": [], "character_beats": {}}
        return meta, outline, guard

    def test_writer_task_injects_dispatch_note(self):
        dispatch = json.loads(self._dispatch_json())
        ctx = self._ctx_with_dispatch(dispatch)
        meta, outline, guard = self._writer_fixture()
        task_a = editorial_daily._writer_task(ctx, 0, meta, outline, guard, 2000)
        task_b = editorial_daily._writer_task(ctx, 1, meta, outline, guard, 2000)
        self.assertIn("主编今日分派", task_a)
        self.assertIn("写今天两章", task_a)
        self.assertIn("钩子要够", task_a)
        self.assertIn("主编今日分派", task_b)

    def test_writer_task_uses_second_assignment_for_track_b(self):
        dispatch = json.loads(self._dispatch_json())
        dispatch["assignments"] = [
            {"agent": "writer", "task": "A章主攻开篇钩子", "note": ""},
            {"agent": "writer", "task": "B章埋下伏笔", "note": ""},
        ]
        ctx = self._ctx_with_dispatch(dispatch)
        meta, outline, guard = self._writer_fixture()
        task_a = editorial_daily._writer_task(ctx, 0, meta, outline, guard, 2000)
        task_b = editorial_daily._writer_task(ctx, 1, meta, outline, guard, 2000)
        self.assertIn("A章主攻开篇钩子", task_a)
        self.assertNotIn("B章埋下伏笔", task_a)
        self.assertIn("B章埋下伏笔", task_b)

    def test_writer_task_without_dispatch_is_unchanged(self):
        ctx = self._ctx_with_dispatch(None)
        meta, outline, guard = self._writer_fixture()
        task = editorial_daily._writer_task(ctx, 0, meta, outline, guard, 2000)
        self.assertNotIn("主编今日分派", task)

    def _dispatch_for_response(self):
        return {
            "chapters": 2,
            "focus": "强化章末钩子",
            "assignments": [
                {"agent": "writer", "task": "写今天两章", "note": "钩子要够"},
                {"agent": "reviewer", "task": "重点查逻辑承接", "note": ""},
            ],
        }

    def _apply(self, response_text):
        ctx = editorial_daily._Ctx(1, self.db_path, dry_run=True)
        with mock.patch("tools.editorial_daily.config.TASK_RESPONSE_MODE", "on"):
            with mock.patch(
                "tools.editorial_daily._agent", return_value=response_text
            ):
                return editorial_daily._apply_writer_responses(
                    ctx, self.conn, self._dispatch_for_response()
                )

    def test_response_accept_keeps_assignment(self):
        result = self._apply('{"decision": "accept", "reason": "没问题"}')
        writer = [a for a in result["assignments"] if a["agent"] == "writer"][0]
        self.assertEqual(writer["task"], "写今天两章")
        self.assertEqual(writer["note"], "钩子要够")

    def test_response_counter_replaces_assignment(self):
        result = self._apply(
            '{"decision": "counter", "reason": "B章更适合埋伏笔", '
            '"alternative": "B章改写伏笔回收"}'
        )
        writer = [a for a in result["assignments"] if a["agent"] == "writer"][0]
        self.assertEqual(writer["task"], "B章改写伏笔回收")
        self.assertIn("写手提议，主编采纳", writer["note"])

    def test_response_reject_clears_assignment(self):
        result = self._apply('{"decision": "reject", "reason": "今天手感不对"}')
        writer = [a for a in result["assignments"] if a["agent"] == "writer"][0]
        self.assertEqual(writer["task"], "")
        self.assertEqual(writer["note"], "")
        ctx = editorial_daily._Ctx(1, self.db_path, dry_run=True)
        ctx.writing_context = "前情"
        ctx.dispatch = result
        meta, outline, guard = self._writer_fixture()
        task = editorial_daily._writer_task(ctx, 0, meta, outline, guard, 2000)
        self.assertNotIn("主编今日分派", task)

    def test_response_unparseable_degrades_to_accept(self):
        result = self._apply("我不是 JSON")
        writer = [a for a in result["assignments"] if a["agent"] == "writer"][0]
        self.assertEqual(writer["task"], "写今天两章")

    def test_response_mode_off_never_calls_agent(self):
        ctx = editorial_daily._Ctx(1, self.db_path, dry_run=True)
        with mock.patch("tools.editorial_daily.config.TASK_RESPONSE_MODE", "off"):
            with mock.patch(
                "tools.editorial_daily._agent",
                side_effect=AssertionError("off mode must not call agents"),
            ):
                result = editorial_daily._apply_writer_responses(
                    ctx, self.conn, self._dispatch_for_response()
                )
        self.assertEqual(result["assignments"][0]["task"], "写今天两章")

    def test_response_reject_raises_friction(self):
        ctx = editorial_daily._Ctx(1, self.db_path, dry_run=False)
        with mock.patch("tools.editorial_daily.config.TASK_RESPONSE_MODE", "on"):
            with mock.patch(
                "tools.editorial_daily._agent",
                return_value='{"decision": "reject", "reason": "手感不对"}',
            ):
                editorial_daily._apply_writer_responses(
                    ctx, self.conn, self._dispatch_for_response()
                )
        rel = self.conn.execute(
            "SELECT friction FROM agent_relations "
            "WHERE agent='writer' AND other='eic' AND novel_id=1"
        ).fetchone()
        self.assertIsNotNone(rel)
        self.assertGreater(rel["friction"], 0)

    def test_response_counter_raises_trust(self):
        ctx = editorial_daily._Ctx(1, self.db_path, dry_run=False)
        with mock.patch("tools.editorial_daily.config.TASK_RESPONSE_MODE", "on"):
            with mock.patch(
                "tools.editorial_daily._agent",
                return_value=(
                    '{"decision": "counter", "reason": "换方案", '
                    '"alternative": "B章改写伏笔回收"}'
                ),
            ):
                editorial_daily._apply_writer_responses(
                    ctx, self.conn, self._dispatch_for_response()
                )
        rel = self.conn.execute(
            "SELECT trust FROM agent_relations "
            "WHERE agent='writer' AND other='eic' AND novel_id=1"
        ).fetchone()
        self.assertIsNotNone(rel)
        self.assertGreater(rel["trust"], 0)

    def test_dispatch_input_includes_relations_snapshot(self):
        self.conn.execute(
            "INSERT INTO agent_relations(agent,other,novel_id,familiarity,trust,friction,updated_at) "
            "VALUES('writer','eic',1,0.2,0.9,0.1,datetime('now','localtime'))"
        )
        self.conn.commit()
        ctx = editorial_daily._Ctx(1, self.db_path, dry_run=False)
        captured = {}

        def fake_agent(ctx_arg, node, task, target_words=None):
            captured["task"] = task
            return json.dumps(
                {
                    "chapters": 2,
                    "focus": "f",
                    "assignments": [
                        {"agent": "writer", "task": "写今天两章", "note": ""}
                    ],
                },
                ensure_ascii=False,
            )

        with mock.patch("tools.editorial_daily.config.DISPATCH_MODE", "editorial"):
            with mock.patch("tools.editorial_daily._agent", side_effect=fake_agent):
                editorial_daily._dispatch(
                    ctx, self.conn, {"stock": 0, "target": 2, "need": 2}
                )
        self.assertIn("relations_snapshot", captured["task"])
        self.assertIn('"writer"', captured["task"])

if __name__ == "__main__":
    unittest.main()
