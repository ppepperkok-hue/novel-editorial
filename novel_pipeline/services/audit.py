"""Unified audit trail: every traceable pipeline event lands here."""

import json


def log(conn, category, action, target_type="", target_id="", detail=None, source="web"):
    conn.execute(
        "INSERT INTO audit_logs(created_at,category,action,target_type,target_id,detail,source) "
        "VALUES(datetime('now','localtime'),?,?,?,?,?,?)",
        (
            category,
            action,
            target_type,
            str(target_id),
            json.dumps(detail or {}, ensure_ascii=False),
            source,
        ),
    )
    conn.commit()


def list_logs(conn, category=None, limit=100):
    sql = (
        "SELECT id, created_at, category, action, target_type, target_id, detail, source "
        "FROM audit_logs"
    )
    params = []
    if category:
        sql += " WHERE category=?"
        params.append(category)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["detail"] = json.loads(d["detail"] or "{}")
        except (TypeError, json.JSONDecodeError):
            d["detail"] = {}
        out.append(d)
    return out
