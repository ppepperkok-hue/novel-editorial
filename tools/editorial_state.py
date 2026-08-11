"""Read-side queries for editorial state (S5): relations, memories, promises.

These back the panel read APIs and the agent context snapshot. All results
are explicit dicts; failures never raise.
"""

from __future__ import annotations


def _scoped_ids(novel_id):
    novel_id = int(novel_id or 0)
    return (0,) if novel_id == 0 else (0, novel_id)


def _err(message):
    return {"ok": False, "error": message}


def list_relations(conn, agent=None, novel_id=0, limit=50):
    """Relationships of `agent` (or all agents) within a novel scope."""
    limit = max(1, min(int(limit or 50), 500))
    try:
        sql = "SELECT * FROM agent_relations WHERE 1=1"
        params = []
        if agent:
            sql += " AND agent=?"
            params.append(str(agent))
        if novel_id:
            sql += " AND novel_id IN (" + ",".join("?" * len(_scoped_ids(novel_id))) + ")"
            params += list(_scoped_ids(novel_id))
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return {"ok": True, "items": [dict(r) for r in rows]}
    except Exception as exc:  # noqa: BLE001
        return _err(f"list_relations failed: {str(exc)[:200]}")


def list_memories(conn, agent=None, novel_id=0, category=None, limit=50):
    """Memories of `agent` (or all agents), optional category filter."""
    limit = max(1, min(int(limit or 50), 500))
    try:
        sql = "SELECT * FROM agent_memories WHERE 1=1"
        params = []
        if agent:
            sql += " AND agent=?"
            params.append(str(agent))
        if novel_id:
            sql += " AND novel_id IN (" + ",".join("?" * len(_scoped_ids(novel_id))) + ")"
            params += list(_scoped_ids(novel_id))
        if category:
            sql += " AND category=?"
            params.append(str(category))
        sql += " ORDER BY importance DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return {"ok": True, "items": [dict(r) for r in rows]}
    except Exception as exc:  # noqa: BLE001
        return _err(f"list_memories failed: {str(exc)[:200]}")


def list_promises(conn, agent=None, novel_id=0, status=None, limit=50):
    """Promises of `agent` (or all agents), optional status filter."""
    limit = max(1, min(int(limit or 50), 500))
    try:
        sql = "SELECT * FROM agent_promises WHERE 1=1"
        params = []
        if agent:
            sql += " AND agent=?"
            params.append(str(agent))
        if novel_id:
            sql += " AND novel_id IN (" + ",".join("?" * len(_scoped_ids(novel_id))) + ")"
            params += list(_scoped_ids(novel_id))
        if status:
            sql += " AND status=?"
            params.append(str(status))
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return {"ok": True, "items": [dict(r) for r in rows]}
    except Exception as exc:  # noqa: BLE001
        return _err(f"list_promises failed: {str(exc)[:200]}")
