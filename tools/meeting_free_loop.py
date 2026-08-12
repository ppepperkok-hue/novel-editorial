"""Free-meeting event loop: per-session queue, heartbeat and recovery.

Events (user message, agent message, approval result, cold timer) are
submitted without blocking; one daemon worker per session processes them in
order. Speech scheduling lives in `meeting_speaker` (step 2.2); this module
owns the queue, the lock, the heartbeat and fail-closed recovery.
"""

from __future__ import annotations

import json
import queue
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from novel_editorial import db
from novel_editorial.services import audit
from tools import app_settings, meeting_events, meeting_executor, meeting_speaker
from tools import meeting_interactions


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class FreeMeetingLoop:
    """进程内事件循环。重启后事件丢失，但消息持久；running 会话由
    `scan_interrupted` 显式标记，避免「看似在跑实则无线程」的假绿灯。"""

    def __init__(self, db_path="", dry_run=False):
        self._db_path = db_path
        self._dry_run = dry_run
        self._queues = {}
        self._workers = {}
        self._seen_events = {}
        self._locks = {}
        self._running = {}
        self._running_guard = threading.Lock()
        self._futures = {}
        self._pool = ThreadPoolExecutor(max_workers=3)
        self._guard = threading.Lock()

    # ── 对外接口 ────────────────────────────────────────────

    def submit_event(self, session_id, event):
        """投递事件，立即返回（不阻塞）。同 event_id 只处理一次。"""
        session_id = int(session_id)
        event = dict(event or {})
        event_id = str(event.get("event_id") or "")
        with self._guard:
            if event_id:
                seen = self._seen_events.setdefault(session_id, deque(maxlen=100))
                if event_id in seen:
                    return {"ok": True, "duplicate": True}
                seen.append(event_id)
            q = self._queues.setdefault(session_id, queue.Queue())
            if session_id not in self._workers or not self._workers[session_id].is_alive():
                worker = threading.Thread(
                    target=self._run_worker,
                    args=(session_id,),
                    name=f"free-meeting-{session_id}",
                    daemon=True,
                )
                self._workers[session_id] = worker
                worker.start()
        q.put(event)
        return {"ok": True, "duplicate": False}

    def is_processing(self, session_id):
        with self._guard:
            return bool(self._locks.get(int(session_id)))

    def running_agents(self, session_id):
        with self._running_guard:
            return set(self._running.get(int(session_id), set()))

    # ── 内部 ────────────────────────────────────────────────

    def _run_worker(self, session_id):
        q = self._queues.get(session_id)
        if q is None:
            return
        lock = self._locks.setdefault(session_id, threading.Lock())
        while True:
            try:
                conn = db.connect(self._db_path)
                try:
                    cold_s = app_settings.get_int(
                        conn, "meeting_free_cold_s", 30
                    )
                finally:
                    conn.close()
                event = q.get(timeout=max(0.2, cold_s))
            except queue.Empty:
                self._process_cold(session_id)
                continue
            if event is None:
                return
            with lock:
                self._process_event(session_id, event)

    def _process_event(self, session_id, event):
        conn = db.connect(self._db_path)
        try:
            conn.execute(
                "UPDATE meeting_sessions SET heartbeat_at=?, updated_at=? WHERE id=?",
                (_now(), _now(), session_id),
            )
            session = conn.execute(
                "SELECT * FROM meeting_sessions WHERE id=?", (session_id,)
            ).fetchone()
            if not session or session["status"] not in ("running", "awaiting_input"):
                return
            audit.log(
                conn,
                "meeting",
                "free_event",
                target_type="session",
                target_id=session_id,
                detail={"kind": event.get("kind") or "user_message"},
            )
            meeting_interactions.expire_interactions(conn)
            self._maybe_compress(conn, session)
            self._schedule_speakers(conn, session, event)
            conn.commit()
        finally:
            conn.close()

    def _process_cold(self, session_id):
        conn = db.connect(self._db_path)
        try:
            session = conn.execute(
                "SELECT * FROM meeting_sessions WHERE id=?", (session_id,)
            ).fetchone()
            if not session or session["status"] != "running":
                return
            candidates = self._cold_candidates(conn, session)
            if not candidates:
                return
            audit.log(
                conn,
                "meeting",
                "cold_timer",
                target_type="session",
                target_id=session_id,
                detail={"agents": [c["agent"] for c in candidates]},
            )
            self._run_candidates(conn, session, candidates, event={"kind": "cold_timer"})
            conn.commit()
        finally:
            conn.close()

    def _cold_candidates(self, conn, session):
        attendees = self._attendees(session)
        busy = self.running_agents(session["id"])
        cooldown_s = app_settings.get_int(conn, "meeting_free_cooldown_s", 60)
        if "eic" in attendees and "eic" not in busy:
            return [{"agent": "eic", "reason": "cold_chair", "score": 0, "mandatory": True}]
        # 轮转：选最近发言最久的 agent（无发言记录者优先）。
        rows = conn.execute(
            "SELECT from_agent, MAX(id) AS last_id FROM meeting_messages "
            "WHERE session_id=? AND kind='speech' GROUP BY from_agent",
            (session["id"],),
        ).fetchall()
        spoke = {r["from_agent"] for r in rows}
        for agent in attendees:
            if agent not in busy and agent not in spoke:
                return [{"agent": agent, "reason": "cold_rotate", "score": 0, "mandatory": True}]
        if rows:
            oldest = min(rows, key=lambda r: r["last_id"])
            if oldest["from_agent"] not in busy:
                return [
                    {
                        "agent": oldest["from_agent"],
                        "reason": "cold_rotate",
                        "score": 0,
                        "mandatory": True,
                    }
                ]
        return []

    def _schedule_speakers(self, conn, session, event):
        if self._breaker_hit(conn, session):
            audit.log(
                conn,
                "meeting",
                "breaker",
                target_type="session",
                target_id=session["id"],
                detail={"reason": "meeting free budget exhausted"},
            )
            return
        attendees = self._attendees(session)
        if not attendees:
            return
        k = app_settings.get_int(conn, "meeting_free_candidate_k", 2)
        cooldown_s = app_settings.get_int(conn, "meeting_free_cooldown_s", 60)
        candidates = meeting_speaker.candidate_speakers(
            conn,
            session,
            event,
            attendees,
            busy=self.running_agents(session["id"]),
            k=k,
            cooldown_s=cooldown_s,
        )
        candidates = self._maybe_add_chair(conn, session, candidates)
        if not candidates:
            audit.log(
                conn,
                "meeting",
                "no_candidate",
                target_type="session",
                target_id=session["id"],
                detail={"kind": event.get("kind") or "user_message"},
            )
            return
        self._run_candidates(conn, session, candidates, event)

    def _maybe_compress(self, conn, session):
        """历史超限且无摘要时生成一次摘要（幂等：有摘要即跳过）。"""
        if session["meeting_summary"]:
            return False
        row = conn.execute(
            "SELECT COALESCE(SUM(LENGTH(body)),0) AS s FROM meeting_messages "
            "WHERE session_id=? AND status='active'",
            (session["id"],),
        ).fetchone()
        if int(row["s"] or 0) <= 30000:
            return False
        summary = meeting_executor.summarize_history(
            conn, session, dry_run=self._dry_run
        )
        conn.execute(
            "UPDATE meeting_sessions SET meeting_summary=?, updated_at=? WHERE id=?",
            (summary, _now(), session["id"]),
        )
        conn.execute(
            "UPDATE meeting_messages SET compressed_at=? "
            "WHERE session_id=? AND compressed_at=''",
            (_now(), session["id"]),
        )
        audit.log(
            conn,
            "meeting",
            "history_compressed",
            target_type="session",
            target_id=session["id"],
            detail={"summary_len": len(summary)},
        )
        return True

    def _maybe_add_chair(self, conn, session, candidates):
        """每 N 条发言主席插话一次（N 可配，默认 12）。"""
        every_n = app_settings.get_int(conn, "meeting_free_chair_every_n", 12)
        if every_n <= 0:
            return candidates
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM meeting_messages "
            "WHERE session_id=? AND kind='speech'",
            (session["id"],),
        ).fetchone()["c"]
        if count == 0 or count % every_n != 0:
            return candidates
        busy = self.running_agents(session["id"])
        if "eic" not in busy and "eic" not in {c["agent"] for c in candidates}:
            candidates.append(
                {"agent": "eic", "reason": "chair_every_n", "score": 0, "mandatory": True}
            )
        return candidates

    def _breaker_hit(self, conn, session):
        max_calls = app_settings.get_int(conn, "meeting_free_max_calls", 300)
        max_cost = app_settings.get_float(conn, "meeting_free_max_cost", 20.0)
        speech = conn.execute(
            "SELECT COUNT(*) AS c FROM meeting_messages "
            "WHERE session_id=? AND kind='speech'",
            (session["id"],),
        ).fetchone()["c"]
        if speech >= max_calls:
            return True
        # cost_logs 无 session_id，按 novel_id 限定范围（仍可能混入该书的
        # 日更成本，但避免把其他作品的成本算进本次会议）。
        if session["created_at"]:
            cost_row = conn.execute(
                "SELECT COALESCE(SUM(cost),0) AS s FROM cost_logs "
                "WHERE created_at >= ? AND novel_id=?",
                (session["created_at"], session["novel_id"]),
            ).fetchone()
            if float(cost_row["s"] or 0) >= max_cost:
                return True
        return False

    def _run_candidates(self, conn, session, candidates, event):
        busy = set()
        with self._running_guard:
            busy = set(self._running.get(int(session["id"]), set()))
        for c in candidates:
            if c["agent"] in busy:
                continue
            with self._running_guard:
                self._running.setdefault(int(session["id"]), set()).add(c["agent"])
            session_id = int(session["id"])
            future = self._pool.submit(
                self._speak, session_id, c["agent"], event
            )
            with self._running_guard:
                self._futures.setdefault(session_id, set()).add(future)
            future.add_done_callback(
                lambda f, sid=session_id: self._drop_future(sid, f)
            )

    def _drop_future(self, session_id, future):
        with self._running_guard:
            self._futures.get(session_id, set()).discard(future)

    def _speak(self, session_id, agent, event):
        try:
            conn = db.connect(self._db_path)
            try:
                result = meeting_executor.reply_to_mention(
                    conn,
                    session_id,
                    agent,
                    event,
                    dry_run=self._dry_run,
                )
                self._broadcast_result(conn, session_id, agent, result)
            finally:
                conn.close()
        finally:
            with self._running_guard:
                self._running.get(session_id, set()).discard(agent)

    def _broadcast_result(self, conn, session_id, agent, result):
        hub = meeting_events.get_hub()
        if result.get("ok") and result.get("spoken"):
            hub.publish(
                session_id,
                {
                    "type": "message",
                    "session_id": session_id,
                    "message_id": result.get("message_id"),
                    "agent": agent,
                    "speech": result.get("speech"),
                },
            )
        interaction_id = result.get("interaction_id")
        if interaction_id:
            row = conn.execute(
                "SELECT * FROM pending_interactions WHERE id=?", (interaction_id,)
            ).fetchone()
            if row:
                hub.publish(
                    session_id,
                    {
                        "type": "approval",
                        "session_id": session_id,
                        "interaction": {
                            "id": row["id"],
                            "agent": row["agent"],
                            "kind": row["kind"],
                            "question": str(
                                dict_from_json(row["payload"]).get("question", "")
                            ),
                            "choices": dict_from_json(row["payload"]).get("choices", []),
                            "expires_at": row["expires_at"],
                            "status": row["status"],
                        },
                    },
                )
    def _attendees(self, session):
        try:
            return [
                str(a).replace(".md", "")
                for a in json.loads(session["attendees"] or "[]")
            ]
        except (TypeError, ValueError):
            return []

    def stop(self, session_id):
        """停止指定会话的 worker（用于测试与收尾）。"""
        session_id = int(session_id)
        with self._guard:
            q = self._queues.get(session_id)
            worker = self._workers.get(session_id)
        with self._running_guard:
            futures = list(self._futures.get(session_id, set()))
        if q is not None:
            q.put(None)
        if worker is not None:
            worker.join(timeout=3)
        for future in futures:
            try:
                future.result(timeout=5)
            except Exception:  # noqa: BLE001 - stop must not raise on speaker failure
                pass
        with self._guard:
            self._queues.pop(session_id, None)
            self._workers.pop(session_id, None)
        with self._running_guard:
            self._running.pop(session_id, None)
            self._futures.pop(session_id, None)


_LOOP = None
_LOOP_LOCK = threading.Lock()


def get_loop(db_path=""):
    """进程级单例事件循环。"""
    global _LOOP
    with _LOOP_LOCK:
        if _LOOP is None:
            _LOOP = FreeMeetingLoop(db_path=db_path)
        return _LOOP


def scan_interrupted(conn):
    """启动时把 status='running' 的 free 会话标记 interrupted（fail-closed）。
    返回受影响会话数。"""
    rows = conn.execute(
        "SELECT id FROM meeting_sessions WHERE mode='free' AND status='running'"
    ).fetchall()
    if not rows:
        return 0
    for row in rows:
        conn.execute(
            "UPDATE meeting_sessions SET status='interrupted', updated_at=? WHERE id=?",
            (_now(), row["id"]),
        )
        audit.log(
            conn,
            "meeting",
            "session_interrupted",
            target_type="session",
            target_id=row["id"],
            detail={"reason": "process restart"},
        )
    conn.commit()
    return len(rows)


def dict_from_json(text):
    import json as _json

    try:
        obj = _json.loads(text or "{}")
        return obj if isinstance(obj, dict) else {}
    except (TypeError, ValueError):
        return {}
