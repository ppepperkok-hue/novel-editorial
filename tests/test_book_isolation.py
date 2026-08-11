"""Regression tests for per-book isolation (external review P1-1)."""

import json
import os
import tempfile
import unittest

from novel_pipeline import db
from tools import check_stock, preflight


def _seed_book(conn, title, book_id, status="publishing", chapters=0, published_today=0):
    cur = conn.execute(
        "INSERT INTO novels(title,genre,premise,selling_point,platform,status,book_id,"
        "tags,abstract,protagonists,outline,volume_goal,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            title,
            "都市",
            "设定",
            "",
            "fanqie",
            status,
            book_id,
            json.dumps(["都市"]),
            "x" * 60,
            json.dumps([]),
            json.dumps({}),
            "",
            "2026-08-11 00:00:00",
        ),
    )
    novel_id = cur.lastrowid
    for i in range(chapters):
        cid = conn.execute(
            "INSERT INTO chapters(novel_id,seq,outline,status) VALUES(?,?,?,?)",
            (novel_id, i + 1, "o", "reviewed"),
        ).lastrowid
        conn.execute(
            "INSERT INTO chapter_content(chapter_id,content,updated_at) "
            "VALUES(?,?,datetime('now','localtime'))",
            (cid, "正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容"),
        )
    for i in range(published_today):
        cid = conn.execute(
            "INSERT INTO chapters(novel_id,seq,outline,status,published_at) "
            "VALUES(?,?,?,'published',datetime('now','localtime'))",
            (novel_id, 100 + i, "o"),
        ).lastrowid
        conn.execute(
            "INSERT INTO publish_logs(chapter_id,platform,action,result,error,ai_declared,created_at) "
            "VALUES(?,?,?,?,?,?,datetime('now','localtime'))",
            (cid, "fanqie", "publish", "success", "", 1),
        )
    conn.commit()
    return novel_id


class BookIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.conn = db.connect(self.db_path)

    def tearDown(self):
        self.conn.close()

    def test_check_already_ran_is_per_book(self):
        book_a = _seed_book(self.conn, "甲书", "bA", published_today=1)
        book_b = _seed_book(self.conn, "乙书", "bB")
        self.assertTrue(preflight.check_already_ran(self.conn, book_a))
        self.assertFalse(preflight.check_already_ran(self.conn, book_b))

    def test_check_stock_is_per_book(self):
        book_a = _seed_book(self.conn, "甲书", "bA", chapters=2)
        book_b = _seed_book(self.conn, "乙书", "bB")
        stock_b = check_stock.check_stock(self.conn, novel_id=book_b)
        self.assertEqual(stock_b["stock"], 0)
        self.assertEqual(stock_b["need"], stock_b["target"])
        self.assertEqual(stock_b["novel_id"], book_b)
        stock_a = check_stock.check_stock(self.conn, novel_id=book_a)
        self.assertEqual(stock_a["stock"], 2)
        self.assertEqual(stock_a["need"], 0)

    def test_check_stock_finishing_book_is_usable(self):
        book = _seed_book(self.conn, "收尾书", "bF", status="finishing", chapters=1)
        stock = check_stock.check_stock(self.conn, novel_id=book)
        self.assertEqual(stock["novel_id"], book)
        self.assertEqual(stock["stock"], 1)


if __name__ == "__main__":
    unittest.main()
