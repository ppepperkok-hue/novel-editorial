"""Misc data endpoints: alerts, reader stats, hot topics, export, meetings, taste."""

import json
import subprocess
import sys
import threading
from datetime import datetime

from novel_editorial import config, data_feedback, monitor
from novel_editorial.services import audit


def load_alerts(conn):
    from tools.app_settings import get_float  # noqa: PLC0415

    spent_row = conn.execute(
        "SELECT COALESCE(SUM(cost),0) s FROM cost_logs "
        "WHERE created_at >= date('now','localtime','start of month')"
    ).fetchone()
    spent = round(spent_row["s"] or 0.0, 4)
    budget = get_float(conn, "monthly_budget", 100.0)
    issues = monitor.run_checks(conn, monthly_budget=budget, spent=spent)
    tail = []
    if config.ALERTS_LOG.exists():
        tail = config.ALERTS_LOG.read_text(encoding="utf-8").strip().splitlines()[-20:]
    return {"issues": issues, "log_tail": tail}


def load_reader_stats():
    if not config.READER_CSV.exists():
        return {"present": False, "rows": [], "report": None}
    rows = data_feedback.load_reader_stats(config.READER_CSV)
    return {"present": True, "rows": rows, "report": data_feedback.feedback_report(rows)}


def load_hot_topics():
    if not config.HOT_TOPICS_JSON.exists():
        return {"present": False}
    payload = json.loads(config.HOT_TOPICS_JSON.read_text(encoding="utf-8"))
    payload["present"] = True
    return payload


def export_novels(conn):
    from novel_editorial.services.dashboard import load_novels  # noqa: PLC0415

    novels = load_novels(conn)
    lines = []
    total_chapters = 0
    total_words = 0
    for n in novels:
        lines.append(f"# {n['title']}")
        lines.append("")
        lines.append(f"- 类型：{n['genre']} · 平台：{n['platform']} · 状态：{n['status']}")
        lines.append(f"- 简介：{(n['abstract'] or n['premise'] or '').strip()}")
        lines.append(f"- 标签：{', '.join(n['tags'] or [])}")
        chapters = conn.execute(
            "SELECT * FROM chapters WHERE novel_id=? ORDER BY seq", (n["id"],)
        ).fetchall()
        for c in chapters:
            content_row = conn.execute(
                "SELECT content FROM chapter_content WHERE chapter_id=?", (c["id"],)
            ).fetchone()
            content = (content_row["content"] if content_row else "") or ""
            total_words += len(content)
            lines.append("")
            lines.append(f"## 第 {c['seq']} 章 {c['title']}")
            lines.append("")
            lines.append(
                f"状态：{c['status']} · 字数：{c['words']} · 发布时间：{c['published_at'] or '—'}"
            )
            lines.append("")
            lines.append(content if content else "（正文未存档）")
            total_chapters += 1
    if not novels:
        lines.append("（暂无作品）")
    markdown = "\n".join(lines)
    config.EXPORTS_DIR.mkdir(exist_ok=True)
    fname = f"novels_{datetime.now():%Y%m%d_%H%M%S}.md"
    (config.EXPORTS_DIR / fname).write_text(markdown, encoding="utf-8")
    result = {
        "ok": True,
        "path": str(config.EXPORTS_DIR / fname),
        "novels": len(novels),
        "chapters": total_chapters,
        "words": total_words,
    }
    audit.log(conn, "export", "novels", detail={k: result[k] for k in ("novels", "chapters", "words")})
    return result


