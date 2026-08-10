"""调度与存稿池：模拟每日发布计划、断更预警与健康检查。

骨架阶段用注入时钟与注入适配器实现，不依赖 APScheduler / cron；
接入真实平台后，把 tick() 挂到系统定时任务即可。
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import db
from novel_pipeline.publisher import ManualAdapter

SAFE_BACKLOG = 3


def backlog_level(conn, novel_id):
    row = conn.execute(
        "SELECT COUNT(*) c FROM chapters "
        "WHERE novel_id=? AND status IN ('reviewed','queued')",
        (novel_id,),
    ).fetchone()
    return row["c"]


class Scheduler:
    def __init__(self, adapter, chapters_per_day=2, safe_backlog=SAFE_BACKLOG,
                 alert_sink=None, now=None):
        self.adapter = adapter
        self.chapters_per_day = chapters_per_day
        self.safe_backlog = safe_backlog
        self.alert_sink = alert_sink
        self.now = now

    def tick(self, conn):
        """执行一次发布计划：检查存稿池、发布当日章节、更新状态、返回报告。"""
        report = {"published": [], "warnings": [], "date": str(self.now)}
        for novel in conn.execute("SELECT id, title FROM novels").fetchall():
            level = backlog_level(conn, novel["id"])
            if level < self.safe_backlog:
                warning = (
                    f"断更预警：小说「{novel['title']}」存稿池 {level} 章，"
                    f"低于安全线 {self.safe_backlog}"
                )
                report["warnings"].append(warning)
                if self.alert_sink:
                    self.alert_sink.send(warning)

            rows = conn.execute(
                "SELECT c.id, c.seq, c.outline, COALESCE(cc.content, c.outline) AS body "
                "FROM chapters c LEFT JOIN chapter_content cc ON cc.chapter_id=c.id "
                "WHERE c.novel_id=? AND c.status IN ('reviewed','queued') "
                "ORDER BY c.seq LIMIT ?",
                (novel["id"], self.chapters_per_day),
            ).fetchall()
            for row in rows:
                result = self.adapter.publish(row["id"], text=row["body"])
                conn.execute("UPDATE chapters SET status='published' WHERE id=?", (row["id"],))
                report["published"].append({"chapter_id": row["id"], "result": result})
        conn.commit()
        return report


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="调度与存稿池")
    ap.add_argument("--db", default="demo.db", help="SQLite 数据库路径")
    ap.add_argument("--chapters-per-day", type=int, default=2)
    args = ap.parse_args()
    conn = db.connect(args.db)
    scheduler = Scheduler(adapter=ManualAdapter(), chapters_per_day=args.chapters_per_day)
    print(scheduler.tick(conn))


if __name__ == "__main__":
    main()
