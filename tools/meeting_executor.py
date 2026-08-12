"""Free-meeting speech executor: assemble context, call the agent, persist.

One agent's reply to a meeting event. The agent decides whether to speak
(`{"speak": false}` means silence); speech is stored in `meeting_messages`
and every failure is explicit (audit + `no_speech`).
"""

from __future__ import annotations

import json
import sqlite3

from novel_editorial.services import audit
from tools import agent_context, agent_meeting, agent_tool_loop

AGENT_PERSONA = {
    "planner": "文策",
    "guard": "守界",
    "writer": "墨白",
    "editor": "润物",
    "reviewer": "守正",
    "reader": "阿读",
    "memory": "录事",
    "work_meta": "书案",
    "eic": "掌印",
    "ending_judge": "终局",
    "knowledge_keeper": "博闻",
}


def agent_label(agent: str) -> str:
    """人格名（与前端 AGENT_DEFAULT_NAMES 一致），用于会议上下文显示。"""
    return AGENT_PERSONA.get(str(agent or "").replace(".md", ""), str(agent or ""))


def _event_text(event: dict) -> str:
    kind = str(event.get("kind") or "user_message")
    content = str(event.get("content") or "").strip()
    sender = agent_label(event.get("from_agent") or "")
    if kind == "agent_message":
        return f"{sender} 说：{content}"
    if kind == "approval_resolved":
        question = str(event.get("question") or "")
        resolution = str(event.get("resolution") or "")
        return f"审批结果：{resolution}（{question}）"
    if kind == "cold_timer":
        return (
            "会议室安静了一段时间。你可以选择发言推进讨论、提出新议题，"
            "或保持沉默。"
        )
    return f"老板说：{content}"


def build_meeting_user(conn, session, agent, event, tail=20):
    """组装会议发言输入：事件 + 最近历史 + 周记/心情 + 协作快照。"""
    rows = conn.execute(
        "SELECT from_agent, body FROM meeting_messages "
        "WHERE session_id=? AND status='active' ORDER BY id DESC LIMIT ?",
        (session["id"], tail),
    ).fetchall()
    history = list(reversed(rows))
    history_text = "\n".join(
        f"{agent_label(r['from_agent'])}：{r['body']}" for r in history
    ) or "（还没有发言）"

    weekly = agent_meeting.latest_weekly(conn, session["novel_id"], agent)
    weekly_text = ""
    if weekly:
        weekly_text = (
            f"\n我的本周日记：{json.dumps(weekly, ensure_ascii=False)[:600]}"
        )

    snapshot = agent_context.build_context_snapshot(
        conn, agent.replace(".md", ""), session["novel_id"]
    )
    snapshot_text = f"\n{snapshot}" if snapshot else ""

    return (
        f"【会议】{session['topic']}\n"
        f"【事件】{_event_text(event)}\n"
        f"【最近发言】\n{history_text}"
        f"{weekly_text}"
        f"{snapshot_text}\n"
        "请以你的性格自然发言。若你认为此刻不需要开口，只输出 "
        '{"speak": false}。开口则输出 JSON：{"speech": "你的发言"}；'
        "正式提案可扩展为 {\"speech\", \"proposals\", \"priority\"}。"
    )


def parse_speech(raw):
    """解析 LLM 输出。返回 {spoken, speech, structured, reason}。"""
    text = str(raw or "").strip()
    if not text:
        return {"spoken": False, "speech": "", "structured": None, "reason": "empty"}
    candidate = text
    if "```json" in text:
        block = text.split("```json", 1)[1].split("```", 1)[0].strip()
        candidate = block
    try:
        obj = json.loads(candidate)
    except (TypeError, ValueError):
        # 非 JSON：视为自然语言发言（自由会议允许口语化输出）。
        return {"spoken": True, "speech": text, "structured": None}
    if isinstance(obj, dict):
        if obj.get("speak") is False:
            return {"spoken": False, "speech": "", "structured": obj, "reason": "speak_false"}
        speech = (
            obj.get("speech")
            or obj.get("opinion")
            or obj.get("weekly_summary")
            or ""
        )
        speech = str(speech or "").strip()
        if speech:
            return {"spoken": True, "speech": speech, "structured": obj}
        return {"spoken": False, "speech": "", "structured": obj, "reason": "no_content"}
    return {"spoken": True, "speech": str(obj), "structured": None}


def reply_to_mention(conn, session_id, agent, event, dry_run=False, mock_text="", tail=20):
    """一个 agent 对会议事件的发言。失败重试一次，再失败显式留痕。"""
    agent = str(agent or "").replace(".md", "")
    session = conn.execute(
        "SELECT * FROM meeting_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if not session:
        return {"ok": False, "error": "session not found"}

    system = None
    user = None
    raw = None
    last_error = ""
    for attempt in range(2):
        try:
            if system is None:
                system = agent_tool_loop.build_system(agent)[1]
                user = build_meeting_user(conn, session, agent, event, tail=tail)
            ask_result = agent_meeting.ask(
                conn,
                session["novel_id"],
                agent,
                user,
                temperature=0.7,
                dry_run=dry_run,
                mock_text=mock_text,
                max_tokens=1800,
                system_override=system,
            )
            raw = ask_result[0]
            break
        except Exception as exc:  # noqa: BLE001 - explicit retry + audit below
            last_error = f"{exc.__class__.__name__}: {exc}"
            if attempt == 0:
                continue
            audit.log(
                conn,
                "meeting",
                "no_speech",
                target_type="session",
                target_id=session_id,
                detail={"agent": agent, "error": last_error[:300]},
            )
            conn.commit()
            return {
                "ok": False,
                "spoken": False,
                "error": last_error,
            }

    parsed = parse_speech(raw)
    if not parsed["spoken"]:
        audit.log(
            conn,
            "meeting",
            "no_speech",
            target_type="session",
            target_id=session_id,
            detail={"agent": agent, "reason": parsed.get("reason")},
        )
        conn.commit()
        return {"ok": True, "spoken": False, "reason": parsed.get("reason")}

    now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inserted = None
    for _ in range(3):
        seq_row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS s FROM meeting_messages "
            "WHERE session_id=?",
            (session_id,),
        ).fetchone()
        try:
            inserted = conn.execute(
                "INSERT INTO meeting_messages(session_id, novel_id, seq, from_agent, "
                "role, kind, body, mentions, status, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    session["novel_id"],
                    int(seq_row["s"]),
                    agent,
                    "assistant",
                    "speech",
                    parsed["speech"],
                    "[]",
                    "active",
                    now,
                ),
            )
            break
        except sqlite3.IntegrityError:
            # 并发发言竞争同一 seq：重算后重试。
            continue
    if inserted is None:
        audit.log(
            conn,
            "meeting",
            "no_speech",
            target_type="session",
            target_id=session_id,
            detail={"agent": agent, "error": "seq conflict after 3 attempts"},
        )
        conn.commit()
        return {"ok": False, "spoken": False, "error": "seq conflict after 3 attempts"}
    audit.log(
        conn,
        "meeting",
        "speech",
        target_type="session",
        target_id=session_id,
        detail={"agent": agent, "message_id": inserted.lastrowid},
    )
    conn.commit()
    return {
        "ok": True,
        "spoken": True,
        "message_id": inserted.lastrowid,
        "speech": parsed["speech"],
    }
