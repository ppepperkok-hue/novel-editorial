"""Workflow control: status, manual run, schedule, settings."""

import json
import urllib.error
import urllib.request

from novel_pipeline import config
from novel_pipeline.services import audit
from novel_pipeline.services import n8n
from tools.app_settings import set_many

WEBHOOK_PATHS = {
    "daily": "novel-manual-run",
    "weekly": "novel-weekly-run",
}


def load_control(conn):
    from tools.app_settings import get_all  # noqa: PLC0415

    return {
        "settings": get_all(conn),
        "workflows": {
            "daily": n8n.workflow_status(config.N8N_WORKFLOW_DAILY),
            "weekly": n8n.workflow_status(config.N8N_WORKFLOW_WEEKLY),
            "keeper": n8n.workflow_status(config.N8N_WORKFLOW_KEEPER),
        },
    }


def run_workflow_now(workflow):
    hook_path = WEBHOOK_PATHS.get(workflow)
    if not hook_path:
        return {"ok": False, "error": "workflow must be daily|weekly"}
    req = urllib.request.Request(
        config.N8N_BASE + "/webhook/" + hook_path,
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            payload = r.read().decode("utf-8", "ignore")
        return {"ok": True, "response": payload, "workflow": workflow}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"webhook trigger failed: HTTP {e.code}"}
    except (urllib.error.URLError, OSError) as e:
        return {"ok": False, "error": f"n8n unreachable: {e}"}


def apply_schedule(conn):
    row = conn.execute(
        "SELECT value FROM settings WHERE key='daily_run_time'"
    ).fetchone()
    value = (row["value"] if row else "08:00").strip()
    parts = value.split(":")
    if len(parts) != 2:
        return {"ok": False, "error": f"daily_run_time must be HH:MM, got {value!r}"}
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return {"ok": False, "error": f"daily_run_time must be HH:MM, got {value!r}"}
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return {"ok": False, "error": "time out of range (00:00-23:59)"}

    wf = json.loads(config.WORKFLOW_JSON.read_text(encoding="utf-8"))
    found = False
    for node in wf["nodes"]:
        if node.get("type") == "n8n-nodes-base.scheduleTrigger":
            rule = node.setdefault("parameters", {}).setdefault("rule", {})
            for item in rule.get("interval", []):
                item["triggerAtHour"] = hour
                item["triggerAtMinute"] = minute
                found = True
    if not found:
        return {"ok": False, "error": "schedule trigger node not found in workflow"}
    config.WORKFLOW_JSON.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    deployed = deploy_workflow()
    return {
        "ok": deployed["ok"],
        "time": f"{hour:02d}:{minute:02d}",
        "deploy": deployed,
    }


def deploy_workflow():
    wf = json.loads(config.WORKFLOW_JSON.read_text(encoding="utf-8"))
    body = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
    }
    res = n8n.n8n_api("PUT", "/workflows/" + config.N8N_WORKFLOW_DAILY, body)
    if res is None:
        return {"ok": False, "error": "n8n deploy failed (offline or API key missing)"}
    return {"ok": True, "nodes": len(wf["nodes"]), "active": bool(res.get("active"))}


def handle_control(conn, payload):
    action = payload.get("action")
    if action == "save_settings":
        values = {
            k: v
            for k, v in (payload.get("settings") or {}).items()
            if k in ALLOWED_SETTINGS
        }
        set_many(conn, values)
        audit.log(conn, "settings", "save_settings", detail={"saved": values})
        return {"ok": True, "saved": values}
    if action == "run_now":
        if payload.get("workflow") == "daily":
            set_many(conn, {"manual_run_requested": "1"})
            chapters = payload.get("chapters")
            if chapters:
                try:
                    n = max(1, min(int(chapters), 5))
                except (TypeError, ValueError):
                    n = 0
                if n:
                    set_many(conn, {"pending_publish": str(n)})
        wf = payload.get("workflow") or "daily"
        result = run_workflow_now(wf)
        audit.log(
            conn,
            "operation",
            "run_now",
            target_type="workflow",
            target_id=wf,
            detail={"chapters": payload.get("chapters"), "ok": result.get("ok")},
        )
        return result
    if action == "apply_schedule":
        time_value = (payload.get("time") or "").strip()
        if time_value:
            set_many(conn, {"daily_run_time": time_value})
        result = apply_schedule(conn)
        audit.log(conn, "settings", "apply_schedule", detail={"time": time_value or None, "ok": result.get("ok")})
        return result
    if action == "request_run":
        set_many(conn, {"manual_run_requested": "1"})
        audit.log(conn, "operation", "request_run")
        return {"ok": True, "note": "将在下次定时触发时执行"}
    if action in ("pause", "resume"):
        wf_id = {
            "daily": config.N8N_WORKFLOW_DAILY,
            "weekly": config.N8N_WORKFLOW_WEEKLY,
            "keeper": config.N8N_WORKFLOW_KEEPER,
        }.get(payload.get("workflow"))
        if not wf_id:
            return {"ok": False, "error": "workflow must be daily|weekly|keeper"}
        endpoint = "deactivate" if action == "pause" else "activate"
        res = n8n.n8n_api(
            "POST",
            f"/workflows/{wf_id}/{endpoint}",
            body={},
        )
        audit.log(
            conn,
            "operation",
            action,
            target_type="workflow",
            target_id=payload.get("workflow"),
            detail={"ok": res is not None},
        )
        return {"ok": res is not None, "response": res}
    if action == "refresh_hot_topics":
        from novel_pipeline import hot_topics  # noqa: PLC0415

        payload = hot_topics.refresh(
            out_path=str(config.HOT_TOPICS_JSON), browser_fallback=True
        )
        audit.log(
            conn, "operation", "refresh_hot_topics",
            detail={
                src.get("source"): {
                    "method": src.get("method"),
                    "count": src.get("count", 0),
                    "error": src.get("error", ""),
                }
                for src in payload.get("sources", [])
            },
        )
        return {
            "ok": True,
            "updated_at": payload.get("updated_at"),
            "sources": [
                {
                    "source": src.get("source"),
                    "method": src.get("method", "html"),
                    "count": src.get("count", 0),
                    "error": src.get("error", ""),
                }
                for src in payload.get("sources", [])
            ],
        }
    if action == "run_knowledge_keeper":
        from tools import knowledge_keeper  # noqa: PLC0415

        result = knowledge_keeper.run(conn)
        audit.log(
            conn, "operation", "run_knowledge_keeper",
            detail={
                "auto_updates": result.get("auto_updates"),
                "draft_suggestions": result.get("draft_suggestions"),
                "deprecations": result.get("deprecations"),
                "ok": result.get("ok"),
            },
        )
        return result
    return {"ok": False, "error": f"unknown action {action}"}


ALLOWED_SETTINGS = {
    "daily_enabled",
    "monthly_budget",
    "target_words",
    "style_tweak",
    "daily_run_time",
    "daily_chapters",
    "target_chapters",
    "novel_premise",
    "novel_keywords",
    "novel_genre",
}
