"""监控与告警：Cookie 失效、断更预警、发布失败、成本超限。"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import db
from novel_pipeline.scheduler import SAFE_BACKLOG, backlog_level

N8N_ENV = Path.home() / ".n8n" / ".env"


def _load_n8n_env():
    """Fallback: read n8n's .env so the dashboard sees the real credentials."""
    if not N8N_ENV.exists():
        return {}
    vals = {}
    for line in N8N_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    return vals


class AlertSink:
    def __init__(self, path="alerts.log"):
        self.path = path

    def send(self, message):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")


def run_checks(conn, env=None, monthly_budget=100.0, spent=0.0):
    env = env if env is not None else os.environ
    if not env.get("FANQIE_COOKIE") and not env.get("TOMATO_COOKIE"):
        env = {**env, **_load_n8n_env()}
    issues = []

    if not (env.get("FANQIE_COOKIE") or env.get("TOMATO_COOKIE")) or not (
        env.get("FANQIE_CSRF_TOKEN") or env.get("TOMATO_CSRF_TOKEN")
    ):
        issues.append("番茄 Cookie/CSRF 缺失或失效，请从作者后台重新抓取")

    for novel in conn.execute("SELECT id, title FROM novels").fetchall():
        level = backlog_level(conn, novel["id"])
        if level < SAFE_BACKLOG:
            issues.append(f"断更预警：小说「{novel['title']}」存稿池 {level} 章")

    failed = conn.execute(
        "SELECT COUNT(*) c FROM publish_logs WHERE result='failed'"
    ).fetchone()["c"]
    if failed:
        issues.append(f"发布失败 {failed} 条，请检查发布适配器")

    if spent > monthly_budget:
        issues.append(f"成本超限：本月已用 {spent:.1f} 元，预算 {monthly_budget} 元")

    return issues


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="监控与告警")
    ap.add_argument("--db", default="demo.db")
    ap.add_argument("--spent", type=float, default=0.0, help="本月已用成本（元）")
    ap.add_argument("--budget", type=float, default=100.0, help="月度预算（元）")
    args = ap.parse_args()
    conn = db.connect(args.db)
    issues = run_checks(conn, monthly_budget=args.budget, spent=args.spent)
    if issues:
        print("问题清单：")
        for issue in issues:
            print(" -", issue)
        sys.exit(1)
    print("健康检查通过：无异常。")


if __name__ == "__main__":
    main()
