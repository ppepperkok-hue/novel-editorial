"""Interactive topic meetings: run round by round, pausing for user input."""

import json
import threading
import time
from datetime import datetime, timedelta

import novel_pipeline
from novel_pipeline import config
from novel_pipeline.services import audit
from novel_pipeline.services import activity
from tools import agent_meeting, architect_weekly

_MEETING_LOCK = threading.Lock()
FINISH_TOKEN = "__FINISH__"
MAX_ROUNDS = 20
MEETING_TIMEOUT_SECONDS = 60 * 60


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_session(conn, topic, novel_id=0, db_path=""):
    if not topic or not str(topic).strip():
        return {"ok": False, "error": "topic 不能为空"}
    active = get_active_session(conn)
    if active is not None:
        return {
            "ok": False,
            "error": f"已有会议进行中（#{active['id']}），请先结束或关闭当前会议",
        }
    if not novel_id:
        row = conn.execute("SELECT id FROM novels ORDER BY id DESC LIMIT 1").fetchone()
        novel_id = row["id"] if row else 0
    cur = conn.execute(
        "INSERT INTO meeting_sessions(kind,topic,status,novel_id,db_path,heartbeat_at,created_at,updated_at) "
        "VALUES('topic',?,?,?,?,?,?,?)",
        (
            str(topic).strip(),
            "running",
            novel_id,
            str(db_path or ""),
            _now(),
            _now(),
            _now(),
        ),
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
    """Latest in-progress topic session (running or awaiting input).

    Stale ``running`` sessions whose heartbeat is older than 10 minutes are
    considered dead (their background thread died, e.g. after a web_api
    restart) and are marked failed so they cannot block new meetings.
    ``awaiting_input`` sessions are left alone: the thread is parked waiting
    for the user, which is a legitimate state.
    """
    row = conn.execute(
        "SELECT id FROM meeting_sessions WHERE status='running' ORDER BY id DESC LIMIT 5"
    ).fetchone()
    if row is not None:
        session = get_session(conn, row["id"])
        cutoff = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        if session.get("heartbeat_at", "") < cutoff:
            conn.execute(
                "UPDATE meeting_sessions SET status='failed', updated_at=? WHERE id=?",
                (_now(), row["id"]),
            )
            conn.commit()
        else:
            return session
    parked = conn.execute(
        "SELECT id FROM meeting_sessions WHERE status='awaiting_input' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if parked is not None:
        return get_session(conn, parked["id"])
    return None


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


def cancel_session(conn, session_id):
    """Cancel a running/parked session; the background thread stops at the
    next round boundary (awaiting_input write is guarded against cancelled)."""
    cur = conn.execute(
        "UPDATE meeting_sessions SET status='cancelled', updated_at=? "
        "WHERE id=? AND status IN ('running','awaiting_input')",
        (_now(), session_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        return {"ok": False, "error": "session not found or already finished"}
    audit.log(
        conn,
        "meeting",
        "cancel_session",
        target_type="session",
        target_id=session_id,
    )
    return {"ok": True}


def _resolve_speakers(conn, novel_id, materials, transcript, topic, attendees, round_no):
    """S13: open mode lets the chair pick who speaks next; rounds mode keeps
    everyone. Any failure degrades to everyone speaking (never stalls)."""
    from novel_pipeline import config  # noqa: PLC0415

    if config.MEETING_MODE != "open":
        return list(attendees or [])
    if round_no <= 1:
        return list(attendees or [])
    try:
        direct = agent_meeting.chair_direct(
            conn, novel_id, materials, transcript, topic
        )
        if not direct.get("ok") or not direct.get("continue"):
            return []
        picked = [a for a in (direct.get("next_agents") or []) if a in attendees]
        return picked or list(attendees or [])
    except Exception:  # noqa: BLE001 - degrade to everyone
        return list(attendees or [])


def _collect_topic_requests(conn, novel_id=0):
    """Agenda items agents asked to discuss (kind='topic_request' mail)."""
    scope = "AND ref_novel_id=?" if novel_id else ""
    params = (int(novel_id),) if novel_id else ()
    rows = conn.execute(
        f"SELECT from_agent, subject, body FROM agent_messages "
        f"WHERE kind='topic_request' AND status!='archived' {scope} "
        "ORDER BY id DESC LIMIT 8",
        params,
    ).fetchall()
    return [
        {
            "from": r["from_agent"],
            "title": str(r["body"] or r["subject"] or "")[:120],
        }
        for r in rows
    ]


def _record_topic_requests(conn, agent, novel_id, speech):
    """Persist an agent's suggested agenda items as topic_request mail."""
    requests = speech.get("topic_requests") if isinstance(speech, dict) else None
    if not isinstance(requests, list) or not requests:
        return
    from tools import mailroom  # noqa: PLC0415

    for item in requests:
        text = str(item or "").strip()
        if not text:
            continue
        mailroom.send(
            conn,
            agent,
            "eic",
            body=text[:400],
            subject="议题提议",
            kind="topic_request",
            novel_id=novel_id or 0,
        )


def run_session(session_id, db_path=""):
    """Background worker: executes rounds, pauses for user instructions."""
    conn = None
    try:
        # Use the database the session was created on; never fall back to a
        # hardcoded demo.db lookup that silently misses sessions in other DBs.
        conn = novel_pipeline.db.connect(db_path or config.DB_PATH)
        with _MEETING_LOCK:
            _run_locked(conn, session_id)
    finally:
        if conn is not None:
            conn.close()


def _run_locked(conn, session_id):
    started_at = time.time()
    try:
        row = conn.execute("SELECT * FROM meeting_sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            return
        novel_id = row["novel_id"]
        topic = row["topic"]
        if time.time() - started_at > MEETING_TIMEOUT_SECONDS:
            _fail_timeout(conn, session_id, 0)
            return
        materials = architect_weekly.build_materials(
            conn, novel_id, allow_empty=(novel_id == 0)
        )
        if materials is None:
            conn.execute("UPDATE meeting_sessions SET status='failed' WHERE id=?", (session_id,))
            conn.commit()
            return
        attendees, topics, pick = agent_meeting.chair_pick(
            conn, novel_id, dry_run=False, materials=materials, topic=topic
        )
        if topic:
            topics = [topic] + [t for t in (topics or []) if t != topic]
        topic_requests = _collect_topic_requests(conn, novel_id)
        if topic_requests:
            topics = topics + [f"（议题提议·{r['from']}）{r['title']}" for r in topic_requests]
        conn.execute(
            "UPDATE meeting_sessions SET attendees=?, current_round=0, updated_at=? WHERE id=?",
            (json.dumps(attendees, ensure_ascii=False), _now(), session_id),
        )
        conn.commit()

        transcript = []
        compressed = {"summary": "", "until": 0}
        round_no = 0
        while True:
            if time.time() - started_at > MEETING_TIMEOUT_SECONDS:
                _fail_timeout(conn, session_id, round_no)
                return
            round_no += 1
            conn.execute(
                "UPDATE meeting_sessions SET current_round=?, status='running', updated_at=? WHERE id=?",
                (round_no, _now(), session_id),
            )
            conn.commit()
            # Incrementally compress history once per round (round 2+):
            # the memory agent merges new speeches into the running summary.
            if len(transcript) > 2 and len(transcript) > compressed["until"]:
                new_part = transcript[compressed["until"]:]
                try:
                    compressed = agent_meeting.compress_history(
                        conn, novel_id, new_part,
                        prev_summary=compressed["summary"], dry_run=False,
                    )
                    compressed["until"] = len(transcript)
                except Exception as exc:  # noqa: BLE001
                    audit.log(
                        conn,
                        "meeting",
                        "compress_history_failed",
                        target_type="session",
                        target_id=session_id,
                        detail={"round": round_no, "error": str(exc)[:300]},
                    )
            instruction = ""
            if round_no > 1:
                # read user instruction placed while awaiting
                r = conn.execute(
                    "SELECT instruction FROM meeting_sessions WHERE id=?", (session_id,)
                ).fetchone()
                instruction = r["instruction"] if r else ""
            speakers = _resolve_speakers(
                conn, novel_id, materials, transcript, topic, attendees, round_no
            )
            if not speakers:
                break
            for agent in speakers:
                conn.execute(
                    "UPDATE meeting_sessions SET current_agent=?, heartbeat_at=? WHERE id=?",
                    (agent, _now(), session_id),
                )
                conn.commit()
                try:
                    speech = agent_meeting.round_speech(
                        conn,
                        novel_id,
                        agent,
                        materials,
                        transcript,
                        round_no,
                        dry_run=False,
                        instruction=instruction if round_no > 1 else "",
                        topic=topic,
                        compressed_history=compressed["summary"],
                    )
                except Exception as exc:  # noqa: BLE001
                    # One attendee failing must not kill the whole meeting:
                    # record a visible placeholder + audit trace and continue.
                    speech = {
                        "speech": f"（{agent} 本轮没有发言，已跳过）",
                        "weekly_summary": "",
                        "feelings": "",
                        "opinion": "",
                        "concerns": [],
                        "proposals": [],
                        "priority": "低",
                        "_error": str(exc)[:200],
                    }
                    audit.log(
                        conn,
                        "meeting",
                        "round_speech_failed",
                        target_type="session",
                        target_id=session_id,
                        detail={"agent": agent, "round": round_no, "error": str(exc)[:300]},
                    )
                finally:
                    conn.execute(
                        "UPDATE meeting_sessions SET current_agent='', heartbeat_at=? WHERE id=?",
                        (_now(), session_id),
                    )
                    conn.commit()
                if isinstance(speech, dict) and isinstance(speech.get("promises"), list):
                    from tools import promises  # noqa: PLC0415

                    promises.record_promises(
                        conn, agent, novel_id or 0, speech["promises"], source="meeting"
                    )
                _record_topic_requests(conn, agent, novel_id or 0, speech)
                transcript.append({"round": round_no, "agent": agent, "speech": speech})
                activity.log_activity(
                    conn,
                    agent,
                    novel_id,
                    "meeting_speech",
                    f"会议第 {round_no} 轮发言",
                    {
                        "session_id": session_id,
                        "round": round_no,
                        "speech": str(speech.get("speech") or "")[:500],
                        "proposals": speech.get("proposals") or [],
                    },
                )
                conn.execute(
                    "UPDATE meeting_sessions SET transcript=?, updated_at=? WHERE id=?",
                    (json.dumps(transcript, ensure_ascii=False), _now(), session_id),
                )
                conn.commit()
            cur = conn.execute(
                "UPDATE meeting_sessions SET status='awaiting_input', instruction='', "
                "updated_at=? WHERE id=? AND status != 'cancelled'",
                (_now(), session_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                # cancelled while speaking: stop instead of parking forever
                return
            if round_no >= MAX_ROUNDS:
                # Hard cap: auto-finish instead of waiting forever for a click.
                break
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
            if r["instruction"] == FINISH_TOKEN:
                break
        # summary
        report = agent_meeting.chair_summary(
            conn, novel_id, attendees, topics, transcript, dry_run=False,
            materials=materials,
        )
        report["attendees"] = attendees
        report["topics"] = topics
        report["date"] = _now()
        report["kind"] = "topic"
        report.setdefault("decisions", {"blueprint_updates": [], "volume_goal_adjust": ""})
        report.setdefault("disagreements", [])
        report.setdefault("action_items", [])
        report.setdefault("discussion_summary", "")

        cur = conn.execute(
            "INSERT INTO weekly_meetings(held_at,novel_id,attendees,topics,report,status,kind,session_id) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                report["date"],
                novel_id,
                json.dumps(attendees, ensure_ascii=False),
                json.dumps(topics, ensure_ascii=False),
                json.dumps(report, ensure_ascii=False),
                "completed",
                "topic",
                session_id,
            ),
        )
        conn.commit()
        weekly_id = cur.lastrowid
        activity.log_activity(
            conn,
            "eic",
            novel_id,
            "meeting_summary",
            "主席总结会议",
            {
                "session_id": session_id,
                "meeting_id": weekly_id,
                "summary": str(report.get("discussion_summary") or "")[:400],
                "action_items": len(report.get("action_items") or []),
            },
        )
        # Post-meeting tasks: each attendee turns the conclusions into their
        # own actionable backlog (flash call per agent, rule fallback on error).
        try:
            action_result = activity.generate_post_meeting_actions(
                conn,
                session_id,
                weekly_id,
                novel_id,
                attendees,
                report,
                transcript,
                dry_run=False,
            )
            audit.log(
                conn,
                "meeting",
                "post_meeting_actions",
                target_type="session",
                target_id=session_id,
                detail={"created": action_result.get("created", 0)},
            )
        except Exception as exc:  # noqa: BLE001
            audit.log(
                conn,
                "meeting",
                "post_meeting_actions_failed",
                target_type="session",
                target_id=session_id,
                detail={"error": str(exc)[:300]},
            )
            conn.commit()
        # Persist decisions (blueprints / cover_prompt / next_book) for topic
        # meetings too; skip when no novel exists yet (new-book topic meeting).
        if novel_id:
            try:
                from tools.apply_architect import apply_report  # noqa: PLC0415

                apply_report(conn, novel_id, report)
            except Exception as exc:  # noqa: BLE001
                audit.log(
                    conn,
                    "meeting",
                    "apply_report_failed",
                    target_type="session",
                    target_id=session_id,
                    detail={"error": str(exc)},
                )
                conn.commit()
        else:
            # New-book meeting without a novel yet: turn decisions.next_book
            # into a planning novel so auto-create on Fanqie has a target.
            try:
                from tools.apply_architect import create_planning_from_next_book  # noqa: PLC0415

                book_result = create_planning_from_next_book(
                    conn, report, cover_prompt=report.get("cover_prompt", "")
                )
                if book_result.get("ok"):
                    audit.log(
                        conn,
                        "meeting",
                        "planning_book_created",
                        target_type="novel",
                        target_id=str(book_result.get("id") or ""),
                        detail={"duplicate": bool(book_result.get("duplicate"))},
                    )
            except Exception as exc:  # noqa: BLE001
                audit.log(
                    conn,
                    "meeting",
                    "planning_book_failed",
                    target_type="session",
                    target_id=session_id,
                    detail={"error": str(exc)[:300]},
                )
                conn.commit()
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
    except Exception as exc:  # noqa: BLE001
        if conn is not None:
            try:
                agent_at_fail = conn.execute(
                    "SELECT current_agent FROM meeting_sessions WHERE id=?",
                    (session_id,),
                ).fetchone()
                conn.execute("UPDATE meeting_sessions SET status='failed' WHERE id=?", (session_id,))
                audit.log(
                    conn,
                    "meeting",
                    "session_failed",
                    target_type="session",
                    target_id=session_id,
                    detail={
                        "error": f"{exc.__class__.__name__}: {exc}",
                        "agent": (agent_at_fail["current_agent"] if agent_at_fail else "") or "",
                    },
                )
                conn.commit()
            except Exception:  # noqa: BLE001
                try:
                    conn.execute(
                        "UPDATE meeting_sessions SET current_agent='', heartbeat_at=? WHERE id=?",
                        (_now(), session_id),
                    )
                    conn.commit()
                except Exception:  # noqa: BLE001
                    pass
                pass


def _fail_timeout(conn, session_id, round_no):
    conn.execute(
        "UPDATE meeting_sessions SET status='failed', updated_at=? WHERE id=?",
        (_now(), session_id),
    )
    audit.log(
        conn,
        "meeting",
        "session_timeout",
        target_type="session",
        target_id=session_id,
        detail={"round": round_no, "timeout_seconds": MEETING_TIMEOUT_SECONDS},
    )
    conn.commit()


def start_session_async(topic, novel_id=0, db_path=None):
    """Create a session and run it in a background thread."""
    conn = novel_pipeline.db.connect(db_path or config.DB_PATH)
    try:
        result = create_session(conn, topic, novel_id, db_path=db_path or "")
    finally:
        conn.close()
    if not result["ok"]:
        return result
    threading.Thread(
        target=run_session,
        args=(result["session_id"], db_path or ""),
        daemon=True,
    ).start()
    return result
