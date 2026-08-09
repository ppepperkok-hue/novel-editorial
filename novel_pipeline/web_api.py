"""实时监控 Web API：读取 SQLite 与监控产物，供前端轮询展示。

端点：
  /                 监控面板（web/index.html）
  /api/dashboard    汇总负载（一次拉全，前端每 5 秒轮询）
  /api/summary /api/novels /api/chapters /api/publish_logs
  /api/health /api/reader_stats /api/hot_topics /api/alerts
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import data_feedback, db, monitor

WEB_DIR = ROOT / "web"
ALERTS_LOG = ROOT / "alerts.log"
HOT_TOPICS_JSON = ROOT / "hot_topics.json"
READER_CSV = ROOT / "demo_data" / "reader_stats.csv"

N8N_BASE = os.environ.get("N8N_BASE", "http://127.0.0.1:5678")
N8N_WORKFLOW_DAILY = os.environ.get("N8N_WORKFLOW_DAILY", "SkLUnm3uRyBSY84F")
N8N_WORKFLOW_WEEKLY = os.environ.get("N8N_WORKFLOW_WEEKLY", "TAScPjj0Oqtz1uy7")
ALLOWED_SETTINGS = {"daily_enabled", "monthly_budget", "target_words", "style_tweak"}
_N8N_KEY = None


def _load_n8n_env():
    global _N8N_KEY
    if _N8N_KEY is None:
        env_file = Path.home() / ".n8n" / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("N8N_API_KEY="):
                    _N8N_KEY = line.split("=", 1)[1].strip()
        _N8N_KEY = _N8N_KEY or os.environ.get("N8N_API_KEY", "")
    return _N8N_KEY


def n8n_api(method, path, body=None):
    """Call the n8n public API; returns parsed JSON or None on any failure."""
    key = _load_n8n_env()
    if not key:
        return None
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        N8N_BASE + "/api/v1" + path,
        data=data,
        method=method,
        headers={
            "X-N8N-API-KEY": key,
            "Content-Type": "application/json" if data else "text/plain",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _workflow_status(wf_id):
    info = n8n_api("GET", "/workflows/" + wf_id)
    if info is None:
        return {"online": False, "active": None, "last": None}
    last = None
    execs = n8n_api("GET", f"/executions?workflowId={wf_id}&limit=1")
    if isinstance(execs, dict) and isinstance(execs.get("data"), list) and execs["data"]:
        e = execs["data"][0]
        last = {
            "id": e.get("id"),
            "status": e.get("status"),
            "started_at": e.get("startedAt"),
            "stopped_at": e.get("stoppedAt"),
        }
    return {"online": True, "active": bool(info.get("active")), "last": last}


def _load_control(conn):
    from tools.app_settings import get_all  # noqa: PLC0415

    return {
        "settings": get_all(conn),
        "workflows": {
            "daily": _workflow_status(N8N_WORKFLOW_DAILY),
            "weekly": _workflow_status(N8N_WORKFLOW_WEEKLY),
        },
    }


def _handle_control(conn, payload):
    from tools.app_settings import set_many  # noqa: PLC0415

    action = payload.get("action")
    if action == "save_settings":
        values = {
            k: v
            for k, v in (payload.get("settings") or {}).items()
            if k in ALLOWED_SETTINGS
        }
        set_many(conn, values)
        return {"ok": True, "saved": values}
    if action == "request_run":
        set_many(conn, {"manual_run_requested": "1"})
        return {"ok": True, "note": "将在下次定时触发时执行"}
    if action in ("pause", "resume"):
        wf_id = {
            "daily": N8N_WORKFLOW_DAILY,
            "weekly": N8N_WORKFLOW_WEEKLY,
        }.get(payload.get("workflow"))
        if not wf_id:
            return {"ok": False, "error": "workflow must be daily|weekly"}
        endpoint = "deactivate" if action == "pause" else "activate"
        res = n8n_api("POST", f"/workflows/{wf_id}/{endpoint}", body={} if action == "resume" else None)
        return {"ok": res is not None, "response": res}
    return {"ok": False, "error": f"unknown action {action}"}


def _load_summary(conn):
    queries = {
        "novels": "SELECT COUNT(*) c FROM novels",
        "chapters_total": "SELECT COUNT(*) c FROM chapters",
        "chapters_draft": "SELECT COUNT(*) c FROM chapters WHERE status='draft'",
        "chapters_ready": "SELECT COUNT(*) c FROM chapters WHERE status IN ('reviewed','queued')",
        "chapters_published": "SELECT COUNT(*) c FROM chapters WHERE status='published'",
        "quality_total": "SELECT COUNT(*) c FROM quality_reports",
        "quality_passed": "SELECT COUNT(*) c FROM quality_reports WHERE passed=1",
        "publish_failed": "SELECT COUNT(*) c FROM publish_logs WHERE result='failed'",
    }
    summary = {key: conn.execute(sql).fetchone()["c"] for key, sql in queries.items()}
    cost_row = conn.execute(
        "SELECT COALESCE(SUM(cost),0) s FROM cost_logs "
        "WHERE created_at >= date('now','localtime','start of month')"
    ).fetchone()
    summary["monthly_cost"] = round(cost_row["s"] or 0.0, 4)
    return summary


def _load_novels(conn):
    rows = conn.execute(
        "SELECT n.id, n.title, n.genre, n.platform, n.status, "
        "n.book_id, n.tags, n.abstract, n.protagonists, n.outline, "
        "n.volume_goal, n.premise, n.selling_point, n.updated_at, "
        "(SELECT COUNT(*) FROM chapters c WHERE c.novel_id=n.id) AS chapters, "
        "(SELECT COUNT(*) FROM chapters c WHERE c.novel_id=n.id "
        " AND c.status='published') AS published "
        " , (SELECT title FROM chapters c WHERE c.novel_id=n.id "
        " ORDER BY c.seq DESC LIMIT 1) AS last_chapter_title "
        "FROM novels n ORDER BY n.id"
    ).fetchall()
    novels = []
    for r in rows:
        d = dict(r)
        for key in ("tags", "protagonists", "outline"):
            try:
                d[key] = json.loads(d[key] or "{}" if key == "outline" else d[key] or "[]")
            except (TypeError, json.JSONDecodeError):
                d[key] = [] if key != "outline" else {}
        chars = conn.execute(
            "SELECT name, role, traits, goals FROM characters "
            "WHERE novel_id=? ORDER BY id",
            (d["id"],),
        ).fetchall()
        d["characters"] = [dict(c) for c in chars]
        novels.append(d)
    return novels


def _load_chapters(conn, novel_id=None):
    sql = (
        "SELECT c.id, c.novel_id, c.seq, c.outline, c.title, c.status, c.words, c.score, "
        "c.published_at, c.fanqie_item_id, "
        "(SELECT r.revision_count FROM quality_reports r "
        " WHERE r.chapter_id=c.id ORDER BY r.id DESC LIMIT 1) AS revisions "
        "FROM chapters c"
    )
    params = []
    if novel_id:
        sql += " WHERE c.novel_id=?"
        params.append(novel_id)
    sql += " ORDER BY c.novel_id, c.seq"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _load_publish_logs(conn, limit=50):
    rows = conn.execute(
        "SELECT id, chapter_id, platform, action, result, error, ai_declared "
        "FROM publish_logs ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def _load_alerts(conn):
    issues = monitor.run_checks(conn)
    tail = []
    if ALERTS_LOG.exists():
        tail = ALERTS_LOG.read_text(encoding="utf-8").strip().splitlines()[-20:]
    return {"issues": issues, "log_tail": tail}


def _load_reader_stats():
    if not READER_CSV.exists():
        return {"present": False, "rows": [], "report": None}
    rows = data_feedback.load_reader_stats(READER_CSV)
    return {"present": True, "rows": rows, "report": data_feedback.feedback_report(rows)}


def _load_hot_topics():
    if not HOT_TOPICS_JSON.exists():
        return {"present": False}
    payload = json.loads(HOT_TOPICS_JSON.read_text(encoding="utf-8"))
    payload["present"] = True
    return payload


def build_payload(conn):
    return {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": _load_summary(conn),
        "cost_budget": float(os.environ.get("MONTHLY_BUDGET", "100")),
        "novels": _load_novels(conn),
        "chapters": _load_chapters(conn),
        "publish_logs": _load_publish_logs(conn),
        "health": _load_alerts(conn),
        "reader_stats": _load_reader_stats(),
        "hot_topics": _load_hot_topics(),
    }


def make_handler(db_path):
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
                        self._json(build_payload(conn))
                    finally:
                        conn.close()
                elif path == "/api/chapters":
                    conn = db.connect(db_path)
                    try:
                        qs = parse_qs(parsed.query)
                        novel_id = int(qs["novel_id"][0]) if qs.get("novel_id") else None
                        self._json({"chapters": _load_chapters(conn, novel_id)})
                    finally:
                        conn.close()
                elif path == "/api/control":
                    conn = db.connect(db_path)
                    try:
                        self._json(_load_control(conn))
                    finally:
                        conn.close()
                elif path in ("/api/summary", "/api/novels", "/api/publish_logs",
                              "/api/alerts", "/api/reader_stats", "/api/hot_topics"):
                    conn = db.connect(db_path)
                    try:
                        self._json(_endpoint(conn, path.split("/")[-1]))
                    finally:
                        conn.close()
                else:
                    self.send_error(404, "Not Found")
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, status=500)

        def do_POST(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/control":
                self.send_error(404, "Not Found")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                payload = json.loads(raw.decode("utf-8") or "{}")
                conn = db.connect(db_path)
                try:
                    result = _handle_control(conn, payload)
                finally:
                    conn.close()
                self._json(result)
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, status=500)

        def _endpoint_data(self, name):
            conn = db.connect(db_path)
            try:
                return _endpoint(conn, name)
            finally:
                conn.close()

        def _serve_index(self):
            index = WEB_DIR / "index.html"
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


def _endpoint(conn, name):
    if name == "summary":
        return _load_summary(conn)
    if name == "novels":
        return _load_novels(conn)
    if name == "publish_logs":
        return _load_publish_logs(conn)
    if name == "alerts":
        return _load_alerts(conn)
    if name == "reader_stats":
        return _load_reader_stats()
    if name == "hot_topics":
        return _load_hot_topics()
    return {"error": f"未知端点 {name}"}


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
