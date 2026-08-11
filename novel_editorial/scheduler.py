"""调度与存稿池：模拟每日发布计划、断更预警与健康检查。

骨架阶段用注入时钟与注入适配器实现，不依赖 APScheduler / cron；
接入真实平台后，把 tick() 挂到系统定时任务即可。
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import db
from novel_editorial.publisher import ManualAdapter

SAFE_BACKLOG = 3


def backlog_level(conn, novel_id):
    row = conn.execute(
        "SELECT COUNT(*) c FROM chapters "
        "WHERE novel_id=? AND status IN ('reviewed','queued')",
        (novel_id,),
    ).fetchone()
    return row["c"]


class Scheduler:
    """DEPRECATED 发布调度器类（n8n 时代路径，当前无调用方）。

    `SAFE_BACKLOG` 与 `backlog_level` 仍被 monitor 使用；类的发布循环已由
    `tools/publish_stock.publish_batch` 取代，保留为回退后备。
    """

    def __init__(self, adapter, chapters_per_day=2, safe_backlog=SAFE_BACKLOG,
                 alert_sink=None, now=None):
        self.adapter = adapter
        self.chapters_per_day = chapters_per_day
        self.safe_backlog = safe_backlog
        self.alert_sink = alert_sink
        self.now = now

    def tick(self, conn):
        """执行一次发布计划：检查存稿池、发布当日章节、更新状态、返回报告。"""
        now = self.now or datetime.now()
        report = {
            "published": [],
            "failures": [],
            "warnings": [],
            "date": now.strftime("%Y-%m-%d") if hasattr(now, "strftime") else str(now),
        }
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
                "SELECT c.id, c.seq, c.outline, cc.content AS body "
                "FROM chapters c LEFT JOIN chapter_content cc ON cc.chapter_id=c.id "
                "WHERE c.novel_id=? AND c.status IN ('reviewed','queued') "
                "ORDER BY c.seq LIMIT ?",
                (novel["id"], self.chapters_per_day),
            ).fetchall()
            for row in rows:
                body = str(row["body"] or "").strip()
                if not body:
                    message = (
                        f"章节 {row['seq']} 处于待发布状态但缺少正文（chapter_content），"
                        "已跳过，禁止把章纲当正文发布"
                    )
                    report["warnings"].append(message)
                    report["failures"].append({"chapter_id": row["id"], "error": message})
                    if self.alert_sink:
                        self.alert_sink.send(message)
                    continue
                try:
                    result = self.adapter.publish(row["id"], text=body)
                    conn.execute(
                        "UPDATE chapters SET status='published' WHERE id=?", (row["id"],)
                    )
                except Exception as exc:  # noqa: BLE001
                    result = {"result": "failed", "error": str(exc)[:200]}
                    report["failures"].append(
                        {"chapter_id": row["id"], "error": str(exc)[:200]}
                    )
                    if self.alert_sink:
                        self.alert_sink.send(f"章节 {row['seq']} 发布失败：{exc}")
                    continue
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
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    scheduler = Scheduler(adapter=ManualAdapter(), chapters_per_day=args.chapters_per_day)
    print(scheduler.tick(conn))


if __name__ == "__main__":
    main()
