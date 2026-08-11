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
    """Execute one whitelisted action; returns (ok, reason)."""
    from novel_editorial.services import activity  # noqa: PLC0415
    from tools import mailroom  # noqa: PLC0415

    body = str(
        item.get("body") or item.get("content") or item.get("task") or ""
    ).strip()
    if name == "write_report":
        if not body:
            return False, "empty body"
        activity.log_activity(
            conn, agent, novel_id, "agency_report", body[:500],
            {"source": "agency"},
        )
        return True, ""
    if name == "update_draft":
        if not body:
            return False, "empty body"
        conn.execute(
            "INSERT INTO knowledge_drafts(kind,agent,source,title,content,status,created_at) "
            "VALUES('lesson',?,'agency',?,?,'draft',datetime('now','localtime'))",
            (
                agent,
                str(item.get("title") or body[:30]),
                body[:4000],
            ),
        )
        return True, ""
    if name == "post_issue":
        if not body:
            return False, "empty body"
        r = mailroom.send(
            conn, agent, "eic", body[:400],
            subject="议题提议", kind="topic_request", novel_id=novel_id,
        )
        if r.get("ok"):
            return True, ""
        return False, str(r.get("error") or "post_issue rejected")
    if name == "claim_task":
        raw_id = item.get("action_id")
        if isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)):
            return False, "action_id must be an integer"
        if isinstance(raw_id, str) and not raw_id.strip().isdigit():
            return False, "action_id must be an integer"
        action_id = int(raw_id)
        if action_id <= 0:
            return False, "action_id must be positive"
        r = activity.claim_action(conn, action_id, agent, novel_id=novel_id)
        if r.get("ok"):
            return True, ""
        return False, str(r.get("error") or "claim_action rejected")
    if name == "propose":
        if not body:
            return False, "empty body"
        r = activity.create_action(
            conn, agent, body[:300], novel_id=novel_id,
            detail={"source": "agency"},
            priority=str(item.get("priority") or "medium"),
        )
        if r.get("ok"):
            return True, ""
        return False, str(r.get("error") or "create_action rejected")
    return False, "unknown action"


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
                detail={"action": name, "novel_id": novel_id, "reason": "unknown action"},
            )
            rejected += 1
            continue
        try:
            ok, reason = _dispatch(conn, agent, novel_id, name, item)
        except Exception as exc:  # noqa: BLE001
            audit.log(
                conn, "agency", name,
                target_type="agent", target_id=agent,
                detail={
                    "novel_id": novel_id,
                    "error": f"{exc.__class__.__name__}: {exc}",
                    **item,
                    "reason": "dispatch exception",
                },
            )
            rejected += 1
            continue
        audit.log(
            conn, "agency", name,
            target_type="agent", target_id=agent,
            detail={"novel_id": novel_id, **item, "ok": ok, "reason": reason},
        )
        if ok:
            applied += 1
        else:
            rejected += 1
    conn.commit()
    return {"ok": True, "applied": applied, "rejected": rejected}
