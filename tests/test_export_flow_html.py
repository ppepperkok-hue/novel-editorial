import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novel_pipeline import db
from tools import export_flow_html


class ExportFlowHtmlTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.conn = db.connect(self.db_path)
        self.conn.execute(
            "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,started_at,"
            "finished_at,failed_nodes,error,published,detail,created_at) "
            "VALUES('r1',1,'manual','scheduler','completed','2026-08-11 10:00:00',"
            "'2026-08-11 10:01:00','[]','',2,'{}','2026-08-11 10:00:00')"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_render_is_self_contained(self):
        html = export_flow_html.render_html(self.conn)
        self.assertIn("<!doctype html>", html.lower())
        self.assertIn("Planner 出大纲", html)
        self.assertIn("上次成功", html)
        # SVG namespace is the only allowed "http://" occurrence; no external
        # script/style/resource references may exist.
        self.assertNotIn("https://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("<script src", html)
        self.assertNotIn("<link ", html)
        self.assertNotIn("url(http", html)
        self.assertNotIn("</script>", html.split("flow-data")[0])

    def test_render_escapes_payload(self):
        html = export_flow_html.render_html(self.conn)
        self.assertIn('id="flow-data"', html)
        self.assertIn("application/json", html)

    def test_error_content_is_html_escaped(self):
        self.conn.execute(
            "UPDATE daily_runs SET error='<script>alert(1)</script> & <b>boom</b>' "
            "WHERE run_id='r1'"
        )
        self.conn.commit()
        doc = export_flow_html.render_html(self.conn)
        self.assertIn("&lt;script&gt;", doc)
        self.assertIn("&lt;b&gt;", doc)
        self.assertNotIn("alert(1)</script>", doc)

    def test_cli_writes_file(self):
        out = os.path.join(self.tmpdir, "report.html")
        import sys

        with mock.patch.object(
            sys,
            "argv",
            ["export_flow_html", "--db", self.db_path, "--out", out],
        ):
            with mock.patch("builtins.print") as print_mock:
                export_flow_html.main()
        self.assertTrue(Path(out).exists())
        text = Path(out).read_text(encoding="utf-8")
        self.assertIn("日更链路报告", text)
        payload = json.loads(print_mock.call_args[0][0])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["file"], out)


if __name__ == "__main__":
    unittest.main()
