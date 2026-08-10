"""全自动日更编排：生成 → 质量/合规门 → 发布调度 → 健康检查。"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import db, monitor, novel_flow
from novel_pipeline.llm_client import LLMClient
from novel_pipeline.publisher import FanqieHttpAdapter
from novel_pipeline.scheduler import Scheduler


def daily_run(conn, client, premise, chapters=3, chapters_per_day=2,
              platform="fanqie", min_chars=800, max_chars=1300,
              monthly_budget=100.0, spent=0.0, env=None, adapter=None):
    env = env if env is not None else os.environ
    generation = novel_flow.run_novel(
        conn, client, premise,
        chapters=chapters, platform=platform,
        min_chars=min_chars, max_chars=max_chars,
    )
    publish = Scheduler(
        adapter=adapter if adapter is not None else FanqieHttpAdapter(conn),
        chapters_per_day=chapters_per_day,
    ).tick(conn)
    issues = monitor.run_checks(
        conn, env=env, monthly_budget=monthly_budget, spent=spent
    )
    return {
        "generation": generation,
        "publish": publish,
        "health_issues": issues,
        "ok": generation["all_passed"] and not issues,
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="全自动日更编排")
    ap.add_argument("--premise", required=True, help="一句话核心设定")
    ap.add_argument("--chapters", type=int, default=3)
    ap.add_argument("--daily", type=int, default=2, help="每日发布章节数")
    ap.add_argument("--platform", default="fanqie")
    ap.add_argument("--db", default="demo.db")
    ap.add_argument("--budget", type=float, default=100.0, help="月度预算（元）")
    ap.add_argument("--spent", type=float, default=0.0, help="本月已用成本（元）")
    args = ap.parse_args()
    client = LLMClient()
    if not client.configured:
        print("未配置 LLM_API_KEY / LLM_BASE_URL，无法运行自动日更。")
        return 2
    conn = db.connect(args.db)
    result = daily_run(
        conn, client, args.premise,
        chapters=args.chapters, chapters_per_day=args.daily,
        platform=args.platform,
        monthly_budget=args.budget, spent=args.spent,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
