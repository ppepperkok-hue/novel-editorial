"""Pending interaction routing for free meetings (approval / clarify).

Requests are persisted, expire with the session heartbeat and can only be
resolved once (repeat responses return `stale`). Failures are explicit.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from novel_editorial.services import audit


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def request_interaction(conn, session_id, agent, kind, question, choices=None,
                        expires_in=300):
    """创建一条待审批交互。返回 {ok, interaction} 或 {ok:False, error}。"""
    if kind not in ("approval", "clarify"):
        return {"ok": False, "error": f"unknown kind {kind}"}
    if not str(question or "").strip():
        return {"ok": False, "error": "question is required"}
    now = datetime.now()
    cur = conn.execute(
        "INSERT INTO pending_interactions(session_id, agent, kind, payload, "
        "status, created_at, expires_at) VALUES(?,?,?,?,?,?,?)",
        (
            int(session_id),
            str(agent or ""),
            kind,
            json.dumps(
                {
                    "question": str(question),
                    "choices": list(choices or []),
                },
                ensure_ascii=False,
            ),
            "pending",
            now.strftime("%Y-%m-%d %H:%M:%S"),
            (now + timedelta(seconds=max(1, int(expires_in)))).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        ),
    )
    interaction_id = cur.lastrowid
    audit.log(
        conn,
        "meeting",
        "interaction_requested",
        target_type="session",
        target_id=int(session_id),
        detail={"interaction_id": interaction_id, "agent": str(agent), "kind": kind},
    )
    conn.commit()
    return {
        "ok": True,
        "interaction": {
            "id": interaction_id,
            "session_id": int(session_id),
            "agent": str(agent),
            "kind": kind,
            "question": str(question),
            "choices": list(choices or []),
            "status": "pending",
        },
    }


def resolve_interaction(conn, interaction_id, resolution):
    """响应一条交互；已响应/已过期返回 stale（幂等）。"""
    row = conn.execute(
        "SELECT * FROM pending_interactions WHERE id=?", (int(interaction_id),)
    ).fetchone()
    if not row:
        return {"ok": False, "error": "interaction not found"}
    if row["status"] != "pending":
        return {"ok": True, "stale": True, "status": row["status"]}
    conn.execute(
        "UPDATE pending_interactions SET status='resolved', resolution=?, "
        "resolved_at=? WHERE id=?",
        (str(resolution or ""), _now(), int(interaction_id)),
    )
    audit.log(
        conn,
        "meeting",
        "interaction_resolved",
        target_type="session",
        target_id=row["session_id"],
        detail={
            "interaction_id": int(interaction_id),
            "agent": row["agent"],
            "resolution": str(resolution or ""),
        },
    )
    conn.commit()
    return {"ok": True, "stale": False, "status": "resolved"}


def expire_interactions(conn):
    """把过期的 pending 交互标记 expired；返回过期数量。"""
    now = _now()
    rows = conn.execute(
        "SELECT id, session_id FROM pending_interactions "
        "WHERE status='pending' AND expires_at <= ?",
        (now,),
    ).fetchall()
    for row in rows:
        conn.execute(
            "UPDATE pending_interactions SET status='expired', resolved_at=? WHERE id=?",
            (now, row["id"]),
        )
        audit.log(
            conn,
            "meeting",
            "interaction_expired",
            target_type="session",
            target_id=row["session_id"],
            detail={"interaction_id": row["id"]},
        )
    if rows:
        conn.commit()
    return len(rows)
