"""R3-1: agent agency - a whitelist of safe autonomous actions.

Agents may autonomously perform safe, side-effect-free-internal actions:
write a report, propose a knowledge draft, post an issue for the next
meeting, claim a task or propose a new action item. Anything outside the
whitelist is rejected and audited. External side effects (publish, create/
delete books, finishing, adopting knowledge) are never reachable here.
"""

from __future__ import annotations

from novel_editorial import config
from novel_editorial.services import audit

AGENCY_ACTIONS = ("write_report", "update_draft", "post_issue", "claim_task", "propose")


def _err(message):
    return {"ok": False, "error": message}


def _dispatch(conn, agent, novel_id, name, item):
    """Execute one whitelisted action; returns True on success."""
    from novel_editorial.services import activity  # noqa: PLC0415
    from tools import mailroom  # noqa: PLC0415

    body = str(
        item.get("body") or item.get("content") or item.get("task") or ""
    ).strip()
    if name == "write_report":
        if not body:
            return False
        activity.log_activity(
            conn, agent, novel_id, "agency_report", body[:500],
            {"source": "agency"},
        )
        return True
    if name == "update_draft":
        if not body:
            return False
        conn.execute(
            "INSERT INTO knowledge_drafts(kind,agent,source,title,content,status,created_at) "
            "VALUES('lesson',?,'agency',?,?,'draft',datetime('now','localtime'))",
            (
                agent,
                str(item.get("title") or body[:30]),
                body[:4000],
            ),
        )
        return True
    if name == "post_issue":
        if not body:
            return False
        r = mailroom.send(
            conn, agent, "eic", body[:400],
            subject="议题提议", kind="topic_request", novel_id=novel_id,
        )
        return bool(r.get("ok"))
    if name == "claim_task":
        action_id = int(item.get("action_id") or 0)
        if not action_id:
            return False
        r = activity.claim_action(conn, action_id, agent, novel_id=novel_id)
        return bool(r.get("ok"))
    if name == "propose":
        if not body:
            return False
        r = activity.create_action(
            conn, agent, body[:300], novel_id=novel_id,
            detail={"source": "agency"},
            priority=str(item.get("priority") or "medium"),
        )
        return bool(r.get("ok"))
    return False


def apply(conn, agent, novel_id, actions):
    """Apply an agent's agency array; whitelisted items execute, others reject."""
    if not config.AGENCY_ENABLED:
        return {"ok": False, "error": "agency disabled", "applied": 0, "rejected": 0}
    if not isinstance(actions, list):
        return _err("agency must be a list")
    applied = 0
    rejected = 0
    for item in actions:
        if not isinstance(item, dict):
            rejected += 1
            continue
        name = str(item.get("action") or "").strip()
        if name not in AGENCY_ACTIONS:
            audit.log(
                conn, "agency", "rejected",
                target_type="agent", target_id=agent,
                detail={"action": name, "novel_id": novel_id},
            )
            rejected += 1
            continue
        ok = _dispatch(conn, agent, novel_id, name, item)
        audit.log(
            conn, "agency", name,
            target_type="agent", target_id=agent,
            detail={"novel_id": novel_id, **item},
        )
        if ok:
            applied += 1
    conn.commit()
    return {"ok": True, "applied": applied, "rejected": rejected}
