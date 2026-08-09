"""实时监控 Web API：读取 SQLite 与监控产物，供前端轮询展示。

端点：
  /                 监控面板（web/index.html）
  /api/dashboard    汇总负载（一次拉全，前端每 5 秒轮询）
  /api/summary /api/novels /api/chapters /api/publish_logs
  /api/health /api/reader_stats /api/hot_topics /api/alerts
"""

import argparse
import json
import sys
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
    return {key: conn.execute(sql).fetchone()["c"] for key, sql in queries.items()}


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
