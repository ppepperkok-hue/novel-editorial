"""R4-2: post-meeting action routing per kind.

The generic post-meeting action generation (activity.generate_post_meeting_actions)
already turns the report into agent_actions. This module adds the kind-specific
side effects: incident/retro lessons become knowledge drafts, learning meetings
turn proposals into drafts, review/critique record explicit markers. Everything
is idempotent per session (an audit marker prevents double application).
"""

from __future__ import annotations

import json

from novel_editorial import config
from novel_editorial.services import audit
from tools import meeting_kinds


def _insert_draft(conn, agent, title, content):
    conn.execute(
        "INSERT INTO knowledge_drafts(kind,agent,source,title,content,status,created_at) "
        "VALUES('lesson',?,'meeting',?,?,'draft',datetime('now','localtime'))",
        (agent, (title or content)[:40], (content or "")[:4000]),
    )


def run_post_actions(conn, session_id, meeting_id, novel_id, kind, report,
                     transcript=None, attendees=None):
    """Apply kind-specific post-meeting side effects, exactly once per session."""
    spec = meeting_kinds.MEETING_KINDS.get(
        str(kind or "topic"), meeting_kinds.MEETING_KINDS["topic"]
    )
    actions = spec.get("post_actions") or ["actions"]
    # Reserve the idempotency marker atomically: INSERT ... WHERE NOT EXISTS
    # is one statement, so concurrent runs cannot both pass the check.
    marker = conn.execute(
        "INSERT INTO audit_logs(created_at,category,action,target_type,target_id,detail) "
        "SELECT datetime('now','localtime'), 'meeting', 'post_actions_applied', "
        "'session', ?, ? "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM audit_logs WHERE category='meeting' "
        "  AND action='post_actions_applied' AND target_type='session' "
        "  AND target_id=?"
        ")",
        (
            str(session_id),
            json.dumps({"kind": kind, "results": "pending"}, ensure_ascii=False),
            str(session_id),
        ),
    )
    conn.commit()
    if marker.rowcount == 0:
        return {"ok": True, "skipped": True, "reason": "already applied"}

    results = {}
    lessons = report.get("lessons") or []
    if "incident" in actions or "retro" in actions:
        created = 0
        for item in lessons:
            if isinstance(item, dict):
                text = str(item.get("lesson") or item.get("content") or "").strip()
                title = str(item.get("title") or "")[:40]
            else:
                text = str(item).strip()
                title = ""
            if text:
                _insert_draft(conn, "memory", title, text)
                created += 1
        results["lesson_drafts"] = created
    if "learning" in actions:
        created = 0
        for proposal in report.get("proposals") or report.get("action_items") or []:
            if isinstance(proposal, dict):
                text = str(proposal.get("proposal") or proposal.get("task") or "").strip()
                title = str(proposal.get("title") or "")[:40]
            else:
                text = str(proposal).strip()
                title = ""
            if text:
                _insert_draft(conn, "knowledge_keeper", title, text)
                created += 1
        results["knowledge_drafts"] = created
    if "review" in actions:
        audit.log(
            conn, "meeting", "ending_review_recorded",
            target_type="session", target_id=str(session_id),
            detail={
                "recommendation": str(report.get("recommendation") or "")[:200],
                "kind": kind,
            },
        )
        results["review"] = True
    if "critique" in actions:
        audit.log(
            conn, "meeting", "critique_recorded",
            target_type="session", target_id=str(session_id),
            detail={
                "verdict": str(report.get("verdict") or "")[:200],
                "kind": kind,
            },
        )
        results["critique"] = True
    conn.execute(
        "UPDATE audit_logs SET detail=? WHERE category='meeting' "
        "AND action='post_actions_applied' AND target_type='session' "
        "AND target_id=?",
        (
            json.dumps({"kind": kind, "results": results}, ensure_ascii=False),
            str(session_id),
        ),
    )
    conn.commit()
    return {"ok": True, "results": results}
