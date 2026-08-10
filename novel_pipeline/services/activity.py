"""Agent activity log and post-meeting action items.

Every agent action (meeting speech, diary, knowledge maintenance, tool use,
decision application) is recorded into agent_activity so the panel can show
"what did each agent do today".  After a meeting, each attendee also gets
concrete post-meeting tasks in agent_actions, which are injected back into
their weekly briefs so the tasks actually get executed.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from novel_pipeline.llm_client import chat_deepseek

ACTION_STATUSES = ("pending", "done", "skipped")
AGENTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts" / "agents"


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json(value, fallback=None):
    if value is None or value == "":
        return fallback if fallback is not None else {}
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback if fallback is not None else {}


def log_activity(conn, agent, novel_id, activity_type, title, detail=None):
    """Record one activity row for an agent (or 'system' for pipeline events)."""
    conn.execute(
        "INSERT INTO agent_activity(agent,novel_id,activity_type,title,detail,created_at) "
        "VALUES(?,?,?,?,?,?)",
        (
            str(agent or "system"),
            novel_id or 0,
            str(activity_type or "system"),
            str(title or ""),
            json.dumps(detail or {}, ensure_ascii=False),
            _now(),
        ),
    )
    conn.commit()


def list_activity(conn, agent=None, day=None, limit=300):
    """Return activity rows ordered by time, optionally filtered."""
    sql = "SELECT id, agent, novel_id, activity_type, title, detail, created_at FROM agent_activity"
    conds = []
    params = []
    if agent:
        conds.append("agent=?")
        params.append(agent)
    if day:
        conds.append("created_at >= date(?) AND created_at < date(?,'+1 day')")
        params.extend([day, day])
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["detail"] = _json(d.get("detail"))
        out.append(d)
    return out


def activity_days(conn, agent=None, days=30):
    """Group activity rows by calendar day (newest first) for the panel."""
    rows = list_activity(conn, agent=agent, limit=1000)
    if not rows:
        return []
    by_day = {}
    for r in rows:
        day = (r["created_at"] or "")[:10]
        by_day.setdefault(day, []).append(r)
    return [{"date": d, "items": by_day[d]} for d in sorted(by_day, reverse=True)][:days]


def create_action(conn, agent, task, novel_id=0, session_id=0, meeting_id=0,
                  detail=None):
    """Create one pending action item for an agent."""
    if not agent or not str(task).strip():
        return {"ok": False, "error": "agent and task required"}
    cur = conn.execute(
        "INSERT INTO agent_actions(session_id,meeting_id,agent,novel_id,task,detail,status,created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            int(session_id or 0),
            int(meeting_id or 0),
            str(agent),
            novel_id or 0,
            str(task).strip(),
            json.dumps(detail or {}, ensure_ascii=False),
            "pending",
            _now(),
        ),
    )
    conn.commit()
    action_id = cur.lastrowid
    log_activity(
        conn,
        agent,
        novel_id,
        "action_created",
        "收到会后任务",
        {"action_id": action_id, "task": str(task).strip()[:200]},
    )
    return {"ok": True, "id": action_id}


def list_actions(conn, agent=None, status=None, limit=200):
    sql = "SELECT * FROM agent_actions"
    conds = []
    params = []
    if agent:
        conds.append("agent=?")
        params.append(agent)
    if status:
        conds.append("status=?")
        params.append(status)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["detail"] = _json(d.get("detail"))
        out.append(d)
    return out


def update_action(conn, action_id, status=None, result=None, task=None):
    row = conn.execute("SELECT * FROM agent_actions WHERE id=?", (action_id,)).fetchone()
    if row is None:
        return {"ok": False, "error": "action not found"}
    new_status = status or row["status"]
    if new_status not in ACTION_STATUSES:
        return {"ok": False, "error": f"invalid status {new_status}"}
    if task is not None:
        conn.execute("UPDATE agent_actions SET task=? WHERE id=?", (str(task).strip(), action_id))
    conn.execute(
        "UPDATE agent_actions SET status=?, result=?, completed_at=? WHERE id=?",
        (
            new_status,
            str(result or ""),
            _now() if new_status == "done" else (row["completed_at"] or ""),
            action_id,
        ),
    )
    conn.commit()
    log_activity(
        conn,
        row["agent"],
        row["novel_id"] or 0,
        "action_done" if new_status == "done" else "action_status",
        "行动项已完成" if new_status == "done" else f"行动项状态变更为 {new_status}",
        {"action_id": action_id, "task": row["task"][:200], "result": (result or "")[:300]},
    )
    return {"ok": True}


def _parse_task_list(text):
    if not text:
        return None
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return None
    try:
        value = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(value, list):
        return None
    return [v for v in value if isinstance(v, dict) and str(v.get("task") or "").strip()]


def generate_post_meeting_actions(conn, session_id, meeting_id, novel_id,
                                  attendees, report, transcript, dry_run=False):
    """Let each attendee turn meeting conclusions into their own task list.

    One cheap flash call per attendee.  On failure (or empty report action
    items) fall back to rule-based assignment so the meeting never finishes
    without a traceable task backlog.
    """
    action_items = report.get("action_items") or []
    created = 0
    for agent in attendees:
        speech = next((s.get("speech") for s in transcript if s.get("agent") == agent), {})
        if not isinstance(speech, dict):
            speech = {}
        user = (
            "你是刚开完会的 agent。根据会议结论，给自己列出会后的具体任务。"
            "只输出 JSON 数组，每项 {task(一句话可执行), reason, expected_output, due(如 '3天内')}，1-3 项。"
            "会议主题/结论："
            + json.dumps(
                {
                    "action_items": action_items,
                    "discussion_summary": report.get("discussion_summary", ""),
                },
                ensure_ascii=False,
            )
            + "；我在会上的发言（重点看我的 proposals/concerns/priority）："
            + json.dumps(
                {
                    k: speech.get(k)
                    for k in ("speech", "proposals", "concerns", "priority", "opinion")
                },
                ensure_ascii=False,
            )
        )
        tasks = None
        if not dry_run:
            try:
                system = (
                    "你是会议行动项整理器。任务要具体、可执行、和 agent 职责匹配，"
                    "不要泛泛而谈。"
                )
                try:
                    md = AGENTS_DIR / f"{agent}.md"
                    if md.exists():
                        head = md.read_text(encoding="utf-8")[:800]
                        if head.strip():
                            system += "\n该 agent 的职责档案摘录（据此派活）：\n" + head
                except OSError:
                    pass
                resp = chat_deepseek(
                    "deepseek-v4-flash",
                    system,
                    user,
                    temperature=0.3,
                    max_tokens=900,
                )
                tasks = _parse_task_list(resp["text"])
            except Exception:  # noqa: BLE001
                tasks = None
        if not tasks:
            # Fallback: rule-based assignment from report action items.
            mine = [
                item for item in action_items
                if str(agent) in str(item).lower() or str(agent) in str(item.get("owner", ""))
            ]
            tasks = []
            for item in (mine or action_items)[:2]:
                if isinstance(item, dict):
                    tasks.append(
                        {
                            "task": str(item.get("task") or item.get("title") or str(item)),
                            "reason": "会议结论分配",
                            "expected_output": "落实并回填结果",
                            "due": "下周会前",
                        }
                    )
            if not tasks:
                tasks = [
                    {
                        "task": "复盘本次会议，结合我的职责落实讨论结论",
                        "reason": "会议未产出可归因行动项",
                        "expected_output": "下次会议前给出进展",
                        "due": "下周会前",
                    }
                ]
        for t in tasks:
            detail = {
                "reason": str(t.get("reason") or ""),
                "expected_output": str(t.get("expected_output") or ""),
                "due": str(t.get("due") or ""),
            }
            create_action(
                conn,
                agent,
                str(t.get("task")),
                novel_id=novel_id,
                session_id=session_id,
                meeting_id=meeting_id,
                detail=detail,
            )
            created += 1
    return {"ok": True, "created": created}
