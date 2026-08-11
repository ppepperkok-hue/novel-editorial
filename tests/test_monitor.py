import os
import tempfile
import unittest
import unittest.mock

from novel_pipeline import db, monitor


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "test.db"))

    def test_issues_empty_when_healthy(self):
        env = {"TOMATO_COOKIE": "c", "TOMATO_CSRF_TOKEN": "t"}
        issues = monitor.run_checks(self.conn, env=env, monthly_budget=100, spent=20)
        self.assertEqual(issues, [])

    @unittest.mock.patch("novel_pipeline.monitor._load_n8n_env", return_value={})
    def test_detects_missing_cookie_and_budget_overrun(self, _mock_env):
        issues = monitor.run_checks(self.conn, env={}, monthly_budget=100, spent=150)
        self.assertTrue(any("Cookie" in i for i in issues))
        self.assertTrue(any("成本超限" in i for i in issues))

    def test_detects_failed_publish_logs(self):
        nid = db.add_novel(self.conn, "测试书", "都市", "简介")
        vid = db.add_volume(self.conn, nid, 1, "第一卷")
        cid = db.add_chapter(self.conn, nid, vid, 1, "第1章")
        db.add_publish_log(self.conn, cid, "fanqie", "publish", "failed", error="boom")
        issues = monitor.run_checks(
            self.conn, env={"TOMATO_COOKIE": "c", "TOMATO_CSRF_TOKEN": "t"}
        )
        self.assertTrue(any("发布失败" in i for i in issues))

    def test_planning_and_finished_books_do_not_warn(self):
        env = {"TOMATO_COOKIE": "c", "TOMATO_CSRF_TOKEN": "t"}
        nid = db.add_novel(self.conn, "规划书", "都市", "简介")
        self.conn.execute("UPDATE novels SET status='planning' WHERE id=?", (nid,))
        nid2 = db.add_novel(self.conn, "完结书", "都市", "简介")
        self.conn.execute("UPDATE novels SET status='finished' WHERE id=?", (nid2,))
        self.conn.commit()
        issues = monitor.run_checks(self.conn, env=env, monthly_budget=100, spent=20)
        self.assertFalse(any("断更预警" in i for i in issues))

    def test_publishing_book_with_empty_stock_warns(self):
        env = {"TOMATO_COOKIE": "c", "TOMATO_CSRF_TOKEN": "t"}
        nid = db.add_novel(self.conn, "连载书", "都市", "简介")
        self.conn.execute(
            "UPDATE novels SET status='publishing' WHERE id=?", (nid,)
        )
        self.conn.commit()
        issues = monitor.run_checks(self.conn, env=env, monthly_budget=100, spent=20)
        self.assertTrue(any("断更预警" in i for i in issues))


if __name__ == "__main__":
    unittest.main()
