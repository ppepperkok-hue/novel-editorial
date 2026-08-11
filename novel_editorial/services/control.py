"""Scheduler control: status, manual run, schedule, settings (de-n8n).

The panel no longer talks to n8n: `run_now` launches the Python scheduler in
a background thread, `apply_schedule` registers a Windows scheduled task and
`pause/resume` flip the `daily_enabled` switch.
"""

import os
import subprocess
import sys
import threading
from pathlib import Path

from novel_editorial import config, db
from novel_editorial.services import audit
from tools.app_settings import get_all, set_many

ROOT = config.ROOT
DAILY_TASK_SCRIPT = ROOT / "scripts" / "install_daily_task.ps1"
DAILY_TASK_NAME = "NovelEditorialDaily"

_ACTIVE_DB = None


def set_db_path(db_path):
    """Point every control background path at the service's active database."""
    global _ACTIVE_DB
    _ACTIVE_DB = str(db_path or "")


def _db_path():
    return _ACTIVE_DB or str(config.DB_PATH)


def _alert(message):
    try:
        config.ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
            from datetime import datetime

            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
    except Exception:  # noqa: BLE001
        pass


def _enabled(value):
    return str(value or "true").strip().lower() in ("1", "true", "yes", "on")


def _scheduler_state(conn):
    settings = get_all(conn)
    row = conn.execute(
        "SELECT run_id, status, trigger, source, started_at, finished_at, "
        "published, failed_nodes, error FROM daily_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    workday_row = conn.execute(
        "SELECT run_id, status, phase, mode, boss_instruction, published, "
        "started_at, finished_at, error, collab_summary, legacy FROM daily_runs "
        "WHERE source='workday' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    from datetime import datetime  # noqa: PLC0415

    today = datetime.now().strftime("%Y-%m-%d")
    today_opened = conn.execute(
        "SELECT COUNT(*) c FROM daily_runs "
        "WHERE source='workday' AND substr(started_at,1,10)=?",
        (today,),
    ).fetchone()["c"]
    today_published = conn.execute(
        "SELECT COUNT(*) c FROM publish_logs "
        "WHERE result='success' AND substr(created_at,1,10)=?",
        (today,),
    ).fetchone()["c"]
    return {
        "enabled": _enabled(settings.get("daily_enabled", "true")),
        "manual_run_requested": str(settings.get("manual_run_requested", "0")) == "1",
        "scheduled_time": settings.get("daily_run_time", "08:00"),
        "daily_chapters": settings.get("daily_chapters", "2"),
        "last_run": dict(row) if row else None,
        "workday": dict(workday_row) if workday_row else None,
        "today_opened": today_opened,
        "today_published": today_published,
    }


def load_control(conn):
    return {
        "settings": get_all(conn),
        "scheduler": _scheduler_state(conn),
    }


def _spawn(target):
    threading.Thread(target=target, daemon=True).start()


def _refresh_hot_topics(timeout=90):
    """Run hot-topics collection off the HTTP thread, bounded by a timeout.

    Returns the refresh payload when it finishes; on exception or timeout it
    returns ``{"ok": False, "error": ...}``. A timed-out worker keeps running
    and still writes hot_topics.json when it eventually completes.
    """
    from novel_editorial import hot_topics  # noqa: PLC0415

    box = {}

    def worker():
        try:
            box["payload"] = hot_topics.refresh(
                out_path=str(config.HOT_TOPICS_JSON), browser_fallback=True
            )
        except Exception as exc:  # noqa: BLE001
            box["error"] = f"{exc.__class__.__name__}: {exc}"
            _alert(f"热点采集失败: {str(exc)[:300]}")

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)
    if "payload" in box:
        return box["payload"]
    if "error" in box:
        return {"ok": False, "error": f"热点采集失败：{box['error']}"}
    return {"ok": False, "error": "热点采集超时（已转入后台继续）"}


def _run_cli(script_rel, args):
    cmd = [sys.executable, str(ROOT / script_rel), *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=7200,
        )
        if result.returncode != 0:
            _alert(
                f"{script_rel} 失败: exit={result.returncode} "
                + str(result.stderr or result.stdout or "")[-300:]
            )
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        _alert(f"{script_rel} 失败: {str(exc)[:200]}")
        return False


