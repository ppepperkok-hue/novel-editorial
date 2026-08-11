"""Editorial context snapshots injected into every agent call (S3).

The snapshot carries the agent's mailbox, recent memories, relationship
state, open promises and pending actions so agents behave like editors who
know what is happening around them. All limits are config-driven; the
snapshot degrades gracefully to empty sections.
"""

from __future__ import annotations

from novel_pipeline import config
from tools import editorial_state


def _truncate(text, limit):
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + "…"


def _scoped_ids(novel_id):
    """Return the novel scopes a row may belong to (global + this novel)."""
    novel_id = int(novel_id or 0)
    return (0,) if novel_id == 0 else (0, novel_id)


def build_context_snapshot(conn, agent, novel_id=0):
    """Assemble the collaboration snapshot for `agent` as a prompt section."""
    agent = str(agent or "")
    if not agent:
        return ""
    scopes = _scoped_ids(novel_id)
    marks = ",".join("?" * len(scopes))
    limit = config.AGENT_CTX_TRUNCATE
    sections = []

    # Mailbox: unread first, newest first.
    rows = conn.execute(
        "SELECT from_agent, subject, body, status FROM agent_messages "
        "WHERE to_agent=? AND ref_novel_id IN (" + marks + ") "
        "ORDER BY (status='unread') DESC, id DESC LIMIT ?",
        (agent, *scopes, config.AGENT_CTX_MESSAGES),
    ).fetchall()
    if rows:
        lines = []
        for r in rows:
            tag = "未读" if r["status"] == "unread" else "已读"
            subject = f"：{r['subject']}" if r["subject"] else ""
            lines.append(
                f"- [{tag}] 来自 {r['from_agent']}{subject}："
                + _truncate(r["body"], limit)
            )
        sections.append("收件箱：\n" + "\n".join(lines))

    memories = editorial_state.list_memories(
        conn, agent=agent, novel_id=novel_id, limit=config.AGENT_CTX_MEMORIES
    ).get("items") or []
    if memories:
        sections.append(
            "最近记忆：\n"
            + "\n".join(
                f"- [{r['category']}] " + _truncate(r["content"], limit)
                for r in memories
            )
        )

    relations = editorial_state.list_relations(
        conn, agent=agent, novel_id=novel_id, limit=config.AGENT_CTX_RELATIONS
    ).get("items") or []
    if relations:
        sections.append(
            "我与同事的关系：\n"
            + "\n".join(
                (
                    f"- {r['other']}：熟悉{float(r['familiarity'] or 0):.1f} "
                    f"信任{float(r['trust'] or 0):.1f} "
                    f"摩擦{float(r['friction'] or 0):.1f}"
                )
                for r in relations
            )
        )

    promises = [
        r for r in (
            editorial_state.list_promises(
                conn, agent=agent, novel_id=novel_id, status="open",
                limit=config.AGENT_CTX_PROMISES,
            ).get("items") or []
        )
    ]
    if promises:
        sections.append(
            "我未兑现的承诺：\n"
            + "\n".join(
                f"- {_truncate(r['promise'], limit)}"
                + (f"（到期 {r['due_at']}）" if r["due_at"] else "")
                for r in promises
            )
        )

    actions = conn.execute(
        "SELECT task, status FROM agent_actions "
        "WHERE novel_id IN (" + marks + ") "
        "AND status IN ('pending','claimed','in_progress') "
        "AND (agent=? OR assignee=? OR claimed_by=?) "
        "ORDER BY id DESC LIMIT ?",
        (*scopes, agent, agent, agent, config.AGENT_CTX_ACTIONS),
    ).fetchall()
    if actions:
        sections.append(
            "我的待办行动项：\n"
            + "\n".join(f"- [{r['status']}] " + _truncate(r["task"], limit) for r in actions)
        )

    if not sections:
        return "[编辑部协作上下文]\n（暂无收件箱消息、记忆、关系、承诺或待办）"
    return "[编辑部协作上下文]\n" + "\n\n".join(sections)
