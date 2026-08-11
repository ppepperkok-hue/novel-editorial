"""Tests for auto-creating a Fanqie book (tools/create_book.py)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_pipeline import db  # noqa: E402
from tools import create_book  # noqa: E402


def make_db(status="ready"):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "t.db")
    conn = db.connect(path)
    conn.execute(
        "INSERT INTO novels(title,genre,premise,abstract,tags,protagonists,status) "
        "VALUES('测试书','悬疑灵异','测试简介','测试简介：一个少年踏上修行之路。',"
        "'[\"规则怪谈\",\"悬疑\"]','[{\"name\":\"林一（主角）\",\"role\":\"主角\"}]',?)",
        (status,),
    )
    conn.commit()
    conn.close()
    return path


def category_row(cid, name, label):
    return {
        "category_id": cid,
        "label": label,
        "name": name,
        "description": name,
    }


CATEGORIES = [
    category_row(751, "悬疑灵异", "主分类"),
    category_row(101, "玄幻", "主分类"),
    category_row(539, "悬疑脑洞", "主分类"),
    category_row(92, "规则怪谈", "主题"),
    category_row(95, "悬疑", "主题"),
    category_row(100, "高武世界", "主题"),
]


ACTIVITIES = {
    "code": 0,
    "data": {
        "activity_list": [
            {
                "activity_id": 300,
                "title": "活动B",
                "group_categorys": ["1_101", "1_751"],
                "is_default_choose": 0,
            },
            {
                "activity_id": 299,
                "title": "盛夏寻章｜暑期征文",
                "group_categorys": ["1_751", "1_539", "1_8"],
                "is_default_choose": 1,
            },
        ]
    },
}


class HelperTests(unittest.TestCase):
    def test_gender(self):
        self.assertEqual(create_book._gender("都市"), 1)
        self.assertEqual(create_book._gender("现代言情"), 0)
        self.assertEqual(create_book._gender("玄幻言情"), 1)  # 男频关键词优先

    def test_clean_protagonist_name(self):
        self.assertEqual(create_book._clean_protagonist_name("林一（主角）/别名"), "林一")
        self.assertEqual(create_book._clean_protagonist_name("abcdefghijk"), "abcde")

    def test_build_abstract_pads_to_50(self):
        short = "短简介"
        out = create_book._build_abstract(short)
        self.assertEqual(len(out), 50)
        self.assertNotIn("\n", out)

    def test_pick_main_category(self):
        self.assertEqual(
            create_book._pick_main_category(CATEGORIES, "悬疑灵异")["category_id"], 751
        )
        # substring fallback
        self.assertEqual(
            create_book._pick_main_category(CATEGORIES, "悬疑")["category_id"], 751
        )
        # no main label -> None
        self.assertIsNone(create_book._pick_main_category([category_row(1, "x", "主题")], "x"))

    def test_pick_extra_categories(self):
        picked = create_book._pick_extra_categories(CATEGORIES, ["规则怪谈", "悬疑"])
        ids = [c["category_id"] for c in picked]
        self.assertIn(92, ids)
        self.assertIn(95, ids)
        # capped at 2
        many = create_book._pick_extra_categories(
            CATEGORIES, ["规则怪谈", "悬疑", "高武世界"]
        )
        self.assertLessEqual(len(many), 2)


class CreateBookFlowTests(unittest.TestCase):
    def _env_file(self):
        tmp = tempfile.mkdtemp()
        env = Path(tmp) / ".env"
        env.write_text(
            "FANQIE_COOKIE=cookie=1\nFANQIE_CSRF_TOKEN=tok\nFANQIE_BOOK_ID=old\n",
            encoding="utf-8",
        )
        return env

    def _responses(self):
        return [
            {"code": 0, "data": CATEGORIES},
            ACTIVITIES,
            {"code": 0, "data": {"book_id": "12345"}},
            {"code": 0, "data": {"volume_list": [{"volume_id": "v99", "volume_name": "第一卷：默认"}]}},
        ]

    def test_create_and_bind_full_flow(self):
        path = make_db()
        conn = db.connect(path)
        env_file = self._env_file()
        try:
            with mock.patch("novel_pipeline.config.N8N_ENV_FILE", env_file):
                with mock.patch(
                    "tools.create_book.http_json", side_effect=self._responses()
                ) as http:
                    result = create_book.create_book_on_fanqie(conn, 1)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["book_id"], "12345")
            self.assertEqual(result["volume_id"], "v99")
            self.assertEqual(http.call_count, 4)

            # The create call must carry the fields the writer console sends.
            create_call = http.call_args_list[2]
            self.assertEqual(create_call.args[0], "POST")
            self.assertEqual(create_call.args[1], "/api/author/book/create/v0/")
            fields = create_call.args[2]
            self.assertEqual(fields["book_name"], "测试书")
            self.assertEqual(fields["roles"], '["林一"]')
            self.assertEqual(fields["category"], "751,92,95")
            self.assertEqual(fields["gender"], "1")
            self.assertEqual(fields["group_category_id"], "751")
            self.assertEqual(fields["activity_id"], "299")
            self.assertEqual(fields["is_self_pic"], "0")
            self.assertEqual(fields["thumb_uri"], create_book.DEFAULT_THUMB_URI)

            row = conn.execute("SELECT status, book_id FROM novels WHERE id=1").fetchone()
            self.assertEqual(row["status"], "publishing")
            self.assertEqual(row["book_id"], "12345")
            self.assertIn("FANQIE_BOOK_ID=12345", env_file.read_text(encoding="utf-8"))
            self.assertIn("FANQIE_VOLUME_ID=v99", env_file.read_text(encoding="utf-8"))
            logs = conn.execute(
                "SELECT category, action FROM audit_logs WHERE target_id=1"
            ).fetchall()
            self.assertTrue(any(l["action"] == "create_book" for l in logs))
        finally:
            conn.close()

    def test_omit_group_category_when_no_activity_matches(self):
        path = make_db()
        conn = db.connect(path)
        try:
            responses = [
                {"code": 0, "data": CATEGORIES},
                {
                    "code": 0,
                    "data": {
                        "activity_list": [
                            {
                                "activity_id": 300,
                                "group_categorys": ["1_999"],
                                "is_default_choose": 1,
                            }
                        ]
                    },
                },
                {"code": 0, "data": {"book_id": "12345"}},
                {"code": 0, "data": {"volume_list": []}},
            ]
            with mock.patch("tools.create_book.load_env", return_value={"FANQIE_COOKIE": "x"}):
                with mock.patch("tools.create_book.http_json", side_effect=responses) as http:
                    result = create_book.create_book_on_fanqie(conn, 1)
            self.assertTrue(result["ok"], result)
            fields = http.call_args_list[2].args[2]
            self.assertEqual(fields["activity_id"], "")
            self.assertNotIn("group_category_id", fields)
        finally:
            conn.close()

    def test_reject_when_no_main_category(self):
        path = make_db()
        conn = db.connect(path)
        try:
            responses = [
                {"code": 0, "data": [category_row(1, "规则怪谈", "主题")]},
            ]
            with mock.patch("tools.create_book.load_env", return_value={"FANQIE_COOKIE": "x"}):
                with mock.patch("tools.create_book.http_json", side_effect=responses):
                    result = create_book.create_book_on_fanqie(conn, 1)
            self.assertFalse(result["ok"])
            self.assertIn("主分类", result["error"])
        finally:
            conn.close()

    def test_reject_not_ready(self):
        path = make_db(status="planning")
        conn = db.connect(path)
        try:
            with mock.patch("tools.create_book.load_env", return_value={"FANQIE_COOKIE": "x"}):
                result = create_book.create_book_on_fanqie(conn, 1)
            self.assertFalse(result["ok"])
            self.assertIn("ready", result["error"])
        finally:
            conn.close()

    def test_reject_already_bound(self):
        path = make_db()
        conn = db.connect(path)
        try:
            conn.execute("UPDATE novels SET book_id='999' WHERE id=1")
            conn.commit()
            with mock.patch("tools.create_book.load_env", return_value={"FANQIE_COOKIE": "x"}):
                result = create_book.create_book_on_fanqie(conn, 1)
            self.assertFalse(result["ok"])
            self.assertIn("无需重复建书", result["error"])
        finally:
            conn.close()

    def test_missing_cookie(self):
        path = make_db()
        conn = db.connect(path)
        try:
            with mock.patch("tools.create_book.load_env", return_value={}):
                result = create_book.create_book_on_fanqie(conn, 1)
            self.assertFalse(result["ok"])
            self.assertIn("FANQIE_COOKIE", result["error"])
        finally:
            conn.close()

    def test_platform_rejection_message(self):
        path = make_db()
        conn = db.connect(path)
        try:
            responses = [
                {"code": 0, "data": CATEGORIES},
                ACTIVITIES,
                {"code": 1, "message": "每天最多创建1本新书"},
            ]
            with mock.patch("tools.create_book.load_env", return_value={"FANQIE_COOKIE": "x"}):
                with mock.patch("tools.create_book.http_json", side_effect=responses):
                    result = create_book.create_book_on_fanqie(conn, 1)
            self.assertFalse(result["ok"])
            self.assertIn("每天最多创建1本新书", result["error"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
