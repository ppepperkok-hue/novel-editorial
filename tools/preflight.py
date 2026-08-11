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

from novel_editorial import config, db  # noqa: E402
from novel_editorial.services import audit  # noqa: E402
from tools.app_settings import get_all, get_bool, get_float  # noqa: E402

ENV_FILE = Path.home() / ".n8n" / ".env"
ALERTS_LOG = ROOT / "alerts.log"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


def load_env(env_file):
    """Load env vars from the given file (default ~/.n8n/.env) into
    os.environ without overwriting already-set process variables."""
    if env_file:
        env = dict(os.environ)
        path = Path(env_file)
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), config._strip_inline_comment(v))
    else:
        env = config.load_env()
    for k, v in env.items():
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


def check_already_ran(conn, novel_id=0):
    """Whether the given novel (0 = any novel, legacy CLI default) already
    published a chapter today. Per-book filtering keeps multi-book setups
    from blocking one novel because another one ran."""
    sql = (
        "SELECT COUNT(*) c FROM chapters "
        "WHERE status='published' AND published_at >= date('now','localtime')"
    )
    params = ()
    if novel_id:
        sql += " AND novel_id=?"
        params = (int(novel_id),)
    row = conn.execute(sql, params).fetchone()
    return row["c"] > 0


def check_budget(conn, budget):
    row = conn.execute(
        "SELECT COALESCE(SUM(cost),0) s FROM cost_logs "
        "WHERE created_at >= date('now','localtime','start of month')"
    ).fetchone()
    spent = round(row["s"] or 0.0, 4)
    return spent < budget, spent


def check_active_book(conn):
    """A daily run needs a publishable (publishing/finishing) novel; without
    one the whole generation+publish chain would spin for nothing and
    record_work would create garbage rows. New books are created by the
    panel flow: new-book meeting -> planning -> auto-create on Fanqie."""
    row = conn.execute(
        "SELECT COUNT(*) c FROM novels WHERE status IN ('publishing','finishing')"
    ).fetchone()
    if row and row["c"]:
        return True, ""
    return False, "当前没有可发布的连载作品，请先开新书会并完成建书"


def acquire_lock(lock_path):
    """Atomically claim the daily run lock (O_EXCL) to prevent concurrent
    scheduled + manual runs from both passing preflight and double-publishing.
    A lock whose PID parses and is still alive is considered held regardless
    of age; it is reclaimed immediately when that PID is dead. Only when the
    PID cannot be parsed does the 2h age rule apply (older locks are stale)."""
    lock = Path(lock_path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"{os.getpid()} {datetime.now():%Y-%m-%d %H:%M:%S}".encode("utf-8"))
        os.close(fd)
        return True, ""
    except FileExistsError:
        pid = None
        try:
            content = lock.read_text(encoding="utf-8").split()
            if content:
                pid = int(content[0])
        except (OSError, ValueError):
            pid = None
        try:
            age = time.time() - lock.stat().st_mtime
        except OSError:
            age = 0
        stale = False
        if pid is not None:
            stale = not _pid_alive(pid)
        elif age > 7200:
            stale = True
        if stale:
            try:
                lock.unlink()
                return acquire_lock(lock_path)
            except OSError:
                pass
        return False, "已有日更运行在途（运行锁占用），本次跳过防重复"


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


def release_lock(lock_path):
    lock = Path(lock_path)
    try:
        lock.unlink()
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
        book_ok, book_reason = check_active_book(conn)
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
        if not book_ok:
            reasons.append(book_reason)
        if manual_requested:
            reasons.append("手动请求运行已生效")
        ok = enabled and cookie_ok and not already_ran and budget_ok and book_ok
        # The preflight CLI is a check-only process; it must never hold the
        # run lock (a short-lived process writing the lock and exiting lets a
        # later run steal it). The lock is acquired by the real scheduler.
        # Consume the manual-run request only while actually holding the lock
        # (proceed case); failed preflights keep the request so the user can
        # retry, and a held lock keeps it for the in-flight run.
        if ok and manual_requested:
            lock_path = ROOT / "n8n_tmp" / (db_path.stem + ".lock")
            locked, _lock_reason = acquire_lock(lock_path)
            if locked:
                try:
                    conn.execute(
                        "INSERT INTO settings(key,value) "
                        "VALUES('manual_run_requested','0') "
                        "ON CONFLICT(key) DO UPDATE SET value='0'"
                    )
                    conn.commit()
                finally:
                    release_lock(lock_path)
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
                "book_ok": book_ok,
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
