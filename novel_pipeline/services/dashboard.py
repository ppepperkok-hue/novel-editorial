"""Dashboard data aggregation: summary, novels, chapters, costs."""

import json
from datetime import datetime


def load_summary(conn):
    queries = {
        "novels": "SELECT COUNT(*) c FROM novels",
        "chapters_total": "SELECT COUNT(*) c FROM chapters",
        "chapters_draft": "SELECT COUNT(*) c FROM chapters WHERE status='draft'",
        "chapters_ready": "SELECT COUNT(*) c FROM chapters WHERE status IN ('reviewed','queued')",
        "chapters_published": "SELECT COUNT(*) c FROM chapters WHERE status='published'",
        "quality_total": "SELECT COUNT(*) c FROM quality_reports",
        "quality_passed": "SELECT COUNT(*) c FROM quality_reports WHERE passed=1",
        "publish_failed": "SELECT COUNT(*) c FROM publish_logs WHERE result='failed' "
        "AND created_at >= datetime('now','localtime','-7 days')",
    }
    summary = {key: conn.execute(sql).fetchone()["c"] for key, sql in queries.items()}
    cost_row = conn.execute(
        "SELECT COALESCE(SUM(cost),0) s FROM cost_logs "
        "WHERE created_at >= date('now','localtime','start of month')"
    ).fetchone()
    summary["monthly_cost"] = round(cost_row["s"] or 0.0, 4)
    return summary


def load_novels(conn):
    rows = conn.execute(
        "SELECT n.id, n.title, n.genre, n.platform, n.status, "
        "n.book_id, n.tags, n.abstract, n.protagonists, n.outline, n.cover_prompt, "
        "n.volume_goal, n.premise, n.selling_point, n.updated_at, "
        "(SELECT COUNT(*) FROM chapters c WHERE c.novel_id=n.id) AS chapters, "
        "(SELECT COUNT(*) FROM chapters c WHERE c.novel_id=n.id "
        " AND c.status='published') AS published "
        " , (SELECT title FROM chapters c WHERE c.novel_id=n.id "
        " ORDER BY c.seq DESC LIMIT 1) AS last_chapter_title "
        "FROM novels n ORDER BY n.id"
    ).fetchall()
    novels = []
    for r in rows:
        d = dict(r)
        for key in ("tags", "protagonists", "outline"):
            try:
                d[key] = json.loads(d[key] or "{}" if key == "outline" else d[key] or "[]")
            except (TypeError, json.JSONDecodeError):
                d[key] = [] if key != "outline" else {}
        chars = conn.execute(
            "SELECT name, role, traits, goals FROM characters "
            "WHERE novel_id=? ORDER BY id",
            (d["id"],),
        ).fetchall()
        d["characters"] = [dict(c) for c in chars]
        novels.append(d)
    return novels


def load_chapters(conn, novel_id=None):
    sql = (
        "SELECT c.id, c.novel_id, c.seq, c.outline, c.title, c.status, c.words, c.score, "
        "c.published_at, c.fanqie_item_id, "
        "(SELECT r.revision_count FROM quality_reports r "
        " WHERE r.chapter_id=c.id ORDER BY r.id DESC LIMIT 1) AS revisions, "
        "(SELECT r.notes FROM quality_reports r "
        " WHERE r.chapter_id=c.id ORDER BY r.id DESC LIMIT 1) AS quality_notes "
        "FROM chapters c"
    )
    params = []
    if novel_id:
        sql += " WHERE c.novel_id=?"
        params.append(novel_id)
    sql += " ORDER BY c.novel_id, c.seq"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def load_publish_logs(conn, limit=50):
    rows = conn.execute(
        "SELECT id, chapter_id, platform, action, result, error, ai_declared, created_at "
        "FROM publish_logs ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def cost_summary(conn):
    by_day = [
        dict(r)
        for r in conn.execute(
            "SELECT substr(created_at,1,10) AS day, ROUND(SUM(cost),4) AS cost "
            "FROM cost_logs WHERE created_at >= date('now','localtime','start of month') "
            "GROUP BY day ORDER BY day"
        ).fetchall()
    ]
    by_node = [
        dict(r)
        for r in conn.execute(
            "SELECT node_name, model, SUM(prompt_tokens) AS prompt_tokens, "
            "SUM(completion_tokens) AS completion_tokens, ROUND(SUM(cost),4) AS cost "
            "FROM cost_logs GROUP BY node_name ORDER BY cost DESC"
        ).fetchall()
    ]
    return {"by_day": by_day, "by_node": by_node}


def build_payload(conn):
    from novel_pipeline.services import misc  # noqa: PLC0415
    from tools.app_settings import get_float  # noqa: PLC0415
    from tools import daily_runs  # noqa: PLC0415

    payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": load_summary(conn),
        "executions": daily_runs.local_executions(conn)[:5],
        "cost_budget": get_float(conn, "monthly_budget", 100.0),
        "novels": load_novels(conn),
        "chapters": load_chapters(conn),
        "publish_logs": load_publish_logs(conn),
        "health": misc.load_alerts(conn),
        "reader_stats": misc.load_reader_stats(),
        "hot_topics": misc.load_hot_topics(),
    }
    return payload
