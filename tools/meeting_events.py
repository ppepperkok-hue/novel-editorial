"""In-process event hub for free-meeting live updates (SSE backend).

Each session keeps a set of subscriber queues; `publish` fans an event out to
every subscriber. The hub is process-local, so restarts rely on the frontend
refetching full history (messages table is the source of truth).
"""

from __future__ import annotations

import json
import queue
import threading


class MeetingEventHub:
    def __init__(self, max_per_session=10):
        self._subscribers = {}
        self._max_per_session = max_per_session
        self._guard = threading.Lock()

    def subscribe(self, session_id):
        """注册订阅，返回一个队列（调用方负责读取与退订）。"""
        q = queue.Queue(maxsize=100)
        with self._guard:
            subscribers = self._subscribers.setdefault(int(session_id), set())
            if len(subscribers) >= self._max_per_session:
                return None
            subscribers.add(q)
        return q

    def unsubscribe(self, session_id, q):
        with self._guard:
            subscribers = self._subscribers.get(int(session_id))
            if subscribers is not None:
                subscribers.discard(q)
                if not subscribers:
                    self._subscribers.pop(int(session_id), None)

    def publish(self, session_id, event):
        payload = json.dumps(event, ensure_ascii=False)
        with self._guard:
            subscribers = list(self._subscribers.get(int(session_id), set()))
        for q in subscribers:
            try:
                q.put_nowait(payload)
            except queue.Full:
                # 订阅者消费慢：丢弃该事件（前端重连会拉全量补齐）。
                pass

    def subscriber_count(self, session_id):
        with self._guard:
            return len(self._subscribers.get(int(session_id), set()))


_HUB = None
_HUB_LOCK = threading.Lock()


def get_hub():
    global _HUB
    with _HUB_LOCK:
        if _HUB is None:
            _HUB = MeetingEventHub()
        return _HUB