def load_meetings(conn, limit=20):
    rows = conn.execute(
        "SELECT id, held_at, novel_id, attendees, topics, report, status, kind, session_id "
        "FROM weekly_meetings ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        try:
            report = json.loads(r["report"] or "{}")
        except (TypeError, json.JSONDecodeError):
            report = {}
        decisions = report.get("decisions") or {}
        out.append(
            {
                "id": r["id"],
                "held_at": r["held_at"],
                "novel_id": r["novel_id"],
                "attendees": json.loads(r["attendees"] or "[]"),
                "topics": json.loads(r["topics"] or "[]"),
                "status": r["status"],
                "summary": report.get("discussion_summary", ""),
                "blueprint_count": len(decisions.get("blueprint_updates") or []),
                "volume_goal_adjust": decisions.get("volume_goal_adjust", ""),
                "action_items": report.get("action_items", []),
                "report": report,
                "kind": r["kind"] if "kind" in r.keys() else "weekly",
                "session_id": r["session_id"] if "session_id" in r.keys() else 0,
            }
        )
    return out


def start_topic_meeting(topic, db_path="demo.db"):
    """Launch a topic meeting in a background thread."""
    if not topic or not str(topic).strip():
        return {"ok": False, "error": "topic 不能为空"}

    def _run():
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(config.ROOT / "tools" / "agent_meeting.py"),
                    "--db",
                    str(db_path),
                    "--topic",
                    str(topic).strip(),
                    "--kind",
                    "topic",
                ],
                cwd=config.ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3600,
            )
        except Exception as exc:  # noqa: BLE001
            try:
                config.ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
                with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
                    f.write(
                        f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 专题会议线程异常："
                        f"{exc.__class__.__name__}: {exc}\n"
                    )
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "note": "专题会议已启动，完成后可在周会档案查看"}


def ai_taste(conn, chapter_id):
    from tools.ai_taste_check import detect  # noqa: PLC0415

    row = conn.execute(
        "SELECT content FROM chapter_content WHERE chapter_id=?", (chapter_id,)
    ).fetchone()
    report = detect(row["content"] if row else "")
    report["chapter_id"] = chapter_id
    return report


def character_evolution(conn, novel_id):
    rows = conn.execute(
        "SELECT name, chapter_id, change_log, arc, created_at "
        "FROM character_evolution WHERE novel_id=? ORDER BY id DESC LIMIT 50",
        (novel_id,),
    ).fetchall()
    return {"evolution": [dict(r) for r in rows]}


def list_diaries(conn, agent=None, diary_type=None, limit=100):
    sql = (
        "SELECT id, agent, novel_id, diary_type, content, created_at "
        "FROM agent_diaries"
    )
    params = []
    conds = []
    if agent:
        conds.append("agent=?")
        params.append(agent)
    if diary_type:
        conds.append("diary_type=?")
        params.append(diary_type)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["content"] = json.loads(d["content"] or "{}")
        except (TypeError, json.JSONDecodeError):
            d["content"] = {}
        out.append(d)
    return out


def list_states(conn, limit=20):
    rows = conn.execute(
        "SELECT agent, novel_id, mood, updated_at FROM agent_states "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["mood"] = json.loads(d["mood"] or "{}")
        except (TypeError, json.JSONDecodeError):
            d["mood"] = {}
        out.append(d)
    return out


def update_diary(conn, diary_id, content):
    if not isinstance(content, dict):
        return {"ok": False, "error": "content must be an object"}
    row = conn.execute("SELECT id FROM agent_diaries WHERE id=?", (diary_id,)).fetchone()
    if row is None:
        return {"ok": False, "error": "diary not found"}
    conn.execute(
        "UPDATE agent_diaries SET content=? WHERE id=?",
        (json.dumps(content, ensure_ascii=False), diary_id),
    )
    conn.commit()
    return {"ok": True}


def update_state(conn, agent, novel_id, mood):
    if not isinstance(mood, dict):
        return {"ok": False, "error": "mood must be an object"}
    conn.execute("DELETE FROM agent_states WHERE agent=? AND novel_id=?", (agent, novel_id))
    conn.execute(
        "INSERT INTO agent_states(agent,novel_id,mood,updated_at) "
        "VALUES(?,?,?,datetime('now','localtime'))",
        (agent, novel_id, json.dumps(mood, ensure_ascii=False)),
    )
    conn.commit()
    return {"ok": True}
