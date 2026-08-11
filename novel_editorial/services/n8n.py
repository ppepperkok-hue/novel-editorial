"""n8n API access shared by services."""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime

from novel_editorial import config

_N8N_KEY = None
_EXEC_ERROR_CACHE = {}
_LAST_API_LOG = {"ts": 0.0}


def n8n_api(method, path, body=None, timeout=6):
    """Call the n8n public API; returns parsed JSON or None on any failure."""
    key = _load_n8n_env()
    if not key:
        return None
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        config.N8N_BASE + "/api/v1" + path,
        data=data,
        method=method,
        headers={
            "X-N8N-API-KEY": key,
            "Content-Type": "application/json" if data else "text/plain",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        now = time.time()
        if now - _LAST_API_LOG["ts"] > 60:
            _LAST_API_LOG["ts"] = now
            try:
                config.ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
                with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
                    f.write(
                        f"[{datetime.now():%Y-%m-%d %H:%M:%S}] n8n API {method} "
                        f"{path} 失败：{exc.__class__.__name__}: {exc}\n"
                    )
            except Exception:  # noqa: BLE001
                pass
        return None


def _load_n8n_env():
    global _N8N_KEY
    value = config.env_value("N8N_API_KEY", "") or os.environ.get("N8N_API_KEY", "")
    _N8N_KEY = value or None
    return value


def workflow_status(wf_id):
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
    return {
        "online": True,
        "active": bool(info.get("active")),
        "last": last,
        "nodes": len(info.get("nodes") or []),
    }


def executions():
    rows = []
    for label, wf_id in (
        ("日更", config.N8N_WORKFLOW_DAILY),
        ("周会", config.N8N_WORKFLOW_WEEKLY),
    ):
        res = n8n_api("GET", f"/executions?workflowId={wf_id}&limit=20")
        if isinstance(res, dict) and isinstance(res.get("data"), list):
            for e in res["data"]:
                rows.append(
                    {
                        "workflow": label,
                        "id": e.get("id"),
                        "status": e.get("status"),
                        "started_at": e.get("startedAt"),
                        "stopped_at": e.get("stoppedAt"),
                    }
                )
    rows.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    rows = rows[:30]
    now = datetime.now().timestamp()
    if len(_EXEC_ERROR_CACHE) > 200:
        cutoff = now - 300
        for key in [k for k, (t, _e) in _EXEC_ERROR_CACHE.items() if t < cutoff]:
            del _EXEC_ERROR_CACHE[key]
    for row in rows:
        if row["status"] in ("success", "running", "waiting", None):
            continue
        exec_id = row.get("id")
        if exec_id is None:
            continue
        cached = _EXEC_ERROR_CACHE.get(exec_id)
        if cached and now - cached[0] < 60:
            row["error"] = cached[1]
            continue
        detail = n8n_api("GET", f"/executions/{exec_id}?includeData=true", timeout=3)
        error = None
        try:
            if detail and detail.get("data", {}).get("resultData", {}).get("error"):
                err = detail["data"]["resultData"]["error"]
                message = str(err.get("message") or "")
                node = (
                    (err.get("node") or {}).get("name")
                    if isinstance(err.get("node"), dict)
                    else None
                )
                if node:
                    message = f"[{node}] {message}"
                error = message[:500]
        except (TypeError, AttributeError):
            error = None
        _EXEC_ERROR_CACHE[exec_id] = (now, error)
        row["error"] = error
    return rows
