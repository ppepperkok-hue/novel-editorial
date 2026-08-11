"""Agent mailbox: the horizontal collaboration channel of the editorial office.

Every function returns a dict with an explicit `ok` flag so failures are
never silent. Messages carry a novel scope for multi-book isolation and a
status machine: unread -> read -> resolved/archived.
"""

from __future__ import annotations

from datetime import datetime

from novel_pipeline.services import audit

RESOLUTIONS = ("accepted", "rejected", "done")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _err(message):
    return {"ok": False, "error": message}


def send(conn, from_agent, to_agent, body, subject="", kind="note",
         novel_id=0, chapter_id=0, reply_to=0):
    """Send one message; returns {ok, id}."""
    if not str(from_agent or "").strip() or not str(to_agent or "").strip():
        return _err("from_agent and to_agent are required")
    if not str(body or "").strip():
        return _err("body is required")
    try:
        cur = conn.execute(
            "INSERT INTO agent_messages(from_agent,to_agent,kind,subject,body,"
            "ref_novel_id,ref_chapter_id,reply_to,status,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                str(from_agent).strip(),
                str(to_agent).strip(),
                str(kind or "note")[:40],
                str(subject or "")[:200],
                str(body),
                int(novel_id or 0),
                int(chapter_id or 0),
                int(reply_to or 0),
                "unread",
                _now(),
            ),
        )
        conn.commit()
        audit.log(
            conn,
            "message",
            "mail_send",
            target_type="agent",
            target_id=str(to_agent),
            detail={
                "message_id": cur.lastrowid,
                "from": str(from_agent),
                "kind": str(kind or "note"),
                "subject": str(subject or "")[:200],
                "novel_id": int(novel_id or 0),
            },
        )
        return {"ok": True, "id": cur.lastrowid}
    except Exception as exc:  # noqa: BLE001
        return _err(f"send failed: {str(exc)[:200]}")


def broadcast(conn, from_agent, to_agents, body, subject="", kind="note", novel_id=0):
    """Send one message to several agents; returns the ids sent so far."""
    ids = []
    for to_agent in to_agents or []:
        result = send(
            conn, from_agent, to_agent, body,
            subject=subject, kind=kind, novel_id=novel_id,
        )
        if not result.get("ok"):
            return {**result, "sent": ids}
        ids.append(result["id"])
    return {"ok": True, "ids": ids, "sent": len(ids)}


def list_messages(conn, agent=None, novel_id=0, status=None, limit=50):
    """List messages touching `agent` (sent or received), scoped by novel."""
    limit = max(1, min(int(limit or 50), 500))
    sql = "SELECT * FROM agent_messages WHERE 1=1"
    params = []
    if agent:
        sql += " AND (to_agent=? OR from_agent=?)"
        params += [str(agent), str(agent)]
    if novel_id:
        sql += " AND ref_novel_id=?"
        params.append(int(novel_id))
    if status:
        sql += " AND status=?"
        params.append(str(status))
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    try:
        rows = conn.execute(sql, params).fetchall()
        return {"ok": True, "messages": [dict(r) for r in rows]}
    except Exception as exc:  # noqa: BLE001
        return _err(f"list failed: {str(exc)[:200]}")


def unread_count(conn, agent, novel_id=0):
    """Count unread messages addressed to `agent`."""
    if not str(agent or "").strip():
        return _err("agent is required")
    try:
        sql = "SELECT COUNT(*) c FROM agent_messages WHERE to_agent=? AND status='unread'"
        params = [str(agent)]
        if novel_id:
            sql += " AND ref_novel_id=?"
            params.append(int(novel_id))
        row = conn.execute(sql, params).fetchone()
        return {"ok": True, "unread": row["c"]}
    except Exception as exc:  # noqa: BLE001
        return _err(f"unread failed: {str(exc)[:200]}")


def unread_summary(conn, novel_id=0):
    """Per-recipient unread counts (the manual 'process messages' pump view)."""
    try:
        sql = "SELECT to_agent, COUNT(*) c FROM agent_messages WHERE status='unread'"
        params = []
        if novel_id:
            sql += " AND ref_novel_id=?"
            params.append(int(novel_id))
        sql += " GROUP BY to_agent ORDER BY c DESC"
        rows = conn.execute(sql, params).fetchall()
        agents = {r["to_agent"]: r["c"] for r in rows}
        return {"ok": True, "agents": agents, "total": sum(agents.values())}
    except Exception as exc:  # noqa: BLE001
        return _err(f"unread_summary failed: {str(exc)[:200]}")


def mark_read(conn, message_ids):
    """Mark unread messages as read; returns the number actually updated."""
    ids = [int(i) for i in (message_ids or []) if str(i).strip().isdigit()]
    if not ids:
        return _err("message_ids required")
    try:
        marks = ",".join("?" * len(ids))
        cur = conn.execute(
            f"UPDATE agent_messages SET status='read', read_at=? "
            f"WHERE id IN ({marks}) AND status='unread'",
            (_now(), *ids),
        )
        conn.commit()
        return {"ok": True, "marked": cur.rowcount}
    except Exception as exc:  # noqa: BLE001
        return _err(f"mark_read failed: {str(exc)[:200]}")


def resolve(conn, message_id, resolution="done"):
    """Resolve a message with an explicit outcome."""
    if resolution not in RESOLUTIONS:
        return _err("resolution must be accepted|rejected|done")
    try:
        cur = conn.execute(
            "UPDATE agent_messages SET status='resolved', resolution=?, resolved_at=? "
            "WHERE id=?",
            (resolution, _now(), int(message_id)),
        )
        conn.commit()
        audit.log(
            conn,
            "message",
            "mail_resolve",
            target_type="message",
            target_id=int(message_id),
            detail={"resolution": resolution},
        )
        return {"ok": cur.rowcount > 0, "updated": cur.rowcount}
    except Exception as exc:  # noqa: BLE001
        return _err(f"resolve failed: {str(exc)[:200]}")


def archive(conn, message_id):
    """Archive a message; idempotent for already-archived rows."""
    try:
        cur = conn.execute(
            "UPDATE agent_messages SET status='archived' "
            "WHERE id=? AND status!='archived'",
            (int(message_id),),
        )
        conn.commit()
        return {"ok": cur.rowcount > 0, "updated": cur.rowcount}
    except Exception as exc:  # noqa: BLE001
        return _err(f"archive failed: {str(exc)[:200]}")
