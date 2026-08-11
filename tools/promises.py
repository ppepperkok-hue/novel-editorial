"""Promise ledger (S6): structured promises extracted from weekly diaries and
meeting speeches, settled against production evidence so agents feel the
consequences of what they said they would do.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_promises(conn, agent, novel_id, promises, source=""):
    """Insert open promises, skipping duplicates by (agent, novel, text)."""
    agent = str(agent or "").strip()
    if not agent or not isinstance(promises, list):
        return {"ok": True, "added": 0}
    added = 0
    try:
        for item in promises:
            if not isinstance(item, dict):
                continue
            text = str(item.get("promise") or item.get("text") or "").strip()
            if not text:
                continue
            dup = conn.execute(
                "SELECT id FROM agent_promises WHERE agent=? AND novel_id=? "
                "AND promise=? AND status='open'",
                (agent, int(novel_id or 0), text),
            ).fetchone()
            if dup:
                continue
            conn.execute(
                "INSERT INTO agent_promises(agent,novel_id,promise,status,due_at,source) "
                "VALUES(?,?,?,?,?,?)",
                (
                    agent,
                    int(novel_id or 0),
                    text,
                    "open",
                    str(item.get("due_at") or ""),
                    str(source or ""),
                ),
            )
            added += 1
        conn.commit()
        return {"ok": True, "added": added}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"record_promises failed: {str(exc)[:200]}"}


def build_evidence(conn, novel_id=0, days=7):
    """Production evidence used to decide whether promises were kept."""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    scope = f"novel_id={int(novel_id)} AND " if novel_id else ""

    def count(sql, params=()):
        return conn.execute(sql, params).fetchone()["c"]

    chapters_published = count(
        f"SELECT COUNT(*) c FROM chapters WHERE {scope}status='published' "
        "AND published_at>=?",
        (since,),
    )
    publish_success = count(
        "SELECT COUNT(*) c FROM publish_logs pl JOIN chapters c ON c.id=pl.chapter_id "
        f"WHERE c.novel_id=? AND pl.result='success' AND pl.created_at>=?",
        (int(novel_id or 0), since),
    ) if novel_id else count(
        "SELECT COUNT(*) c FROM publish_logs WHERE result='success' AND created_at>=?",
        (since,),
    )
    reviews_done = count(
        f"SELECT COUNT(*) c FROM agent_activity WHERE {scope}activity_type='review' "
        "AND created_at>=?",
        (since,),
    )
    plans_done = count(
        f"SELECT COUNT(*) c FROM agent_activity WHERE {scope}activity_type='plan' "
        "AND created_at>=?",
        (since,),
    )
    knowledge_updates = count(
        f"SELECT COUNT(*) c FROM agent_activity WHERE {scope}activity_type='knowledge' "
        "AND created_at>=?",
        (since,),
    )
    actions_done = [
        str(r["task"])
        for r in conn.execute(
            f"SELECT task FROM agent_actions WHERE {scope}status='done' "
            "AND completed_at>=? ORDER BY id DESC LIMIT 50",
            (since,),
        ).fetchall()
    ]
    return {
        "chapters_published": chapters_published,
        "publish_success": publish_success,
        "reviews_done": reviews_done,
        "plans_done": plans_done,
        "knowledge_updates": knowledge_updates,
        "actions_done": actions_done,
    }


def _matches_evidence(promise, evidence):
    p = str(promise or "")
    if any(k in p for k in ("卷纲", "大纲", "细纲", "蓝图")) and evidence.get("plans_done", 0) > 0:
        return True
    if any(k in p for k in ("章", "正文", "稿")) and evidence.get("chapters_published", 0) > 0:
        return True
    if any(k in p for k in ("审", "检查", "把关")) and evidence.get("reviews_done", 0) > 0:
        return True
    if any(k in p for k in ("知识", "热点", "词库")) and evidence.get("knowledge_updates", 0) > 0:
        return True
    for task in evidence.get("actions_done") or []:
        if p and (p in task or task in p):
            return True
    return False


def settle_promises(conn, novel_id=0, days=7):
    """Settle open promises: kept when evidence matches, broken when overdue."""
    from tools import relations  # noqa: PLC0415

    relations.decay(conn, novel_id, days)
    evidence = build_evidence(conn, novel_id, days)
    today = datetime.now().strftime("%Y-%m-%d")
    scope = "AND novel_id=?" if novel_id else ""
    params = (int(novel_id),) if novel_id else ()
    rows = conn.execute(
        f"SELECT id, promise, due_at FROM agent_promises "
        f"WHERE status='open' {scope} ORDER BY id",
        params,
    ).fetchall()
    kept, broken = [], []
    try:
        for row in rows:
            if _matches_evidence(row["promise"], evidence):
                kept.append(row["id"])
            elif row["due_at"] and str(row["due_at"]) < today:
                broken.append(row["id"])
        for pid in kept:
            conn.execute(
                "UPDATE agent_promises SET status='kept', kept_at=? WHERE id=?",
                (_now(), pid),
            )
            row = conn.execute(
                "SELECT agent FROM agent_promises WHERE id=?", (pid,)
            ).fetchone()
            if row:
                relations.apply_event(
                    conn, row["agent"], "eic", "promise_kept", novel_id
                )
        for pid in broken:
            conn.execute(
                "UPDATE agent_promises SET status='broken' WHERE id=?",
                (pid,),
            )
            row = conn.execute(
                "SELECT agent FROM agent_promises WHERE id=?", (pid,)
            ).fetchone()
            if row:
                relations.apply_event(
                    conn, row["agent"], "eic", "promise_broken", novel_id
                )
        conn.commit()
        return {
            "ok": True,
            "kept": kept,
            "broken": broken,
            "open": len(rows) - len(kept) - len(broken),
            "evidence": evidence,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"settle_promises failed: {str(exc)[:200]}"}
