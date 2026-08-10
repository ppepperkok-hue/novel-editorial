"""发布适配器：平台无关接口 + 人工确认通道 + 番茄 HTTP 适配器骨架。"""

import json
from datetime import datetime
from abc import ABC, abstractmethod
from pathlib import Path


class PublisherAdapter(ABC):
    @abstractmethod
    def publish(self, chapter_id, text, scheduled_at=None, as_draft=False):
        ...


class ManualAdapter(PublisherAdapter):
    """人工确认通道：把待发布章节写入队列文件，由真人过目后发布。"""

    def publish(self, chapter_id, text, scheduled_at=None, as_draft=False):
        queue_path = Path("publish_queue.jsonl")
        record = {
            "chapter_id": chapter_id,
            "scheduled_at": scheduled_at,
            "as_draft": as_draft,
            "chars": len(text),
        }
        with queue_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"result": "queued_for_manual_review", "queue_file": str(queue_path)}


class FanqieHttpAdapter(PublisherAdapter):
    """番茄作者后台 HTTP 适配器。

    Uses the same three-step chain as tools/publish_stock.py:
    new_article -> cover_article -> publish_article. Cookie/CSRF come from
    ~/.n8n/.env (FANQIE_COOKIE / FANQIE_CSRF_TOKEN).
    """

    def __init__(self, conn=None):
        self.conn = conn

    def publish(self, chapter_id, text, scheduled_at=None, as_draft=False):
        from novel_pipeline import config, db  # noqa: PLC0415
        from tools import publish_stock  # noqa: PLC0415

        if self.conn is None:
            self.conn = db.connect(config.DB_PATH)
        row = self.conn.execute(
            "SELECT c.id, c.novel_id, c.seq, c.title, "
            "COALESCE(cc.content, ?) AS content "
            "FROM chapters c LEFT JOIN chapter_content cc ON cc.chapter_id=c.id "
            "WHERE c.id=?",
            (str(text or ""), chapter_id),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"chapter {chapter_id} not found")
        env = publish_stock.load_env()
        ok, item_id, error = publish_stock.publish_chapter(self.conn, dict(row), env)
        if not ok:
            self.conn.execute(
                "INSERT INTO publish_logs(chapter_id,platform,action,result,error,ai_declared,created_at) "
                "VALUES(?,?,?,?,?,?,datetime('now','localtime'))",
                (chapter_id, "fanqie", "publish", "failed", str(error or "unknown")[:300], 1),
            )
            self.conn.commit()
            raise RuntimeError(error or "publish failed")
        if error:
            # Published but the verification list did not show it yet
            # (review latency): surface a warning instead of swallowing it.
            try:
                config.ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
                with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
                    f.write(
                        f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 章节 {row['seq']} "
                        f"发布复核警告：{error}\n"
                    )
            except Exception:  # noqa: BLE001
                pass
        self.conn.execute(
            "UPDATE chapters SET status='published', fanqie_item_id=?, published_at=? "
            "WHERE id=?",
            (
                item_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                chapter_id,
            ),
        )
        self.conn.execute(
            "INSERT INTO publish_logs(chapter_id,platform,action,result,error,ai_declared,created_at) "
            "VALUES(?,?,?,?,?,?,datetime('now','localtime'))",
            (chapter_id, "fanqie", "publish", "success", "", 1),
        )
        self.conn.commit()
        return {"result": "published", "item_id": item_id, "warning": error or ""}
