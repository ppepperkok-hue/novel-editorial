"""Persist daily-run traces from n8n into the local database.

The 66-node n8n workflow is the runnable baseline; this module only watches
its executions (n8n local DB + API for failure details) and keeps a durable
local record so the panel can review runs even when n8n is offline.

Usage (library):
    from tools import daily_runs
    daily_runs.sync_from_n8n(conn)
    daily_runs.list_runs(conn)
"""

import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from novel_pipeline import config

N8N_DB = Path.home() / ".n8n" / "database.sqlite"
UTC_OFFSET = timedelta(hours=8)


def _to_local(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt + UTC_OFFSET).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(value)


def _n8n_executions(limit=20):
    """Recent executions of the daily workflow from the n8n local DB."""
    if not N8N_DB.exists():
        return []
    conn = sqlite3.connect(str(N8N_DB), timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, workflowId, mode, status, startedAt, stoppedAt "
            "FROM execution_entity WHERE workflowId=? AND deletedAt IS NULL "
            "ORDER BY id DESC LIMIT ?",
            (config.N8N_WORKFLOW_DAILY, int(limit or 20)),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _execution_failure(run_id):
    """Best-effort failure details via n8n API; never raises."""
    key = config.env_value("N8N_API_KEY", "")
    if not key:
        return ["未知节点"], "n8n API key 缺失，无法获取失败详情"
    try:
        req = urllib.request.Request(
            config.N8N_BASE + f"/api/v1/executions/{run_id}?includeData=true",
            headers={"X-N8N-API-KEY": key},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read().decode("utf-8", "ignore"))
        data = body.get("data") or {}
        result = (data.get("data") or {}).get("resultData") or {}
        last_node = str(result.get("lastNodeExecuted") or "")
        err = result.get("error") or {}
        message = str(err.get("message") or "") if isinstance(err, dict) else str(err)
        return ([last_node] if last_node else ["未知节点"]), message or "执行失败（无详情）"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return ["未知节点"], f"获取失败详情出错：{exc.__class__.__name__}"


def published_of(conn, started_at, finished_at):
    """Successfully published chapters inside a run's time window."""
    if not started_at:
        return 0
    row = conn.execute(
        "SELECT COUNT(*) c FROM publish_logs "
        "WHERE action='publish' AND result='success' AND created_at>=? "
        "AND (created_at<=? OR ?='')",
        (started_at, finished_at or started_at, finished_at or ""),
    ).fetchone()
    return row["c"] if row else 0


def sync_from_n8n(conn, limit=20):
    """Idempotently persist recent n8n executions into daily_runs."""
    written = 0
    for ex in _n8n_executions(limit):
        run_id = str(ex["id"])
        exists = conn.execute(
            "SELECT id FROM daily_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if exists:
            continue
        status = str(ex.get("status") or "running")
        failed_nodes = []
        error = ""
        if status in ("failed", "crashed", "error"):
            failed_nodes, error = _execution_failure(run_id)
        started = _to_local(ex.get("startedAt"))
        finished = _to_local(ex.get("stoppedAt"))
        novel = conn.execute(
            "SELECT id FROM novels WHERE status='publishing' AND book_id!='' "
            "ORDER BY id LIMIT 1"
        ).fetchone()
        conn.execute(
            "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,started_at,"
            "finished_at,failed_nodes,error,published,detail,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
            (
                run_id,
                novel["id"] if novel else 0,
                str(ex.get("mode") or "scheduled"),
                "n8n-legacy",
                status,
                started,
                finished,
                json.dumps(failed_nodes, ensure_ascii=False),
                error,
                published_of(conn, started, finished),
                json.dumps({"execution_id": run_id}, ensure_ascii=False),
            ),
        )
        written += 1
    conn.commit()
    return {"written": written}


def list_runs(conn, limit=30):
    rows = conn.execute(
        "SELECT run_id, novel_id, trigger, status, started_at, finished_at, "
        "published, failed_nodes, error, created_at FROM daily_runs "
        "ORDER BY id DESC LIMIT ?",
        (int(limit or 30),),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["failed_nodes"] = json.loads(d["failed_nodes"] or "[]")
        except (TypeError, ValueError):
            d["failed_nodes"] = []
        out.append(d)
    return out


def run_detail(conn, run_id):
    row = conn.execute(
        "SELECT * FROM daily_runs WHERE run_id=?", (str(run_id),)
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    for key in ("failed_nodes", "detail"):
        try:
            d[key] = json.loads(d[key] or ("[]" if key == "failed_nodes" else "{}"))
        except (TypeError, ValueError):
            d[key] = [] if key == "failed_nodes" else {}
    return d


def local_executions(conn, limit=30):
    """Panel-facing execution rows backed by daily_runs (de-n8n).

    Keeps the old n8n executions shape (`id/workflow/status/started_at/
    stopped_at/error`) so the frontend table keeps working without n8n.
    """
    rows = conn.execute(
        "SELECT run_id, trigger, source, status, started_at, finished_at, "
        "published, failed_nodes, error FROM daily_runs "
        "ORDER BY id DESC LIMIT ?",
        (int(limit or 30),),
    ).fetchall()
    out = []
    for r in rows:
        try:
            failed_nodes = json.loads(r["failed_nodes"] or "[]")
        except (TypeError, ValueError):
            failed_nodes = []
        status = "success" if r["status"] == "completed" else r["status"]
        out.append(
            {
                "workflow": "n8n(legacy)" if r["source"] == "n8n-legacy" else "日更",
                "id": r["run_id"],
                "status": status,
                "started_at": r["started_at"],
                "stopped_at": r["finished_at"],
                "published": r["published"] or 0,
                "failed_nodes": failed_nodes,
                "error": r["error"] or "",
            }
        )
    return out