def _background_daily(chapters=None):
    def worker():
        try:
            conn = db.connect(_db_path())
            try:
                from tools import editorial_daily  # noqa: PLC0415

                editorial_daily.daily(
                    conn,
                    chapters=chapters,
                    trigger="manual",
                    db_path=_db_path(),
                )
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            _alert(f"后台日更线程异常: {str(exc)[:300]}")

    _spawn(worker)


def _background_workday(mode="write", chapters=None, boss_instruction=""):
    def worker():
        try:
            conn = db.connect(_db_path())
            try:
                from tools import workday  # noqa: PLC0415

                workday.open(
                    conn,
                    chapters=chapters,
                    trigger="manual",
                    mode=mode,
                    boss_instruction=boss_instruction,
                    db_path=_db_path(),
                )
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            _alert(f"工作日后台异常: {str(exc)[:300]}")

    _spawn(worker)


def _background_close(run_id):
    def worker():
        try:
            conn = db.connect(_db_path())
            try:
                from tools import workday  # noqa: PLC0415

                workday.close(
                    conn, run_id, db_path=_db_path()
                )
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            _alert(f"收工后台异常: {str(exc)[:300]}")

    _spawn(worker)


def _background_resume(run_id, chapters=None):
    def worker():
        try:
            conn = db.connect(_db_path())
            try:
                from tools import workday  # noqa: PLC0415

                workday.resume(
                    conn, run_id, chapters=chapters, db_path=_db_path()
                )
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            _alert(f"继续工作日后台异常: {str(exc)[:300]}")

    _spawn(worker)


def _background_weekly():
    def worker():
        _weekly_worker()

    _spawn(worker)


def _weekly_worker():
    """Run the weekly chain once; a held weekly lock means another meeting is
    already running, so this invocation is skipped with an explicit alert."""
    from tools import preflight  # noqa: PLC0415

    lock_path = ROOT / "n8n_tmp" / "weekly.lock"
    locked, lock_reason = preflight.acquire_lock(lock_path)
    if not locked:
        _alert(f"周会已在进行中，本次跳过：{lock_reason}")
        return
    try:
        try:
            from novel_editorial import hot_topics  # noqa: PLC0415

            hot_topics.refresh(
                out_path=str(config.HOT_TOPICS_JSON), browser_fallback=True
            )
        except Exception as exc:  # noqa: BLE001
            _alert(f"周会热点采集失败: {str(exc)[:200]}")
        _run_cli("tools/architect_weekly.py", ["--db", _db_path()])
        _run_cli(
            "tools/agent_meeting.py",
            ["--db", _db_path(), "--kind", "weekly"],
        )
        _run_cli("tools/distill_lessons.py", ["--db", _db_path()])
    finally:
        preflight.release_lock(lock_path)


