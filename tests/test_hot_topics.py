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
            return_value=[
                {"title": "都市之重生系统", "author": "甲", "intro": "", "latest": "", "url": "http://x/1", "source": "fake"},
                {"title": "修仙从直播开始", "author": "乙", "intro": "", "latest": "", "url": "http://x/2", "source": "fake"},
            ],
        ):
            payload = refresh(
                out_path=out,
                sources=[{"name": "fake", "url": "http://x"}],
                fetcher=lambda source: "<html></html>",
            )
        src = payload["sources"][0]
        self.assertEqual(src["method"], "browser")
        self.assertEqual(src["count"], 2)
        self.assertEqual(len(src["books"]), 2)

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
                        '{"result": {"result": "[{\\"u\\":\\"https://fanqienovel.com/page/1\\",'
                        '\\"t\\":\\"笨蛋\\ue001\\ue002替嫁\\ue003疯批王爷宠\\ue004\\\\n莫栖君'
                        '\\\\n[完结]替嫁+冲喜\\\\n乔韫幼时摔坏脑袋，被爹娘疼继母欺。\\"}]"}}'
                    ),
                    stderr="",
                )
            return mock.Mock(returncode=0, stdout="{}", stderr="")

        with mock.patch("novel_pipeline.hot_topics._bb_run", side_effect=fake_bb):
            books = ht.fetch_rank_browser({"url": "http://x", "name": "fake"})
        self.assertEqual(books[0]["title"], "笨蛋替嫁疯批王爷宠")
        self.assertEqual(books[0]["author"], "莫栖君")
        self.assertIn("乔韫", books[0]["intro"])

    def test_parse_qidian_books(self):
        from novel_pipeline.hot_topics import parse_browser_books

        items = [
            {
                "u": "https://www.qidian.com/book/123/",
                "t": "1\n捞尸人\n纯洁滴小龙\n都市·异术超能\n连载\n"
                "人知鬼恐怖，鬼晓人心毒。这是一本传统灵异小说。\n"
                "最新更新\n第七百一十三章 人皮·2026-08-09 23:52",
            }
        ]
        books = parse_browser_books(items, "qidian_rank")
        self.assertEqual(books[0]["title"], "捞尸人")
        self.assertEqual(books[0]["author"], "纯洁滴小龙")
        self.assertIn("鬼晓人心毒", books[0]["intro"])
        self.assertIn("第七百一十三章", books[0]["latest"])

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
