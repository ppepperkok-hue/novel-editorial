"""Run preflight checks before a daily n8n run.

Checks:
1. Fanqie cookie still works (otherwise the whole run would waste LLM budget).
2. The day has not already published chapters (idempotency guard).
3. Monthly LLM cost is below budget.

Outputs a single JSON object; exit code is always 0 so n8n can branch on "ok".
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import config, db  # noqa: E402
from novel_pipeline.services import audit  # noqa: E402
from tools.app_settings import get_all, get_bool, get_float  # noqa: E402

ENV_FILE = Path.home() / ".n8n" / ".env"
ALERTS_LOG = ROOT / "alerts.log"
LOCK_FILE = ROOT / "n8n_tmp" / "daily.lock"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


def load_env(env_file):
    for k, v in config.load_env().items():
        os.environ.setdefault(k, v)


def alert(message):
    with ALERTS_LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")


def check_cookie():
    if not (os.environ.get("FANQIE_COOKIE") and os.environ.get("FANQIE_CSRF_TOKEN")):
        return False, "Cookie/CSRF 环境变量缺失"
    qs = urllib.parse.urlencode(
        {"aid": "2503", "app_name": "muye_novel", "page_index": "0", "page_count": "20"}
    )
    req = urllib.request.Request(
        "https://fanqienovel.com/api/author/book/book_list/v0?" + qs,
        headers={
            "Cookie": os.environ["FANQIE_COOKIE"],
            "X-Secsdk-Csrf-Token": os.environ["FANQIE_CSRF_TOKEN"],
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://fanqienovel.com",
            "Referer": "https://fanqienovel.com/main/writer/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read().decode("utf-8", "ignore"))
        if body.get("code") == 0:
            return True, ""
        return False, "Cookie 失效：" + str(body.get("message") or body)[:120]
    except urllib.error.HTTPError as e:
        return False, f"Cookie 请求被拒 HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, f"Cookie 检测异常：{str(e)[:120]}"


def check_already_ran(conn):
    row = conn.execute(
        "SELECT COUNT(*) c FROM chapters "
        "WHERE status='published' AND published_at >= date('now','localtime')"
    ).fetchone()
    return row["c"] > 0


def check_budget(conn, budget):
    row = conn.execute(
        "SELECT COALESCE(SUM(cost),0) s FROM cost_logs "
        "WHERE created_at >= date('now','localtime','start of month')"
    ).fetchone()
    spent = round(row["s"] or 0.0, 4)
    return spent < budget, spent


def acquire_lock():
    """Atomically claim the daily run lock (O_EXCL) to prevent concurrent
    scheduled + manual runs from both passing preflight and double-publishing."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"{os.getpid()} {datetime.now():%Y-%m-%d %H:%M:%S}".encode("utf-8"))
        os.close(fd)
        return True, ""
    except FileExistsError:
        try:
            pid = int(LOCK_FILE.read_text(encoding="utf-8").split()[0])
            alive = _pid_alive(pid)
        except Exception:
            alive = time.time() - LOCK_FILE.stat().st_mtime < 3600
        if not alive:
            try:
                LOCK_FILE.unlink()
                return acquire_lock()
            except OSError:
                pass
        else:
            age = time.time() - LOCK_FILE.stat().st_mtime
            if age > 1800:
                # A healthy daily run finishes well under 30 minutes; a live
                # PID here is likely reused, so treat the lock as stale.
                try:
                    LOCK_FILE.unlink()
                    return acquire_lock()
                except OSError:
                    pass
        return False, "已有日更运行在途中（运行锁占用），本次跳过防双发"


def _pid_alive(pid):
    """Check process liveness without killing it on Windows."""
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    try:
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001 - fall back to conservative "alive"
        return True


def release_lock():
    try:
        LOCK_FILE.unlink()
    except OSError:
        pass


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="日更运行前预检")
    ap.add_argument("--db", default="demo.db")
    ap.add_argument("--budget", type=float, default=100.0)
    ap.add_argument("--env-file", default=str(ENV_FILE))
    args = ap.parse_args()

    load_env(args.env_file)
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    try:
        settings = get_all(conn)
        enabled = str(settings.get("daily_enabled", "true")).strip().lower() in ("1", "true", "yes", "on")
        try:
            budget = float(settings.get("monthly_budget", args.budget))
        except (TypeError, ValueError):
            budget = args.budget
        manual_requested = str(settings.get("manual_run_requested", "0")) == "1"
        cookie_ok, cookie_reason = check_cookie()
        already_ran = check_already_ran(conn)
        if manual_requested:
            already_ran = False
        budget_ok, spent = check_budget(conn, budget)
        reasons = []
        if not enabled:
            reasons.append("日更已暂停（可在监控面板恢复）")
        if not cookie_ok:
            reasons.append(cookie_reason)
            alert("预检失败：" + cookie_reason)
        if already_ran:
            reasons.append("今日已发布过章节，跳过防重复")
        if not budget_ok:
            reasons.append(f"本月成本 {spent:.2f} 元已达预算 {budget:.2f} 元")
            alert(reasons[-1])
        if manual_requested:
            reasons.append("手动请求运行已生效")
        ok = enabled and cookie_ok and not already_ran and budget_ok
        if ok:
            locked, lock_reason = acquire_lock()
            if not locked:
                reasons.append(lock_reason)
                ok = False
        # Consume the manual-run request only when this run will actually
        # proceed; failed preflights keep the request so the user can retry.
        if ok and manual_requested:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES('manual_run_requested','0') "
                "ON CONFLICT(key) DO UPDATE SET value='0'"
            )
            conn.commit()
        audit.log(
            conn,
            "preflight",
            "passed" if ok else "blocked",
            target_type="novel",
            detail={
                "ok": ok,
                "reasons": reasons,
                "cookie_valid": cookie_ok,
                "already_ran": already_ran,
                "budget_ok": budget_ok,
            },
            source="preflight",
        )
        print(
            json.dumps(
                {
                    "ok": ok,
                    "cookie_valid": cookie_ok,
                    "cookie_reason": cookie_reason,
                    "already_ran": already_ran,
                    "manual_run_requested": manual_requested,
                    "budget_ok": budget_ok,
                    "spent": spent,
                    "budget": budget,
                    "daily_enabled": enabled,
                    "reasons": reasons,
                },
                ensure_ascii=False,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
