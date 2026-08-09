"""发布适配器：平台无关接口 + 人工确认通道 + 番茄 HTTP 适配器骨架。"""

import json
import os
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

    需要环境变量 TOMATO_COOKIE / TOMATO_CSRF_TOKEN（登录态约 1-2 个月失效）。
    生产实现建议直接复用开源 tomato-writer-mcp 的 publish_chapter 能力，
    避免自行逆向接口签名。
    """

    def publish(self, chapter_id, text, scheduled_at=None, as_draft=False):
        cookie = os.environ.get("TOMATO_COOKIE")
        csrf = os.environ.get("TOMATO_CSRF_TOKEN")
        if not cookie or not csrf:
            raise RuntimeError("缺少 TOMATO_COOKIE / TOMATO_CSRF_TOKEN，请从番茄作者后台登录态获取。")
        # TODO: 接入 tomato-writer-mcp publish_chapter（HTTP + CSRF，支持定时发布）
        return {"result": "stub", "note": "接入 tomato-writer-mcp 后实现真实发布"}
