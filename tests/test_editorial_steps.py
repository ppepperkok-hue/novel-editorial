import json
import unittest

from tools import editorial_steps as steps


class RobustJsonTests(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(steps.robust_json('{"a": 1}'), {"a": 1})

    def test_code_fence(self):
        self.assertEqual(
            steps.robust_json('```json\n{"a": 1}\n```'), {"a": 1}
        )

    def test_trailing_comma(self):
        self.assertEqual(steps.robust_json('{"a": 1,}'), {"a": 1})

    def test_truncated_object(self):
        self.assertEqual(steps.robust_json('{"a": {"b": 1'), {"a": {"b": 1}})

    def test_garbage_returns_none(self):
        self.assertIsNone(steps.robust_json("not json at all"))


class WritingContextTests(unittest.TestCase):
    def test_assembles_fields(self):
        ctx = steps.build_writing_context(
            {
                "prev_ending": "结尾",
                "recent_summaries": [{"summary": "s"}],
                "character_states": {"林舟": {}},
                "plot_threads": [{"description": "伏笔"}],
                "bible": {
                    "characters": [{"name": "林舟"}],
                    "relationships": [],
                    "world_rules": ["规则"],
                    "style_guide": "简洁",
                },
                "existing_titles": ["第一章"],
                "volume_goal": "第一卷",
                "target_words": "2000",
            }
        )
        for key in ("上一章结尾", "最近摘要", "角色状态", "活跃伏笔", "角色卡", "世界观规则", "风格指南", "目标字数"):
            self.assertIn(key, ctx)


class CategoryTests(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(steps.resolve_category("都市神医")[0], "124")
        self.assertEqual(steps.resolve_category("玄幻")[0], "258")
        self.assertEqual(steps.resolve_category("科幻末世")[0], "8")
        self.assertEqual(steps.resolve_category("悬疑灵异")[0], "10")
        self.assertEqual(steps.resolve_category("历史")[0], "273")
        self.assertEqual(steps.resolve_category("其他")[0], "259")


class WorkMetaTests(unittest.TestCase):
    def test_parse_with_defaults(self):
        src = {
            "premise": "p",
            "platform": "fanqie",
            "daily": 2,
            "keywords": "k",
            "book_id": "b1",
            "start_num": 3,
            "book_name": "旧书",
            "abstract": "",
            "genre": "都市",
            "meta_needed": True,
            "writing_context": "ctx",
        }
        meta = steps.parse_work_meta(
            json.dumps(
                {
                    "protagonist": {"name": "林舟", "traits": "坚韧", "goals": "查明"},
                    "book_name": "旧书店",
                    "abstract": " 简介 内容 ",
                }
            ),
            src,
        )
        self.assertEqual(meta["category_id"], "124")
        self.assertEqual(meta["protagonist"], "林舟")
        # The n8n original only collapses inner whitespace (no strip).
        self.assertEqual(meta["abstract"], " 简介 内容 ")
        self.assertEqual(meta["gender"], "1")

    def test_parse_requires_json(self):
        with self.assertRaises(ValueError):
            steps.parse_work_meta("broken", {"book_id": "b1"})


class BibleMergeTests(unittest.TestCase):
    def test_character_merge_and_dedupe(self):
        prev = {
            "characters": [{"name": "林舟", "traits": "冷静"}],
            "relationships": [{"from": "a", "to": "b", "relation": "友"}],
            "world_rules": ["规则1", "规则2"],
        }
        nxt = {
            "characters": [{"name": "林舟", "goals": "查明"}],
            "relationships": [{"from": "a", "to": "b", "relation": "友"}],
            "world_rules": ["规则2", "规则3"],
        }
        out = steps.merge_bible(prev, nxt)
        self.assertEqual(len(out["characters"]), 1)
        self.assertEqual(out["characters"][0]["traits"], "冷静")
        self.assertEqual(out["characters"][0]["goals"], "查明")
        self.assertEqual(len(out["relationships"]), 1)
        self.assertEqual(out["world_rules"], ["规则1", "规则2", "规则3"])

    def test_none_next_keeps_prev(self):
        self.assertEqual(steps.merge_bible({"a": 1}, None), {"a": 1})


class PlannerOutlineTests(unittest.TestCase):
    def _payload(self, count=2):
        return {
            "premise": "p",
            "genre": "都市",
            "title": "书",
            "keywords": ["k"],
            "chapter_outlines": [
                {"title": "第1章", "outline": "o1", "hook": "h1"}
                for _ in range(count)
            ],
            "bible": {"characters": []},
        }

    def test_two_chapters(self):
        out = steps.parse_planner_outline(json.dumps(self._payload()), {}, {})
        self.assertEqual(len(out["chapter1"].keys()) > 0, True)
        self.assertEqual(out["chapter1"]["title"], "第1章")
        self.assertEqual(out["chapter2"]["title"], "第1章")

    def test_too_few_chapters_raises(self):
        with self.assertRaises(ValueError):
            steps.parse_planner_outline(json.dumps(self._payload(1)), {}, {})

    def test_broken_json_raises(self):
        with self.assertRaises(ValueError):
            steps.parse_planner_outline("broken", {}, {})


class GuardTests(unittest.TestCase):
    def test_parses(self):
        g = steps.parse_guard(
            json.dumps(
                {
                    "passed": True,
                    "issues": [],
                    "constraints": ["规则"],
                    "character_beats": {"林舟": "克制"},
                }
            ),
            {"bible": {}, "chapter1": {}, "chapter2": {}},
        )
        self.assertTrue(g["guard_passed"])
        self.assertEqual(g["constraints"], ["规则"])

    def test_degrades_on_garbage(self):
        g = steps.parse_guard("not json", {"bible": {}, "chapter1": {}, "chapter2": {}})
        self.assertIsNone(g["guard_passed"])
        self.assertEqual(g["constraints"], [])


class QualityGateTests(unittest.TestCase):
    LONG = "他推开门走进院子，风从巷口吹来，远处传来吆喝声。" * 100

    def test_too_short_fails(self):
        gate = steps.quality_gate("短", "{}", None, None, {}, 2000)
        self.assertFalse(gate["passed"])
        self.assertTrue(any("字数不足" in e for e in gate["errors"]))

    def test_ai_words_fail(self):
        text = "突然" * 5 + "顿时" * 5 + self.LONG
        gate = steps.quality_gate(text, "{}", None, None, {}, 2000)
        self.assertFalse(gate["passed"])
        self.assertTrue(any("AI高频词" in e for e in gate["errors"]))

    def test_passes_with_verdicts(self):
        gate = steps.quality_gate(
            self.LONG,
            json.dumps({"passed": True}),
            json.dumps({"would_read_next": True, "score": 9, "hook_rating": 9}),
            json.dumps({"verdict": "pass"}),
            {"title": "第一章"},
            2000,
        )
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["title"]["title"], "第一章")

    def test_editor_missing_degrades_on_review(self):
        gate = steps.quality_gate(
            self.LONG,
            json.dumps({"passed": True}),
            json.dumps({"would_read_next": True, "score": 9, "hook_rating": 9}),
            None,
            {},
            2000,
        )
        self.assertTrue(gate["passed"])
        self.assertIn("降级", gate.get("editorNote") or "")

    def test_review_missing_or_unparseable_fails(self):
        gate = steps.quality_gate(self.LONG, None, None, None, {}, 2000)
        self.assertFalse(gate["passed"])
        self.assertTrue(any("逻辑审稿缺失" in e for e in gate["errors"]))
        gate2 = steps.quality_gate(self.LONG, "not json", None, None, {}, 2000)
        self.assertFalse(gate2["passed"])


class DraftPayloadTests(unittest.TestCase):
    def test_title_volume(self):
        draft = steps.build_draft_payload(
            {"book_id": "b1", "content_html": "<p>x</p>"},
            5,
            {
                "code": 0,
                "data": {
                    "item_id": "i1",
                    "volume_id": "v9",
                    "volume_data": [{"volume_id": "v9", "volume_name": "正文"}],
                },
            },
            {"title": "第 3 章 旧书店的秘密"},
        )
        self.assertEqual(draft["title"], "第 5 章 旧书店的秘密")
        self.assertEqual(draft["volume_name"], "正文")

    def test_missing_item_returns_none(self):
        self.assertIsNone(
            steps.build_draft_payload(
                {"book_id": "b1", "content_html": "<p>x</p>"},
                1,
                {"code": 0, "data": {}},
                {"title": "x"},
            )
        )


class PublishResponseTests(unittest.TestCase):
    def test_success(self):
        r = steps.parse_publish_response('{"code": 0, "data": {"item_id": "i1"}}')
        self.assertTrue(r["published"])
        self.assertEqual(r["item_id"], "i1")

    def test_failure(self):
        r = steps.parse_publish_response('{"code": 1, "message": "boom"}')
        self.assertFalse(r["published"])
        self.assertIn("boom", r["error"])


class StartMetaTests(unittest.TestCase):
    def test_found(self):
        cfg = {"book_id": "b1", "novel_title": "旧书店"}
        resp = {
            "data": {
                "book_list": [
                    {"book_id": "b1", "chapter_number": 3, "book_name": "旧书店", "abstract": "x" * 60}
                ]
            }
        }
        m = steps.compute_start_meta(cfg, resp)
        self.assertEqual(m["start_num"], 4)
        self.assertFalse(m["meta_needed"])

    def test_missing_book_id_raises(self):
        with self.assertRaises(ValueError):
            steps.compute_start_meta({"book_id": ""}, {})

    def test_book_not_found_raises(self):
        with self.assertRaises(ValueError):
            steps.compute_start_meta({"book_id": "b2"}, {"data": {"book_list": []}})

    def test_meta_needed_short_abstract(self):
        cfg = {"book_id": "b1", "novel_title": ""}
        resp = {
            "data": {
                "book_list": [{"book_id": "b1", "chapter_number": 0, "book_name": "用户123", "abstract": "短"}]
            }
        }
        self.assertTrue(steps.compute_start_meta(cfg, resp)["meta_needed"])


class ReviewTests(unittest.TestCase):
    def test_found_published(self):
        r = steps.parse_review(
            '{"code": 0, "data": {"item_list": [{"item_id": "i1", "article_status": 1}]}}',
            "i1",
        )
        self.assertEqual(r["status"], "published")
        self.assertTrue(r["found"])

    def test_not_found(self):
        r = steps.parse_review('{"code": 0, "data": {"item_list": []}}', "i1")
        self.assertEqual(r["status"], "pending")
        self.assertFalse(r["found"])


def _outline():
    return {
        "premise": "p",
        "genre": "都市",
        "title": "书",
        "keywords": "k",
        "bible": {},
        "chapter1": {"title": "第一章", "outline": "o1"},
        "chapter2": {"title": "第二章", "outline": "o2"},
    }


def _meta(start_num=1):
    return {
        "book_id": "b1",
        "book_name": "旧书店",
        "premise": "p",
        "platform": "fanqie",
        "start_num": start_num,
        "tags": [],
        "abstract": "",
        "protagonists": [],
        "volume_goal": "",
        "genre": "都市",
    }


class BuildPayloadTests(unittest.TestCase):
    def _track(self, gate_passed=True, draft=None, pub=None):
        gate = {
            "passed": gate_passed,
            "errors": [] if gate_passed else ["字数不足"],
            "chars": 2000 if gate_passed else 10,
            "editedText": "正文" if gate_passed else "短",
            "review": None,
            "reader": None,
            "editor": None,
        }
        return {"gate": gate, "summary": {"summary": "s"}, "draft": draft, "pub": pub}

    def test_both_published(self):
        draft = {"item_id": "i1", "title": "第 1 章 第一章"}
        pub = {"published": True, "item_id": "i1", "error": None}
        payload = steps.build_payload(
            "run-1",
            _meta(),
            _outline(),
            self._track(True, draft, pub),
            self._track(True, draft, pub),
            [],
            [],
        )
        self.assertEqual(len(payload["chapters"]), 2)
        self.assertTrue(all(c["status"] == "published" for c in payload["chapters"]))

    def test_quality_gate_fails_track(self):
        draft = {"item_id": "i1", "title": "第 1 章 第一章"}
        pub = {"published": True, "item_id": "i1", "error": None}
        payload = steps.build_payload(
            "run-1",
            _meta(),
            _outline(),
            self._track(False),
            self._track(True, draft, pub),
            [],
            [],
        )
        a = next(c for c in payload["chapters"] if c["seq"] == 1)
        b = next(c for c in payload["chapters"] if c["seq"] == 2)
        self.assertEqual(a["status"], "draft")
        self.assertIn("质量门未通过", a["error"])
        self.assertEqual(b["status"], "published")

    def test_k5_gate_passed_but_no_draft(self):
        payload = steps.build_payload(
            "run-1",
            _meta(),
            _outline(),
            self._track(True, None, None),
            self._track(True, None, None),
            [],
            [],
        )
        self.assertEqual(len(payload["chapters"]), 2)
        for c in payload["chapters"]:
            self.assertEqual(c["status"], "draft")
            self.assertIn("草稿创建/发布链中断", c["error"])

    def test_k2_llm_failure_fills_uncovered(self):
        draft = {"item_id": "i1", "title": "第 1 章 第一章"}
        pub = {"published": True, "item_id": "i1", "error": None}
        payload = steps.build_payload(
            "run-1",
            _meta(),
            _outline(),
            self._track(True, draft, pub),
            {"gate": None, "summary": {}, "draft": None, "pub": None},
            [],
            ["写手B"],
        )
        b = next(c for c in payload["chapters"] if c["seq"] == 2)
        self.assertEqual(b["status"], "draft")
        self.assertIn("LLM链路失败", b["error"])


if __name__ == "__main__":
    unittest.main()
