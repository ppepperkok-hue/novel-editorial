"""实时监控 Web API：路由层，业务逻辑在 novel_editorial.services。"""

import argparse
import json
import mimetypes
import os
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import config, db  # noqa: E402
from novel_editorial.llm_client import cached_env  # noqa: E402
from novel_editorial.services import (  # noqa: E402
    agents as agents_service,
    audit as audit_service,
    control as control_service,
    dashboard as dashboard_service,
    ending as ending_service,
    meeting_session as meeting_service,
    misc as misc_service,
)

_SNAPSHOT = {}
_SNAPSHOT_LOCK = threading.Lock()
_SNAPSHOT_THREAD_STARTED = False
_SSE_COUNT = 0
_SSE_COUNT_LOCK = threading.Lock()
_MAX_SSE = 8


def _parse_int(value, default=0):
    """Coerce a query/payload value to int; never raise on garbage input."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _panel_token():
    """Optional bearer token from ~/.n8n/.env; empty means token auth is off."""
    return (cached_env().get("PANEL_TOKEN") or "").strip()


def _origin_allowed(origin, port):
    if not origin:
        return True
    allowed = {
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
    }
    return origin in allowed


def _build_snapshot(conn):
    """Snapshot payload backed by local state only (no n8n dependency)."""
    from tools import daily_runs  # noqa: PLC0415

    return {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "executions": daily_runs.local_executions(conn)[:5],
        "issues": len(misc_service.load_alerts(conn)["issues"]),
        "monthly_cost": dashboard_service.load_summary(conn)["monthly_cost"],
    }


def _snapshot_loop(db_path):
    while True:
        try:
            conn = db.connect(db_path)
            try:
                snapshot = _build_snapshot(conn)
            finally:
                conn.close()
            with _SNAPSHOT_LOCK:
                _SNAPSHOT["data"] = snapshot
        except Exception as exc:  # noqa: BLE001
            try:
                config.ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
                with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
                    f.write(
                        f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 快照线程异常："
                        f"{exc.__class__.__name__}: {exc}\n"
                    )
            except Exception:  # noqa: BLE001
                pass
        time.sleep(5)


def _ensure_snapshot_thread(db_path):
    global _SNAPSHOT_THREAD_STARTED
    with _SNAPSHOT_LOCK:
        if not _SNAPSHOT_THREAD_STARTED:
            _SNAPSHOT_THREAD_STARTED = True
            threading.Thread(target=_snapshot_loop, args=(db_path,), daemon=True).start()


def _endpoint(conn, name):
    if name == "summary":
        return dashboard_service.load_summary(conn)
    if name == "novels":
        return dashboard_service.load_novels(conn)
    if name == "publish_logs":
        return dashboard_service.load_publish_logs(conn)
    if name == "alerts":
        return misc_service.load_alerts(conn)
    if name == "reader_stats":
        return misc_service.load_reader_stats()
    if name == "hot_topics":
        return misc_service.load_hot_topics()
    if name == "agents":
        return {"agents": agents_service.agents_list()}
    if name == "cost":
        return dashboard_service.cost_summary(conn)
    if name == "executions":
        from tools import daily_runs  # noqa: PLC0415

        return {"executions": daily_runs.local_executions(conn)}
    return {"error": f"未知端点 {name}"}


def make_handler(db_path):
    _ensure_snapshot_thread(db_path)
    try:
        conn = db.connect(db_path)
        try:
            from tools import daily_runs  # noqa: PLC0415

            daily_runs.recover_stale_runs(conn)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - startup recovery must never block serving
        pass

    def _get_daily_runs(self, parsed):
        from tools import daily_runs  # noqa: PLC0415

        conn = db.connect(db_path)
        try:
            qs = parse_qs(parsed.query)
            limit = _parse_int(qs.get("limit", ["30"])[0], 30)
            sync_result = daily_runs.sync_from_n8n(conn, limit=limit)
            payload = {"runs": daily_runs.list_runs(conn, limit=limit)}
            if sync_result.get("error"):
                payload["sync_error"] = sync_result["error"]
            self._json(payload)
        finally:
            conn.close()

    def _get_daily_runs_detail(self, parsed):
        from tools import daily_runs  # noqa: PLC0415

        conn = db.connect(db_path)
        try:
            qs = parse_qs(parsed.query)
            run_id = qs.get("run_id", [""])[0] or ""
            if not run_id:
                self._json({"error": "run_id required"}, status=400)
            else:
                detail = daily_runs.run_detail(conn, run_id)
                if detail is None:
                    self._json({"error": "run not found"}, status=404)
                else:
                    self._json({"run": detail})
        finally:
            conn.close()

    def _get_flow(self, parsed):
        from tools import flow_graph  # noqa: PLC0415

        conn = db.connect(db_path)
        try:
            self._json(flow_graph.build_flow(conn))
        finally:
            conn.close()

    def _get_export_flow(self, parsed):
        from tools import export_flow_html  # noqa: PLC0415

        conn = db.connect(db_path)
        try:
            body = export_flow_html.render_html(conn).encode("utf-8")
        finally:
            conn.close()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header(
            "Content-Disposition",
            'attachment; filename="pipeline-flow.html"',
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _get_mailbox(self, parsed):
        from tools import mailroom  # noqa: PLC0415

        qs = parse_qs(parsed.query)
        conn = db.connect(db_path)
        try:
            result = mailroom.list_messages(
                conn,
                agent=qs.get("agent", [""])[0] or None,
                novel_id=_parse_int(qs.get("novel_id", ["0"])[0]),
                status=qs.get("status", [""])[0] or None,
                limit=_parse_int(qs.get("limit", ["50"])[0], 50),
            )
        finally:
            conn.close()
        self._json(result)

    def _get_relations(self, parsed):
        from tools import editorial_state  # noqa: PLC0415

        qs = parse_qs(parsed.query)
        conn = db.connect(db_path)
        try:
            result = editorial_state.list_relations(
                conn,
                agent=qs.get("agent", [""])[0] or None,
                novel_id=_parse_int(qs.get("novel_id", ["0"])[0]),
                limit=_parse_int(qs.get("limit", ["50"])[0], 50),
            )
        finally:
            conn.close()
        self._json(result)

    def _get_memories(self, parsed):
        from tools import editorial_state  # noqa: PLC0415

        qs = parse_qs(parsed.query)
        conn = db.connect(db_path)
        try:
            result = editorial_state.list_memories(
                conn,
                agent=qs.get("agent", [""])[0] or None,
                novel_id=_parse_int(qs.get("novel_id", ["0"])[0]),
                category=qs.get("category", [""])[0] or None,
                limit=_parse_int(qs.get("limit", ["50"])[0], 50),
            )
        finally:
            conn.close()
        self._json(result)

    def _get_promises(self, parsed):
        from tools import editorial_state  # noqa: PLC0415

        qs = parse_qs(parsed.query)
        conn = db.connect(db_path)
        try:
            result = editorial_state.list_promises(
                conn,
                agent=qs.get("agent", [""])[0] or None,
                novel_id=_parse_int(qs.get("novel_id", ["0"])[0]),
                status=qs.get("status", [""])[0] or None,
                limit=_parse_int(qs.get("limit", ["50"])[0], 50),
            )
        finally:
            conn.close()
        self._json(result)

    def _get_editorial_overview(self, parsed):
        from novel_editorial.services import editorial as editorial_service  # noqa: PLC0415

        conn = db.connect(db_path)
        try:
            self._json(editorial_service.build_overview(conn))
        finally:
            conn.close()

    def _post_claim_action(self, parsed, payload):
        from novel_editorial.services import activity as activity_service  # noqa: PLC0415

        conn = db.connect(db_path)
        try:
            result = activity_service.claim_action(
                conn,
                _parse_int(payload.get("id")),
                str(payload.get("agent") or ""),
                novel_id=_parse_int(payload.get("novel_id")),
            )
        finally:
            conn.close()
        self._json(result)

    # Route registry: new endpoints go here instead of the legacy if/elif
    # chains in do_GET/do_POST. Old endpoints migrate over incrementally.
    GET_ROUTES = {
        "/api/daily_runs": _get_daily_runs,
        "/api/daily_runs/detail": _get_daily_runs_detail,
        "/api/flow": _get_flow,
        "/api/export/flow": _get_export_flow,
        "/api/agents/mailbox": _get_mailbox,
        "/api/agents/relations": _get_relations,
        "/api/agents/memories": _get_memories,
        "/api/agents/promises": _get_promises,
        "/api/editorial/overview": _get_editorial_overview,
    }
    POST_ROUTES = {
        "/api/agent_actions/claim": _post_claim_action,
    }

    class Handler(BaseHTTPRequestHandler):
        def _guard(self):
            """Reject browser CSRF and unsafe non-browser writes."""
            port = self.server.server_port
            origin = self.headers.get("Origin") or ""
            if origin:
                if origin == "null":
                    # file:// fallback page is read-only; writes from a null
                    # origin (sandboxed iframe etc.) are always rejected.
                    if self.command == "POST":
                        return False, "cross-origin request denied"
                elif not _origin_allowed(origin, port):
                    return False, "cross-origin request denied"
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if self.command == "POST" and ctype == "text/plain":
                return False, "text/plain requests denied"
            if self.command == "POST":
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except (TypeError, ValueError):
                    length = 0
                if length > 5 * 1024 * 1024:
                    return False, "request body too large"
            token = _panel_token()
            # Token is a write-path guard only: browsers (Origin present) and
            # read-only GETs stay usable without it. A forged local Origin
            # header is out of scope for a localhost trust model.
            if self.command == "POST" and not origin and token:
                auth = self.headers.get("Authorization") or ""
                if auth != "Bearer " + token:
                    return False, "missing panel token"
            return True, ""

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                ok, reason = self._guard()
                if not ok:
                    self._json({"error": reason}, status=403)
                    return
                handler = GET_ROUTES.get(path)
                if handler is not None:
                    handler(self, parsed)
                    return
                if path in ("/", "/index.html"):
                    self._serve_index()
                elif path == "/api/dashboard":
                    conn = db.connect(db_path)
                    try:
                        self._json(dashboard_service.build_payload(conn))
                    finally:
                        conn.close()
                elif path == "/api/chapters":
                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        if qs.get("novel_id"):
                            novel_id = _parse_int(qs["novel_id"][0], None)
                            if novel_id is None:
                                self._json(
                                    {"error": "novel_id must be an integer"},
                                    status=400,
                                )
                                return
                        else:
                            novel_id = None
                        self._json({"chapters": dashboard_service.load_chapters(conn, novel_id)})
                    finally:
                        conn.close()
                elif path == "/api/chapter_content":
                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        chapter_id = _parse_int(qs["chapter_id"][0], None) if qs.get("chapter_id") else None
                        if chapter_id is None:
                            self._json(
                                {"error": "chapter_id required and must be an integer"},
                                status=400,
                            )
                        else:
                            row = conn.execute(
                                "SELECT chapter_id, content, updated_at "
                                "FROM chapter_content WHERE chapter_id=?",
                                (chapter_id,),
                            ).fetchone()
                            self._json(
                                dict(row)
                                if row
                                else {"chapter_id": chapter_id, "content": "", "updated_at": ""}
                            )
                    finally:
                        conn.close()
                elif path == "/api/events":
                    self._sse()
                elif path == "/api/export/novels":
                    conn = db.connect(db_path)
                    try:
                        self._json(misc_service.export_novels(conn))
                    finally:
                        conn.close()
                elif path == "/api/meetings":
                    conn = db.connect(db_path)
                    try:
                        self._json({"meetings": misc_service.load_meetings(conn)})
                    finally:
                        conn.close()
                elif path == "/api/meetings/session":
                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        session_id = _parse_int(qs["id"][0], None) if qs.get("id") else None
                        if session_id is None:
                            self._json({"error": "id required"}, status=400)
                        else:
                            session = meeting_service.get_session(conn, session_id)
                            self._json(session if session else {"error": "session not found"}, status=200 if session else 404)
                    finally:
                        conn.close()
                elif path == "/api/meetings/active":
                    conn = db.connect(db_path)
                    try:
                        self._json(
                            {"session": meeting_service.get_active_session(conn)}
                        )
                    finally:
                        conn.close()
                elif path == "/api/ai_taste":
                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        chapter_id = _parse_int(qs["chapter_id"][0], None) if qs.get("chapter_id") else None
                        if chapter_id is None:
                            self._json({"error": "chapter_id required"}, status=400)
                        else:
                            self._json(misc_service.ai_taste(conn, chapter_id))
                    finally:
                        conn.close()
                elif path == "/api/ending/status":
                    conn = db.connect(db_path)
                    try:
                        self._json(ending_service.ending_status(conn))
                    finally:
                        conn.close()
                elif path == "/api/audit":
                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        category = qs["category"][0] if qs.get("category") else None
                        limit = _parse_int(qs["limit"][0], 100) if qs.get("limit") else 100
                        date_from = qs["from"][0] if qs.get("from") else ""
                        date_to = qs["to"][0] if qs.get("to") else ""
                        self._json(
                            {
                                "logs": audit_service.list_logs(
                                    conn, category, limit, date_from, date_to
                                )
                            }
                        )
                    finally:
                        conn.close()
                elif path == "/api/characters/evolution":
                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        novel_id = _parse_int(qs["novel_id"][0], 0) if qs.get("novel_id") else 0
                        self._json(misc_service.character_evolution(conn, novel_id))
                    finally:
                        conn.close()
                elif path == "/api/novel_knowledge/history":
                    from tools import novel_knowledge  # noqa: PLC0415

                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        knowledge_id = _parse_int(qs.get("knowledge_id", ["0"])[0], 0)
                        if not knowledge_id:
                            self._json({"error": "knowledge_id required"}, status=400)
                        else:
                            self._json(
                                {"items": novel_knowledge.history(conn, knowledge_id)}
                            )
                    finally:
                        conn.close()
                elif path == "/api/novel_knowledge/graph":
                    from tools import novel_knowledge  # noqa: PLC0415

                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        novel_id = _parse_int(qs.get("novel_id", ["0"])[0], 0)
                        if not novel_id:
                            self._json({"error": "novel_id required"}, status=400)
                        else:
                            self._json(novel_knowledge.graph(conn, novel_id))
                    finally:
                        conn.close()
                elif path == "/api/novel_knowledge":
                    from tools import novel_knowledge  # noqa: PLC0415

                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        novel_id = _parse_int(qs["novel_id"][0], 0) if qs.get("novel_id") else 0
                        category = qs.get("category", [""])[0] or None
                        if not novel_id:
                            self._json({"error": "novel_id required"}, status=400)
                        else:
                            self._json(
                                {"items": novel_knowledge.get(conn, novel_id, category=category)}
                            )
                    finally:
                        conn.close()
                elif path == "/api/diaries":
                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        agent = qs["agent"][0] if qs.get("agent") else None
                        dtype = qs["type"][0] if qs.get("type") else None
                        limit = _parse_int(qs["limit"][0], 100) if qs.get("limit") else 100
                        self._json({"diaries": misc_service.list_diaries(conn, agent, dtype, limit)})
                    finally:
                        conn.close()
                elif path == "/api/activity":
                    from novel_editorial.services import activity as activity_service  # noqa: PLC0415

                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        agent = qs["agent"][0] if qs.get("agent") else None
                        day = qs["day"][0] if qs.get("day") else None
                        limit = _parse_int(qs["limit"][0], 300) if qs.get("limit") else 300
                        self._json(
                            {
                                "items": activity_service.list_activity(
                                    conn, agent=agent, day=day, limit=limit
                                ),
                                "days": activity_service.activity_days(
                                    conn, agent=agent
                                ),
                            }
                        )
                    finally:
                        conn.close()
                elif path == "/api/agent_actions":
                    from novel_editorial.services import activity as activity_service  # noqa: PLC0415

                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        agent = qs["agent"][0] if qs.get("agent") else None
                        status = qs["status"][0] if qs.get("status") else None
                        limit = _parse_int(qs["limit"][0], 200) if qs.get("limit") else 200
                        self._json(
                            {
                                "actions": activity_service.list_actions(
                                    conn, agent=agent, status=status, limit=limit
                                )
                            }
                        )
                    finally:
                        conn.close()
                elif path == "/api/agent_states":
                    conn = db.connect(db_path)
                    try:
                        self._json({"states": misc_service.list_states(conn)})
                    finally:
                        conn.close()
                elif path == "/api/control":
                    conn = db.connect(db_path)
                    try:
                        self._json(control_service.load_control(conn))
                    finally:
                        conn.close()
                elif path in (
                    "/api/summary",
                    "/api/novels",
                    "/api/publish_logs",
                    "/api/alerts",
                    "/api/reader_stats",
                    "/api/hot_topics",
                    "/api/agents",
                    "/api/cost",
                    "/api/executions",
                ):
                    conn = db.connect(db_path)
                    try:
                        self._json(_endpoint(conn, path.split("/")[-1]))
                    finally:
                        conn.close()
                else:
                    if self._serve_static(path):
                        return
                    self.send_error(404, "Not Found")
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                return
            except Exception as exc:  # noqa: BLE001
                try:
                    config.ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
                    with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
                        f.write(
                            f"[{datetime.now():%Y-%m-%d %H:%M:%S}] API {self.command} "
                            f"{path} 异常：{exc.__class__.__name__}: {exc}\n"
                        )
                except Exception:  # noqa: BLE001
                    pass
                self._json({"ok": False, "error": "internal error"}, status=500)

        def do_POST(self):  # noqa: N802
            parsed = urlparse(self.path)
            ok, reason = self._guard()
            if not ok:
                self._json({"error": reason}, status=403)
                return
            if parsed.path not in POST_ROUTES and parsed.path not in (
                "/api/control",
                "/api/agents",
                "/api/ending/confirm",
                "/api/ending/bind",
                "/api/ending/create_book",
                "/api/ending/delete_book",
                "/api/diaries/update",
                "/api/agent_states/update",
                "/api/agent_actions/update",
                "/api/agent_actions/create",
                "/api/meetings/start",
                "/api/meetings/advance",
                "/api/meetings/cancel",
                "/api/agent/run",
                "/api/knowledge",
                "/api/knowledge_drafts",
                "/api/novel_knowledge",
            ):
                self.send_error(404, "Not Found")
                return
            conn = None
            try:
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except (TypeError, ValueError):
                    self._json(
                        {"ok": False, "error": "invalid Content-Length"},
                        status=400,
                    )
                    return
                if length < 0:
                    self._json(
                        {"ok": False, "error": "invalid Content-Length"},
                        status=400,
                    )
                    return
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8") or "{}")
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._json(
                        {"ok": False, "error": "invalid JSON body"},
                        status=400,
                    )
                    return
                if not isinstance(payload, dict):
                    self._json(
                        {"ok": False, "error": "request body must be a JSON object"},
                        status=400,
                    )
                    return
                handler = POST_ROUTES.get(parsed.path)
                if handler is not None:
                    handler(self, parsed, payload)
                    return
                conn = db.connect(db_path)
                http_status = 200
                if parsed.path == "/api/control":
                    try:
                        result = control_service.handle_control(conn, payload)
                    finally:
                        conn.close()
                elif parsed.path == "/api/agents":
                    action = payload.get("action")
                    if action == "save":
                        result = agents_service.agent_save(payload, conn)
                    elif action == "deploy":
                        result = agents_service.agent_deploy(conn)
                    else:
                        result = {"ok": False, "error": f"unknown action {action}"}
                    conn.close()
                elif parsed.path == "/api/ending/confirm":
                    try:
                        result = ending_service.confirm_next_book(conn, payload.get("novel_id"))
                    finally:
                        conn.close()
                elif parsed.path == "/api/ending/bind":
                    try:
                        result = ending_service.bind_book(
                            conn,
                            payload.get("novel_id"),
                            payload.get("book_id"),
                            payload.get("volume_id", ""),
                        )
                    finally:
                        conn.close()
                elif parsed.path == "/api/ending/create_book":
                    from tools import create_book  # noqa: PLC0415

                    try:
                        result = create_book.create_book_on_fanqie(
                            conn, payload.get("novel_id")
                        )
                    finally:
                        conn.close()
                elif parsed.path == "/api/ending/delete_book":
                    from tools import delete_book  # noqa: PLC0415

                    try:
                        result = delete_book.delete_book_on_fanqie(
                            conn,
                            payload.get("novel_id"),
                            confirm=bool(payload.get("confirm")),
                        )
                    finally:
                        conn.close()
                elif parsed.path == "/api/diaries/update":
                    try:
                        result = misc_service.update_diary(conn, payload.get("id"), payload.get("content"))
                    finally:
                        conn.close()
                elif parsed.path == "/api/agent_states/update":
                    try:
                        novel_id = int(payload.get("novel_id") or 0)
                    except (TypeError, ValueError):
                        conn.close()
                        self._json(
                            {"ok": False, "error": "novel_id must be an integer"},
                            status=400,
                        )
                        return
                    try:
                        result = misc_service.update_state(
                            conn, payload.get("agent"), novel_id, payload.get("mood")
                        )
                    finally:
                        conn.close()
                    if not result.get("ok"):
                        self._json(result, status=400)
                        return
                elif parsed.path == "/api/agent_actions/update":
                    from novel_editorial.services import activity as activity_service  # noqa: PLC0415

                    try:
                        result = activity_service.update_action(
                            conn,
                            _parse_int(payload.get("id"), 0),
                            status=payload.get("status"),
                            result=payload.get("result"),
                            task=payload.get("task"),
                        )
                    finally:
                        conn.close()
                elif parsed.path == "/api/agent_actions/create":
                    from novel_editorial.services import activity as activity_service  # noqa: PLC0415

                    try:
                        session_id = int(payload.get("session_id") or 0)
                        meeting_id = int(payload.get("meeting_id") or 0)
                        novel_id = int(payload.get("novel_id") or 0)
                    except (TypeError, ValueError):
                        conn.close()
                        self._json(
                            {
                                "ok": False,
                                "error": "session_id, meeting_id and novel_id must be integers",
                            },
                            status=400,
                        )
                        return
                    try:
                        result = activity_service.create_action(
                            conn,
                            payload.get("agent"),
                            payload.get("task"),
                            novel_id=novel_id,
                            session_id=session_id,
                            meeting_id=meeting_id,
                            detail=payload.get("detail") or {},
                        )
                    finally:
                        conn.close()
                elif parsed.path == "/api/meetings/start":
                    conn.close()
                    result = meeting_service.start_session_async(
                        payload.get("topic"),
                        db_path=str(db_path),
                        kind=payload.get("kind") or "topic",
                    )
                elif parsed.path == "/api/meetings/advance":
                    try:
                        result = meeting_service.advance_session(
                            conn,
                            payload.get("session_id"),
                            payload.get("instruction", ""),
                            finish=bool(payload.get("finish")),
                        )
                    finally:
                        conn.close()
                elif parsed.path == "/api/meetings/cancel":
                    try:
                        result = meeting_service.cancel_session(
                            conn, payload.get("session_id")
                        )
                    finally:
                        conn.close()
                elif parsed.path == "/api/agent/run":
                    from tools import agent_tool_loop  # noqa: PLC0415

                    task = str(payload.get("task") or "")
                    if not task:
                        msgs = payload.get("messages") or []
                        task = "\n".join(
                            str(m.get("content") or "")
                            for m in msgs
                            if isinstance(m, dict) and m.get("role") == "user"
                        )
                    agent = str(payload.get("agent") or "").strip()
                    if not agent:
                        result = {"ok": False, "error": "agent required"}
                        conn.close()
                    else:
                        # Inject the agent's pending post-meeting actions so
                        # daily-run agents actually see and execute meeting
                        # conclusions (best effort; logging failure must not
                        # block the call).
                        try:
                            from novel_editorial.services import activity as activity_service  # noqa: PLC0415

                            stem_file = agent_tool_loop._resolve_agent_file(agent)
                            stem = stem_file.stem if stem_file is not None else agent
                            novel_id = _parse_int(payload.get("novel_id"), 0)
                            pending = []
                            if stem:
                                for a in activity_service.list_actions(
                                    conn, agent=stem, status="pending", limit=10
                                ):
                                    if novel_id in (0, int(a.get("novel_id") or 0)):
                                        pending.append(a)
                            if pending:
                                lines = []
                                for a in pending:
                                    due = (a.get("detail") or {}).get("due") or ""
                                    lines.append(
                                        f"- {a['task']}" + (f"（期限：{due}）" if due else "")
                                    )
                                task = (
                                    task.rstrip()
                                    + "\n\n[我的待办行动项]（来自会议结论，请落实；"
                                    "完成后在结果中简述进展）\n"
                                    + "\n".join(lines)
                                )
                        except Exception:  # noqa: BLE001
                            pass
                        loop_result = agent_tool_loop.run(
                            agent,
                            task,
                            temperature=payload.get("temperature"),
                            max_tokens=_parse_int(payload.get("max_tokens"), 1600),
                            target_words=payload.get("target_words"),
                            novel_id=payload.get("novel_id"),
                            db_path=str(db_path),
                            model=payload.get("model"),
                        )
                        if loop_result.get("ok"):
                            result = {
                                "ok": True,
                                "choices": [
                                    {"message": {"content": loop_result["text"]}}
                                ],
                                "usage": loop_result.get("usage") or {},
                                "used_knowledge": loop_result.get("used_knowledge") or [],
                                "model": loop_result.get("model"),
                                "attempts": loop_result.get("attempts"),
                                "degraded": loop_result.get("degraded"),
                            }
                        else:
                            result = {
                                "ok": False,
                                "error": loop_result.get("error") or "agent tool loop failed",
                            }
                    conn.close()
                elif parsed.path == "/api/knowledge":
                    from novel_editorial.services import knowledge as knowledge_service  # noqa: PLC0415

                    try:
                        action = payload.get("action") or "list"
                        if action == "list":
                            result = {"ok": True, "knowledge": knowledge_service.list_knowledge()}
                        elif action == "read":
                            item = knowledge_service.read_knowledge(str(payload.get("file") or ""))
                            result = {"ok": bool(item), "item": item}
                        elif action == "save":
                            file = str(payload.get("file") or "")
                            meta = payload.get("meta") or {}
                            body = str(payload.get("body") or "")
                            if not file or not body.strip():
                                result = {"ok": False, "error": "file and body required"}
                            else:
                                try:
                                    item = knowledge_service.write_knowledge(
                                        file, dict(meta), body
                                    )
                                except ValueError as exc:
                                    result = {"ok": False, "error": str(exc)}
                                    http_status = 400
                                else:
                                    audit_service.log(
                                        conn, "knowledge", "save",
                                        target_type="knowledge", target_id=file,
                                        detail={"title": meta.get("title")},
                                    )
                                    result = {"ok": True, "item": item}
                        else:
                            result = {"ok": False, "error": f"unknown action {action}"}
                    finally:
                        conn.close()
                elif parsed.path == "/api/knowledge_drafts":
                    from novel_editorial.services import knowledge as knowledge_service  # noqa: PLC0415

                    try:
                        action = payload.get("action") or "list"
                        if action == "list":
                            result = {
                                "ok": True,
                                "drafts": knowledge_service.list_drafts(
                                    conn, payload.get("status")
                                ),
                            }
                        elif action in ("accept", "reject", "deprecate"):
                            draft_id = _parse_int(payload.get("id"), 0)
                            status = {"accept": "accepted", "reject": "rejected", "deprecate": "deprecated"}[action]
                            if action == "accept":
                                # write into a knowledge package chosen by the draft
                                rows = conn.execute(
                                    "SELECT * FROM knowledge_drafts WHERE id=?", (draft_id,)
                                ).fetchall()
                                if not rows:
                                    result = {"ok": False, "error": "draft not found"}
                                else:
                                    d = dict(rows[0])
                                    agents = []
                                    try:
                                        agents = json.loads(d.get("agents") or "[]")
                                    except ValueError:
                                        agents = []
                                    kind = d.get("kind") or "lesson"
                                    file = (
                                        "lessons.md"
                                        if kind in ("lesson", "deprecation")
                                        else "custom-knowledge.md"
                                    )
                                    meta = {
                                        "title": d["title"],
                                        "type": "craft",
                                        "agents": agents,
                                        "source": d.get("source") or "agent-draft",
                                    }
                                    try:
                                        knowledge_service.write_knowledge(
                                            file, meta, d["content"]
                                        )
                                    except ValueError as exc:
                                        result = {"ok": False, "error": str(exc)}
                                        http_status = 400
                                    else:
                                        audit_service.log(
                                            conn, "knowledge", "accept_draft",
                                            target_type="knowledge_draft", target_id=draft_id,
                                            detail={"file": file, "title": d["title"]},
                                        )
                                        knowledge_service.update_draft_status(conn, draft_id, "accepted")
                                        result = {"ok": True, "file": file}
                            else:
                                ok = knowledge_service.update_draft_status(conn, draft_id, status)
                                result = {"ok": ok, "error": None if ok else "draft not found or not in draft state"}
                        elif action == "distill":
                            from tools import distill_lessons  # noqa: PLC0415

                            result = distill_lessons.distill_latest(
                                payload.get("meeting_id"),
                                payload.get("session_id"),
                                db_path=str(db_path),
                            )
                        else:
                            result = {"ok": False, "error": f"unknown action {action}"}
                    finally:
                        conn.close()
                elif parsed.path == "/api/novel_knowledge":
                    from tools import novel_knowledge  # noqa: PLC0415

                    try:
                        action = payload.get("action") or "list"
                        novel_id = _parse_int(payload.get("novel_id"), 0)
                        if action == "list":
                            result = {
                                "ok": True,
                                "items": novel_knowledge.get(
                                    conn, novel_id, category=payload.get("category")
                                ),
                            }
                        elif action == "upsert":
                            try:
                                meta = novel_knowledge.upsert_ex(
                                    conn,
                                    novel_id,
                                    str(payload.get("category") or ""),
                                    str(payload.get("entity") or ""),
                                    str(payload.get("content") or ""),
                                    source_chapter=payload.get("source_chapter"),
                                    change_note=str(payload.get("change_note") or ""),
                                    check_similar=True,
                                )
                            except ValueError as exc:
                                result = {"ok": False, "error": str(exc)}
                            else:
                                audit_service.log(
                                    conn, "knowledge", "novel_knowledge_upsert",
                                    target_type="novel", target_id=str(novel_id),
                                    detail={
                                        "category": payload.get("category"),
                                        "entity": meta.get("entity"),
                                        "merged_into": meta.get("merged_into"),
                                    },
                                )
                                result = {
                                    "ok": bool(meta.get("id")),
                                    "id": meta.get("id"),
                                    "entity": meta.get("entity"),
                                    "merged_into": meta.get("merged_into"),
                                    "similar": meta.get("similar") or [],
                                }
                        else:
                            result = {"ok": False, "error": f"unknown action {action}"}
                    finally:
                        conn.close()
                self._json(result, status=http_status)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:  # noqa: BLE001
                        pass
                return
            except Exception as exc:  # noqa: BLE001
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    config.ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
                    with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
                        f.write(
                            f"[{datetime.now():%Y-%m-%d %H:%M:%S}] API POST "
                            f"{parsed.path} 异常：{exc.__class__.__name__}: {exc}\n"
                        )
                except Exception:  # noqa: BLE001
                    pass
                self._json({"ok": False, "error": "internal error"}, status=500)

        def _serve_index(self):
            dist = config.ROOT / "webapp" / "dist"
            if dist.exists() and self._serve_static("/index.html"):
                return
            index = config.ROOT / "web" / "index.html"
            if not index.exists():
                self.send_error(404, "index.html missing")
                return
            data = index.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            origin = self.headers.get("Origin") or ""
            if origin and _origin_allowed(origin, self.server.server_port):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _serve_static(self, path):
            dist = (config.ROOT / "webapp" / "dist").resolve()
            if not dist.exists():
                return False
            rel = path.lstrip("/") or "index.html"
            root = dist
            target = (root / rel).resolve()
            if not target.is_relative_to(root):
                return False
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                return False
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            origin = self.headers.get("Origin") or ""
            if origin and _origin_allowed(origin, self.server.server_port):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return True

        def _sse(self):
            global _SSE_COUNT
            with _SSE_COUNT_LOCK:
                if _SSE_COUNT >= _MAX_SSE:
                    self._json({"error": "too many SSE connections"}, status=503)
                    return
                _SSE_COUNT += 1
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            origin = self.headers.get("Origin") or ""
            if origin and _origin_allowed(origin, self.server.server_port):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            try:
                last = None
                while True:
                    with _SNAPSHOT_LOCK:
                        data = _SNAPSHOT.get("data")
                    if data is not None and data != last:
                        last = data
                        try:
                            self.wfile.write(
                                ("data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode("utf-8")
                            )
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError, OSError):
                            return
                    time.sleep(1)
            finally:
                with _SSE_COUNT_LOCK:
                    _SSE_COUNT -= 1

        def _json(self, payload, status=200):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            origin = self.headers.get("Origin") or ""
            if origin and _origin_allowed(origin, self.server.server_port):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):  # noqa: N802
            self.send_response(403)
            self.end_headers()

        def log_message(self, format, *args):  # noqa: A002
            if args and str(args[0]).startswith(("4", "5")):
                try:
                    import sys as _sys

                    _sys.stderr.write(
                        f"[{datetime.now():%H:%M:%S}] {self.command} {self.path} {args[0]}\n"
                    )
                except Exception:  # noqa: BLE001
                    pass

    return Handler


def _fail_orphan_sessions(db_path):
    """Mark running meetings whose background thread died (e.g. web_api restart)."""
    from datetime import datetime, timedelta

    from novel_editorial import db  # noqa: PLC0415
    from novel_editorial.services.meeting_session import (  # noqa: PLC0415
        _heartbeat_timeout_minutes,
    )

    minutes = _heartbeat_timeout_minutes()
    cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = db.connect(db_path)
        try:
            cur = conn.execute(
                "UPDATE meeting_sessions SET status='failed' "
                "WHERE status='running' AND heartbeat_at < ?",
                (cutoff,),
            )
            conn.commit()
            if cur.rowcount:
                print(f"failed {cur.rowcount} orphan meeting session(s)")
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        print("orphan session cleanup skipped:", str(exc)[:200])


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="novel-editorial 实时监控面板")
    ap.add_argument("--db", default=str(config.DB_PATH))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    if args.host not in ("127.0.0.1", "localhost"):
        raise SystemExit("本机控制台只允许绑定 127.0.0.1，禁止暴露到局域网")
    _fail_orphan_sessions(args.db)
    from novel_editorial.services import reminders  # noqa: PLC0415

    active_db = str(Path(args.db).resolve())
    control_service.set_db_path(active_db)
    reminders.start_worker(active_db)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.db))
    print(f"监控面板：http://{args.host}:{args.port}/  （Ctrl+C 停止）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
