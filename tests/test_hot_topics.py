import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novel_pipeline.hot_topics import (
    count_keywords,
    from_csv,
    parse_rank_html,
    refresh,
    to_premise_candidates,
)

FIXTURE = """
<div class="rank-list">
  <a class="book-name" href="/book/1">都市之重生系统</a>
  <a class="book-name" href="/book/2">修仙从直播开始</a>
  <span class="book-name">无链接书名</span>
</div>
"""


class HotTopicsTests(unittest.TestCase):
    def test_parse_rank_html_extracts_titles(self):
        titles = parse_rank_html(FIXTURE)
        self.assertIn("都市之重生系统", titles)
        self.assertIn("修仙从直播开始", titles)
        self.assertNotIn("无链接书名", titles)

    def test_count_keywords(self):
        counts = dict(count_keywords(["都市之重生系统", "重生之都市修仙"]))
        self.assertEqual(counts.get("重生"), 2)
        self.assertEqual(counts.get("都市"), 2)

    def test_refresh_with_injected_fetcher(self):
        tmpdir = tempfile.mkdtemp()
        out = os.path.join(tmpdir, "hot_topics.json")
        payload = refresh(
            out_path=out,
            sources=[{"name": "fake", "url": "http://x"}],
            fetcher=lambda source: FIXTURE,
        )
        self.assertEqual(payload["sources"][0]["count"], 2)
        self.assertTrue(os.path.exists(out))
        saved = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertIn("都市之重生系统", saved["sources"][0]["titles"])

    def test_refresh_falls_back_to_browser_when_html_empty(self):
        tmpdir = tempfile.mkdtemp()
        out = os.path.join(tmpdir, "hot_topics.json")
        with mock.patch(
            "novel_pipeline.hot_topics.fetch_rank_browser",
            return_value=["都市之重生系统", "修仙从直播开始"],
        ):
            payload = refresh(
                out_path=out,
                sources=[{"name": "fake", "url": "http://x"}],
                fetcher=lambda source: "<html></html>",
            )
        src = payload["sources"][0]
        self.assertEqual(src["method"], "browser")
        self.assertEqual(src["count"], 2)

    def test_browser_extract_cleans_font_glyphs(self):
        import novel_pipeline.hot_topics as ht

        def fake_bb(args, timeout=60):
            cmd = args[0]
            if cmd == "open":
                return mock.Mock(
                    returncode=0,
                    stdout='{"result": {"tab": "abc"}}',
                    stderr="",
                )
            if cmd == "eval" and args[1] == ht.BROWSER_EXTRACT_JS:
                return mock.Mock(
                    returncode=0,
                    stdout=(
                        '{"result": {"result": "[\\"笨蛋\\ue001\\ue002替嫁\\ue003疯批王爷宠\\ue004\\", '
                        '\\"首页\\", \\"月票榜\\", \\"短\\"]"}}'
                    ),
                    stderr="",
                )
            return mock.Mock(returncode=0, stdout="{}", stderr="")

        with mock.patch("novel_pipeline.hot_topics._bb_run", side_effect=fake_bb):
            titles = ht.fetch_rank_browser({"url": "http://x", "name": "fake"})
        self.assertEqual(titles, ["笨蛋替嫁疯批王爷宠"])

    def test_from_csv(self):
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "topics.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("title,genre,heat\n都市之重生系统,都市重生,100\n")
        payload = from_csv(path)
        self.assertEqual(payload["titles"], ["都市之重生系统"])

    def test_to_premise_candidates(self):
        payload = {"titles": ["都市之重生系统", "修仙从直播开始"]}
        candidates = to_premise_candidates(payload, n=2)
        self.assertEqual(len(candidates), 2)
        self.assertIn("都市之重生系统", candidates[0])


if __name__ == "__main__":
    unittest.main()
