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

if __name__ == "__main__":
    unittest.main()
