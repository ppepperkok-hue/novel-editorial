"""Interactive topic meetings: run round by round, pausing for user input."""

import json
import threading
import time
from datetime import datetime

import novel_pipeline
from novel_pipeline import config
from novel_pipeline.services import audit
from tools import agent_meeting, architect_weekly

_MEETING_LOCK = threading.Lock()
FINISH_TOKEN = "__FINISH__"
MAX_ROUNDS = 20


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_session(conn, topic, novel_id=0):
    if not topic or not str(topic).strip():
        return {"ok": False, "error": "topic 不能为空"}
    if not novel_id:
        row = conn.execute("SELECT id FROM novels ORDER BY id DESC LIMIT 1").fetchone()
        novel_id = row["id"] if row else 0
    cur = conn.execute(
        "INSERT INTO meeting_sessions(kind,topic,status,novel_id,created_at,updated_at) "
        "VALUES('topic',?,?,?,?,?)",
        (str(topic).strip(), "running", novel_id, _now(), _now()),
    )
    conn.commit()
    session_id = cur.lastrowid
    audit.log(conn, "meeting", "start_session", target_type="session", target_id=session_id, detail={"topic": topic})
    return {"ok": True, "session_id": session_id}


def get_session(conn, session_id):
    row = conn.execute("SELECT * FROM meeting_sessions WHERE id=?", (session_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    try:
        d["transcript"] = json.loads(d["transcript"] or "[]")
    except (TypeError, json.JSONDecodeError):
        d["transcript"] = []
    try:
        d["attendees"] = json.loads(d["attendees"] or "[]")
    except (TypeError, json.JSONDecodeError):
        d["attendees"] = []
    if d.get("report"):
        try:
            d["report"] = json.loads(d["report"])
        except (TypeError, json.JSONDecodeError):
            pass
    return d


def get_active_session(conn):
    """Latest in-progress topic session (running or awaiting input)."""
    row = conn.execute(
        "SELECT id FROM meeting_sessions "
        "WHERE status IN ('running','awaiting_input') "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return get_session(conn, row["id"])


def advance_session(conn, session_id, instruction="", finish=False):
    row = conn.execute(
        "SELECT id, status FROM meeting_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if row is None:
        return {"ok": False, "error": "session not found"}
    if row["status"] != "awaiting_input":
        return {"ok": False, "error": f"当前状态不是等待输入（{row['status']}）"}
    if finish:
        instruction = FINISH_TOKEN
    conn.execute(
        "UPDATE meeting_sessions SET instruction=?, status='running', updated_at=? WHERE id=?",
        (str(instruction or "").strip(), _now(), session_id),
    )
    conn.commit()
    return {"ok": True}


def run_session(session_id):
    """Background worker: executes rounds, pauses for user instructions."""
    conn = None
    try:
        conn = novel_pipeline.db.connect(config.DB_PATH)
        with _MEETING_LOCK:
            _run_locked(conn, session_id)
    finally:
        if conn is not None:
            conn.close()


def _run_locked(conn, session_id):
    try:
        row = conn.execute("SELECT * FROM meeting_sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            return
        novel_id = row["novel_id"]
        topic = row["topic"]
        materials = architect_weekly.build_materials(
            conn, novel_id, allow_empty=(novel_id == 0)
        )
        if materials is None:
            conn.execute("UPDATE meeting_sessions SET status='failed' WHERE id=?", (session_id,))
            conn.commit()
            return
        agent_meeting.materials = materials
        agent_meeting.topic = topic
        attendees, topics, pick = agent_meeting.chair_pick(conn, novel_id, dry_run=False)
        if topic:
            topics = [topic] + [t for t in (topics or []) if t != topic]
        conn.execute(
            "UPDATE meeting_sessions SET attendees=?, current_round=0, updated_at=? WHERE id=?",
            (json.dumps(attendees, ensure_ascii=False), _now(), session_id),
        )
        conn.commit()

        transcript = []
        round_no = 0
        while True:
            round_no += 1
            conn.execute(
                "UPDATE meeting_sessions SET current_round=?, status='running', updated_at=? WHERE id=?",
                (round_no, _now(), session_id),
            )
            conn.commit()
            instruction = ""
            if round_no > 1:
                # read user instruction placed while awaiting
                r = conn.execute(
                    "SELECT instruction FROM meeting_sessions WHERE id=?", (session_id,)
                ).fetchone()
                instruction = r["instruction"] if r else ""
            for agent in attendees:
                speech = agent_meeting.round_speech(
                    conn,
                    novel_id,
                    agent,
                    materials,
                    transcript,
                    round_no,
                    dry_run=False,
                    instruction=instruction if round_no > 1 else "",
                )
                transcript.append({"round": round_no, "agent": agent, "speech": speech})
                conn.execute(
                    "UPDATE meeting_sessions SET transcript=?, updated_at=? WHERE id=?",
                    (json.dumps(transcript, ensure_ascii=False), _now(), session_id),
                )
                conn.commit()
            conn.execute(
                "UPDATE meeting_sessions SET status='awaiting_input', instruction='', updated_at=? WHERE id=?",
                (_now(), session_id),
            )
            conn.commit()
            # wait for the user: continue to the next round or finish
            while True:
                r = conn.execute(
                    "SELECT status, instruction FROM meeting_sessions WHERE id=?", (session_id,)
                ).fetchone()
                if r["status"] == "cancelled":
                    return
                if r["status"] == "running":
                    break
                time.sleep(2)
            if r["instruction"] == FINISH_TOKEN or round_no >= MAX_ROUNDS:
                break
        # summary
        report = agent_meeting.chair_summary(conn, novel_id, attendees, topics, transcript, dry_run=False)
        report["attendees"] = attendees
        report["topics"] = topics
        report["date"] = _now()
        report["kind"] = "topic"
        report.setdefault("decisions", {"blueprint_updates": [], "volume_goal_adjust": ""})
        report.setdefault("disagreements", [])
        report.setdefault("action_items", [])
        report.setdefault("discussion_summary", "")

        conn.execute(
            "INSERT INTO weekly_meetings(held_at,novel_id,attendees,topics,report,status,kind) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                report["date"],
                novel_id,
                json.dumps(attendees, ensure_ascii=False),
                json.dumps(topics, ensure_ascii=False),
                json.dumps(report, ensure_ascii=False),
                "completed",
                "topic",
            ),
        )
        # meeting memory for each attendee
        for agent in attendees:
            speech = next((s["speech"] for s in transcript if s["agent"] == agent), {})
            conn.execute(
                "INSERT INTO agent_diaries(agent,novel_id,diary_type,content,created_at) "
                "VALUES(?,?,?,?,datetime('now','localtime'))",
                (
                    agent,
                    novel_id,
                    "meeting",
                    json.dumps(
                        {"topic": topic, "my_speech": speech, "conclusions": report.get("action_items", []), "date": report["date"]},
                        ensure_ascii=False,
                    ),
                ),
            )
        conn.execute(
            "UPDATE meeting_sessions SET status='finished', report=?, transcript=?, updated_at=? WHERE id=?",
            (json.dumps(report, ensure_ascii=False), json.dumps(transcript, ensure_ascii=False), _now(), session_id),
        )
        conn.commit()
        audit.log(conn, "meeting", "finish_session", target_type="session", target_id=session_id, detail={"topic": topic})
    except Exception:  # noqa: BLE001
        if conn is not None:
            try:
                conn.execute("UPDATE meeting_sessions SET status='failed' WHERE id=?", (session_id,))
                conn.commit()
            except Exception:  # noqa: BLE001
                pass


def start_session_async(topic, novel_id=0):
    """Create a session and run it in a background thread."""
    conn = novel_pipeline.db.connect(config.DB_PATH)
    try:
        result = create_session(conn, topic, novel_id)
    finally:
        conn.close()
    if not result["ok"]:
        return result
    threading.Thread(target=run_session, args=(result["session_id"],), daemon=True).start()
    return result
