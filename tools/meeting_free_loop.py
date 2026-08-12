"""Free-meeting event loop: per-session queue, heartbeat and recovery.

Events (user message, agent message, approval result, cold timer) are
submitted without blocking; one daemon worker per session processes them in
order. Speech scheduling lives in `meeting_speaker` (step 2.2); this module
owns the queue, the lock, the heartbeat and fail-closed recovery.
"""

from __future__ import annotations

import queue
import threading
from collections import deque
from datetime import datetime

from novel_editorial import db
from novel_editorial.services import audit


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class FreeMeetingLoop:
    """进程内事件循环。重启后事件丢失，但消息持久；running 会话由
    `scan_interrupted` 显式标记，避免「看似在跑实则无线程」的假绿灯。"""

    def __init__(self, db_path=""):
        self._db_path = db_path
        self._queues = {}
        self._workers = {}
        self._seen_events = {}
        self._locks = {}
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

    # ── 内部 ────────────────────────────────────────────────

    def _run_worker(self, session_id):
        q = self._queues.get(session_id)
        if q is None:
            return
        lock = self._locks.setdefault(session_id, threading.Lock())
        while True:
            try:
                event = q.get(timeout=1.0)
            except queue.Empty:
                # 冷场计时由调度器接入（步骤 2.3）；此处保持 worker 存活。
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
            audit.log(
                conn,
                "meeting",
                "free_event",
                target_type="session",
                target_id=session_id,
                detail={"kind": event.get("kind") or "user_message"},
            )
            conn.commit()
        finally:
            conn.close()

    def stop(self, session_id):
        """停止指定会话的 worker（用于测试与收尾）。"""
        with self._guard:
            q = self._queues.get(int(session_id))
            worker = self._workers.get(int(session_id))
        if q is not None:
            q.put(None)
        if worker is not None:
            worker.join(timeout=3)
        with self._guard:
            self._queues.pop(int(session_id), None)
            self._workers.pop(int(session_id), None)


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
