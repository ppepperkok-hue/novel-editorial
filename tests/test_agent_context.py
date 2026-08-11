"""S3 tests: editorial context snapshot injection."""

import os
import tempfile
import unittest
from unittest import mock

from novel_editorial import db
from tools import agent_context, agent_tool_loop, mailroom


class AgentContextTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.conn = db.connect(self.db_path)
        mailroom.send(self.conn, "reviewer", "writer", "第二章逻辑有漏洞", subject="打回", novel_id=1)
        self.conn.execute(
            "INSERT INTO agent_memories(agent,novel_id,category,importance,content,source,created_at) "
            "VALUES('writer',1,'plot',0.9,'审稿打回过我的第二章','review',"
            "datetime('now','localtime'))"
        )
        self.conn.execute(
            "INSERT INTO agent_relations(agent,other,novel_id,familiarity,trust,friction,updated_at) "
            "VALUES('writer','reviewer',1,0.2,0.3,0.4,datetime('now','localtime'))"
        )
        self.conn.execute(
            "INSERT INTO agent_promises(agent,novel_id,promise,due_at,source) "
            "VALUES('writer',1,'周四前交卷纲','2026-08-15','weekly')"
        )
        self.conn.execute(
            "INSERT INTO agent_actions(agent,novel_id,task,status) "
            "VALUES('writer',1,'把规则台账模板定死','pending')"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_snapshot_contains_all_sections(self):
        snap = agent_context.build_context_snapshot(self.conn, "writer", novel_id=1)
        self.assertIn("收件箱", snap)
        self.assertIn("来自 reviewer", snap)
        self.assertIn("最近记忆", snap)
        self.assertIn("审稿打回过我的第二章", snap)

    def test_pending_reply_messages_are_injected(self):
        first = mailroom.send(
            self.conn, "writer", "reviewer", "这是初稿，请审", novel_id=1
        )
        mailroom.send(
            self.conn, "reviewer", "writer", "重写第三章",
            reply_to=first["id"], novel_id=1,
        )
        snap = agent_context.build_context_snapshot(self.conn, "writer", novel_id=1)
        self.assertIn("待响应留言", snap)
        self.assertIn("重写第三章", snap)

    def test_mood_note_injected(self):
        self.conn.execute(
            "INSERT INTO agent_states(agent,novel_id,mood,updated_at) "
            "VALUES('writer',1,?,datetime('now','localtime'))",
            ('{"note": "手感正好"}',),
        )
        self.conn.commit()
        snap = agent_context.build_context_snapshot(self.conn, "writer", novel_id=1)
        self.assertIn("今日心情", snap)
        self.assertIn("手感正好", snap)

    def test_opinion_memories_sort_first(self):
        self.conn.execute(
            "INSERT INTO agent_memories(agent,novel_id,category,importance,content,source,created_at) "
            "VALUES('writer',1,'plot',0.9,'普通剧情记忆','review',datetime('now','localtime'))"
        )
        self.conn.execute(
            "INSERT INTO agent_memories(agent,novel_id,category,importance,content,source,created_at) "
            "VALUES('writer',1,'opinion',0.7,'我对题材的看法变了','weekly',datetime('now','localtime'))"
        )
        self.conn.commit()
        snap = agent_context.build_context_snapshot(self.conn, "writer", novel_id=1)
        self.assertLess(
            snap.index("我对题材的看法变了"),
            snap.index("普通剧情记忆"),
        )

    def test_memory_categories_filtered_by_agent_role(self):
        self.conn.execute(
            "INSERT INTO agent_memories(agent,novel_id,category,importance,content,source,created_at) "
            "VALUES('writer',1,'plot',0.8,'剧情记忆：旧书店的秘密','plot',datetime('now','localtime'))"
        )
        self.conn.execute(
            "INSERT INTO agent_memories(agent,novel_id,category,importance,content,source,created_at) "
            "VALUES('writer',1,'meeting',0.9,'会议记忆：下周加支线','meeting',datetime('now','localtime'))"
        )
        self.conn.commit()
        snap = agent_context.build_context_snapshot(self.conn, "writer", novel_id=1)
        self.assertIn("剧情记忆：旧书店的秘密", snap)
        self.assertNotIn("会议记忆：下周加支线", snap)
        self.assertIn("我与同事的关系", snap)
        self.assertIn("熟悉0.2 信任0.3 摩擦0.4", snap)
        self.assertIn("我未兑现的承诺", snap)
        self.assertIn("周四前交卷纲", snap)
        self.assertIn("我的待办行动项", snap)
        self.assertIn("规则台账模板", snap)

    def test_snapshot_empty_placeholder(self):
        snap = agent_context.build_context_snapshot(self.conn, "memory", novel_id=1)
        self.assertIn("暂无收件箱消息", snap)

    def test_snapshot_scoped_by_novel(self):
        snap = agent_context.build_context_snapshot(self.conn, "writer", novel_id=2)
        self.assertNotIn("第二章逻辑有漏洞", snap)
        self.assertNotIn("周四前交卷纲", snap)

    def test_long_body_truncated(self):
        mailroom.send(self.conn, "eic", "writer", "长" * 500, subject="长消息", novel_id=1)
        snap = agent_context.build_context_snapshot(self.conn, "writer", novel_id=1)
        self.assertIn("…", snap)
        self.assertLess(snap.index("长消息"), snap.index("…"))

    def test_agent_loop_injects_snapshot(self):
        def fake(model, system, user, temperature=0.5, max_tokens=1600, messages=None, tools=None, json_mode=None):
            return {"text": "正文", "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "model": "m"}

        with mock.patch("tools.agent_tool_loop.chat_deepseek", side_effect=fake) as chat:
            agent_tool_loop.run("writer", "写一章", novel_id=1, db_path=self.db_path)
        self.assertIn("编辑部协作上下文", chat.call_args.args[1])
        self.assertIn("收件箱", chat.call_args.args[1])

    def test_agent_loop_skips_without_db(self):
        def fake(model, system, user, temperature=0.5, max_tokens=1600, messages=None, tools=None, json_mode=None):
            return {"text": "正文", "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "model": "m"}

        with mock.patch("tools.agent_tool_loop.chat_deepseek", side_effect=fake) as chat:
            agent_tool_loop.run("writer", "写一章", novel_id=1, db_path=None)
        self.assertNotIn("编辑部协作上下文", chat.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
