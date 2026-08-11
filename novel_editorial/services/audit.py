"""Unified audit trail: every traceable pipeline event lands here."""

import json


def log(conn, category, action, target_type="", target_id="", detail=None, source="web"):
    try:
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
    except Exception as exc:  # noqa: BLE001 - audit must never break business logic
        try:
            from novel_editorial import config  # noqa: PLC0415
            from datetime import datetime  # noqa: PLC0415

            config.ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
            with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
                f.write(
                    f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                    f"audit log failed ({category}/{action}): {str(exc)[:200]}\n"
                )
        except Exception:  # noqa: BLE001
            pass


def list_logs(conn, category=None, limit=100, date_from="", date_to=""):
    sql = (
        "SELECT id, created_at, category, action, target_type, target_id, detail, source "
        "FROM audit_logs WHERE 1=1"
    )
    params = []
    if category:
        sql += " AND category=?"
        params.append(category)
    if date_from:
        sql += " AND created_at>=?"
        params.append(str(date_from).strip()[:10] + " 00:00:00")
    if date_to:
        sql += " AND created_at<=?"
        params.append(str(date_to).strip()[:10] + " 23:59:59")
    limit = max(1, min(int(limit or 100), 500))
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