def run_workflow_now(workflow):
    if workflow == "daily":
        _background_daily()
        return {
            "ok": True,
            "started": True,
            "workflow": "daily",
            "note": "日更已在后台启动，可在执行记录页查看进度",
        }
    if workflow == "weekly":
        _background_weekly()
        return {
            "ok": True,
            "started": True,
            "workflow": "weekly",
            "note": "周会已在后台启动，可在会议中心查看进度",
        }
    return {"ok": False, "error": "workflow must be daily|weekly"}


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

    time_str = f"{hour:02d}:{minute:02d}"
    set_many(conn, {"daily_run_time": time_str})
    if os.name != "nt":
        return {
            "ok": True,
            "time": time_str,
            "deploy": {"ok": True, "note": "非 Windows 环境，仅保存定时设置"},
        }
    db_arg = _db_path()
    try:
        db_arg = os.path.relpath(db_arg, ROOT)
    except ValueError:
        pass  # cross-drive path: keep the absolute path
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(DAILY_TASK_SCRIPT),
        "-Time",
        time_str,
        "-DbPath",
        db_arg,
        "-TaskName",
        DAILY_TASK_NAME,
    ]
    try:
        out = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        ok = out.returncode == 0
        return {
            "ok": ok,
            "time": time_str,
            "deploy": {
                "ok": ok,
                "output": (out.stdout or out.stderr or "")[-400:],
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"计划任务注册失败: {str(exc)[:200]}"}


def deploy_workflow():
    """Legacy no-op kept for callers that still reference deployment."""
    return {"ok": True, "note": "调度器模式无需部署 n8n 工作流"}


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
        mode = str(payload.get("mode") or "")
        wf = payload.get("workflow") or "daily"
        if mode in ("write", "org", "meeting", "free"):
            _background_workday(
                mode,
                chapters=payload.get("chapters"),
                boss_instruction=payload.get("boss_instruction") or "",
            )
            audit.log(
                conn,
                "operation",
                "run_now",
                target_type="workflow",
                target_id="workday",
                detail={"mode": mode, "chapters": payload.get("chapters")},
            )
            return {
                "ok": True,
                "started": True,
                "workflow": "workday",
                "mode": mode,
                "note": "编辑部已开工，可在首页查看进度",
            }
        chapters = payload.get("chapters")
        n = 0
        if chapters:
            try:
                n = max(1, min(int(chapters), 5))
            except (TypeError, ValueError):
                n = 0
        wf = payload.get("workflow") or "daily"
        if wf == "daily":
            set_many(conn, {"manual_run_requested": "1"})
            if n:
                set_many(conn, {"pending_publish": str(n)})
        result = run_workflow_now(wf)
        audit.log(
            conn,
            "operation",
            "run_now",
            target_type="workflow",
            target_id=wf,
            detail={
                "chapters": n or payload.get("chapters"),
                "ok": result.get("ok"),
                "started": result.get("started"),
            },
        )
        return result
    if action == "close_workday":
        run_id = payload.get("run_id") or ""
        if not run_id:
            return {"ok": False, "error": "run_id required"}
        _background_close(run_id)
        audit.log(
            conn, "operation", "close_workday",
            target_type="run", target_id=run_id,
        )
        return {"ok": True, "started": True, "note": "收工流程已启动"}
    if action == "resume_workday":
        run_id = payload.get("run_id") or ""
        if not run_id:
            return {"ok": False, "error": "run_id required"}
        _background_resume(run_id, chapters=payload.get("chapters"))
        audit.log(
            conn, "operation", "resume_workday",
            target_type="run", target_id=run_id,
        )
        return {"ok": True, "started": True, "note": "继续补跑已启动"}
    if action == "apply_schedule":
        result = apply_schedule(conn)
        audit.log(
            conn,
            "settings",
            "apply_schedule",
            detail={"time": result.get("time"), "ok": result.get("ok")},
        )
        return result
    if action == "request_run":
        set_many(conn, {"manual_run_requested": "1"})
        audit.log(conn, "operation", "request_run")
        return {"ok": True, "note": "将在下次定时触发时执行"}
    if action in ("pause", "resume"):
        wf = payload.get("workflow") or "daily"
        if wf != "daily":
            return {
                "ok": True,
                "note": f"{wf} 无独立开关，请使用手动触发",
            }
        enabled = action == "resume"
        set_many(conn, {"daily_enabled": "true" if enabled else "false"})
        audit.log(
            conn,
            "operation",
            action,
            target_type="workflow",
            target_id=wf,
            detail={"enabled": enabled},
        )
        return {"ok": True, "enabled": enabled, "workflow": wf}
    if action == "refresh_hot_topics":
        payload = _refresh_hot_topics(timeout=90)
        if payload.get("ok") is False:
            audit.log(
                conn,
                "operation",
                "refresh_hot_topics",
                detail={"ok": False, "error": payload.get("error", "")},
            )
            return payload
        sources = payload.get("sources", [])
        errors = [src.get("error", "") for src in sources if src.get("error")]
        ok = bool(sources) and len(errors) < len(sources)
        audit.log(
            conn, "operation", "refresh_hot_topics",
            detail={
                src.get("source"): {
                    "method": src.get("method"),
                    "count": src.get("count", 0),
                    "error": src.get("error", ""),
                }
                for src in sources
            },
        )
        result = {
            "ok": ok,
            "updated_at": payload.get("updated_at"),
            "sources": [
                {
                    "source": src.get("source"),
                    "method": src.get("method", "html"),
                    "count": src.get("count", 0),
                    "error": src.get("error", ""),
                }
                for src in sources
            ],
        }
        if not ok:
            result["error"] = (
                "全部热点源采集失败：" + "；".join(errors)
                if errors
                else "未获取到任何热点源结果"
            )
        return result
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
    if action == "process_messages":
        from tools import mailroom  # noqa: PLC0415

        result = mailroom.unread_summary(
            conn, novel_id=payload.get("novel_id") or 0
        )
        audit.log(
            conn,
            "operation",
            "process_messages",
            detail={"total_unread": result.get("total", 0), "ok": result.get("ok")},
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
