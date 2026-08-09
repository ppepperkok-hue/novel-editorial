"""实时监控 Web API：路由层，业务逻辑在 novel_pipeline.services。"""

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

from novel_pipeline import config, db  # noqa: E402
from novel_pipeline.services import (  # noqa: E402
    agents as agents_service,
    audit as audit_service,
    control as control_service,
    dashboard as dashboard_service,
    ending as ending_service,
    meeting_session as meeting_service,
    misc as misc_service,
    n8n as n8n_service,
)

_SNAPSHOT = {}
_SNAPSHOT_LOCK = threading.Lock()
_SNAPSHOT_THREAD_STARTED = False


def _snapshot_loop(db_path):
    while True:
        try:
            conn = db.connect(db_path)
            try:
                snapshot = {
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "workflows": {
                        "daily": n8n_service.workflow_status(config.N8N_WORKFLOW_DAILY),
                        "weekly": n8n_service.workflow_status(config.N8N_WORKFLOW_WEEKLY),
                    },
                    "executions": n8n_service.executions()[:5],
                    "issues": len(misc_service.load_alerts(conn)["issues"]),
                    "monthly_cost": dashboard_service.load_summary(conn)["monthly_cost"],
                }
            finally:
                conn.close()
            with _SNAPSHOT_LOCK:
                _SNAPSHOT["data"] = snapshot
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
        return {"executions": n8n_service.executions()}
    return {"error": f"未知端点 {name}"}


def make_handler(db_path):
    _ensure_snapshot_thread(db_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            try:
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
                        novel_id = int(qs["novel_id"][0]) if qs.get("novel_id") else None
                        self._json({"chapters": dashboard_service.load_chapters(conn, novel_id)})
                    finally:
                        conn.close()
                elif path == "/api/chapter_content":
                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        chapter_id = int(qs["chapter_id"][0]) if qs.get("chapter_id") else None
                        if chapter_id is None:
                            self._json({"error": "chapter_id required"}, status=400)
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
                        session_id = int(qs["id"][0]) if qs.get("id") else None
                        if session_id is None:
                            self._json({"error": "id required"}, status=400)
                        else:
                            session = meeting_service.get_session(conn, session_id)
                            self._json(session if session else {"error": "session not found"}, status=200 if session else 404)
                    finally:
                        conn.close()
                elif path == "/api/ai_taste":
                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        chapter_id = int(qs["chapter_id"][0]) if qs.get("chapter_id") else None
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
                        limit = int(qs["limit"][0]) if qs.get("limit") else 100
                        self._json({"logs": audit_service.list_logs(conn, category, limit)})
                    finally:
                        conn.close()
                elif path == "/api/characters/evolution":
                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        novel_id = int(qs["novel_id"][0]) if qs.get("novel_id") else 0
                        self._json(misc_service.character_evolution(conn, novel_id))
                    finally:
                        conn.close()
                elif path == "/api/diaries":
                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        agent = qs["agent"][0] if qs.get("agent") else None
                        dtype = qs["type"][0] if qs.get("type") else None
                        limit = int(qs["limit"][0]) if qs.get("limit") else 100
                        self._json({"diaries": misc_service.list_diaries(conn, agent, dtype, limit)})
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
                self._json({"error": str(exc)}, status=500)

        def do_POST(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path not in (
                "/api/control",
                "/api/agents",
                "/api/ending/confirm",
                "/api/ending/bind",
                "/api/diaries/update",
                "/api/agent_states/update",
                "/api/meetings/start",
                "/api/meetings/advance",
            ):
                self.send_error(404, "Not Found")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                payload = json.loads(raw.decode("utf-8") or "{}")
                conn = db.connect(db_path)
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
                elif parsed.path == "/api/diaries/update":
                    try:
                        result = misc_service.update_diary(conn, payload.get("id"), payload.get("content"))
                    finally:
                        conn.close()
                elif parsed.path == "/api/agent_states/update":
                    try:
                        result = misc_service.update_state(
                            conn, payload.get("agent"), payload.get("novel_id"), payload.get("mood")
                        )
                    finally:
                        conn.close()
                elif parsed.path == "/api/meetings/start":
                    conn.close()
                    result = meeting_service.start_session_async(payload.get("topic"))
                elif parsed.path == "/api/meetings/advance":
                    try:
                        result = meeting_service.advance_session(
                            conn, payload.get("session_id"), payload.get("instruction", "")
                        )
                    finally:
                        conn.close()
                self._json(result)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                return
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, status=500)

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
            self.send_header("Access-Control-Allow-Origin", "*")
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
            if not str(target).startswith(str(root)):
                return False
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                return False
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return True

        def _sse(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
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

        def _json(self, payload, status=200):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    return Handler


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="novel-pipeline 实时监控面板")
    ap.add_argument("--db", default="demo.db")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.db))
    print(f"监控面板：http://{args.host}:{args.port}/  （Ctrl+C 停止）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
