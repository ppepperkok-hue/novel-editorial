"""Re-publish chapters 1-2 with proper paragraph breaks."""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, r"C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2")
ROOT = Path(r"E:\code\novel-pipeline")
sys.path.insert(0, str(ROOT))

from novel_pipeline import db  # noqa: E402
from tools.debug.paragraphs import to_html  # noqa: E402

BOOK_ID = os.environ.get("FANQIE_BOOK_ID", "YOUR_FANQIE_BOOK_ID")
VOLUME_ID = os.environ.get("FANQIE_VOLUME_ID", "YOUR_FANQIE_VOLUME_ID")
VOLUME_NAME = os.environ.get("FANQIE_VOLUME_NAME", "第一卷：默认")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)
ENV = Path.home() / ".n8n" / ".env"


def load_env():
    for line in open(ENV, encoding="utf-8"):
        line = line.strip()
        if line and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def req(path, params, method="POST"):
    headers = {
        "Cookie": os.environ["FANQIE_COOKIE"],
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://fanqienovel.com",
        "Referer": "https://fanqienovel.com/main/writer/",
        "X-Secsdk-Csrf-Token": os.environ["FANQIE_CSRF_TOKEN"],
    }
    url = "https://fanqienovel.com" + path
    data = None
    if method == "POST":
        data = urllib.parse.urlencode(params).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"
    else:
        url += "?" + urllib.parse.urlencode(params)
    r = urllib.request.urlopen(
        urllib.request.Request(url, data=data, headers=headers, method=method), timeout=30
    )
    return json.loads(r.read().decode())


def get_content(item_id):
    d = req(
        "/api/author/edit_article/v0/",
        {"book_id": BOOK_ID, "item_id": item_id, "from_source": "0"},
        method="GET",
    )
    data = d["data"]
    return data.get("title") or "", re.sub(r"<[^>]+>", "", data.get("content") or "")


def delete_chapter(item_id):
    for is_draft in ("0", "1"):
        try:
            d = req(
                "/api/author/delete_article/v1",
                {"book_id": BOOK_ID, "item_id": item_id, "is_draft": is_draft},
            )
            if d.get("code") == 0:
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def new_draft():
    d = req(
        "/api/author/article/new_article/v0/",
        {"book_id": BOOK_ID, "need_reuse": "0", "aid": "2503", "app_name": "muye_novel"},
    )
    if d.get("code") != 0:
        raise RuntimeError("new_article: " + str(d))
    return d["data"]["item_id"]


def cover_draft(item_id, title, content_html):
    d = req(
        "/api/author/article/cover_article/v0/",
        {
            "book_id": BOOK_ID,
            "item_id": item_id,
            "title": title,
            "content": content_html,
            "volume_id": VOLUME_ID,
            "volume_name": VOLUME_NAME,
            "aid": "2503",
            "app_name": "muye_novel",
        },
    )
    if d.get("code") != 0:
        raise RuntimeError("cover_article: " + str(d))


def publish_chapter(item_id, title, content):
    return req(
        "/api/author/publish_article/v0/",
        {
            "item_id": item_id,
            "book_id": BOOK_ID,
            "content": content,
            "title": title,
            "volume_id": VOLUME_ID,
            "volume_name": VOLUME_NAME,
            "timer_status": "0",
            "timer_time": "0",
            "publish_status": "1",
            "need_pay": "0",
            "use_ai": "2",
            "device_platform": "pc",
            "speak_type": "0",
            "timer_chapter_preview": "[]",
            "has_chapter_ad": "false",
            "chapter_ad_types": "",
            "aid": "2503",
            "app_name": "muye_novel",
        },
    )


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    load_env()
    old_items = {}
    for part in os.environ.get("FANQIE_OLD_ITEMS", "").split(","):
        part = part.strip()
        if ":" in part:
            seq_s, item = part.split(":", 1)
            old_items[int(seq_s.strip())] = item.strip()
    chapters = []
    for seq in (1, 2):
        title, plain = get_content(old_items[seq])
        html = to_html(plain)
        print("seq", seq, "title", title, "paras:", html.count("<p>"))
        ok = delete_chapter(old_items[seq])
        print("  delete old:", ok)
        item_id = new_draft()
        cover_draft(item_id, title, html)
        d = publish_chapter(item_id, title, html)
        print("  publish:", d.get("code"), d.get("message"))
        chapters.append(
            {
                "seq": seq,
                "title": title,
                "status": "published" if d.get("code") == 0 else "draft",
                "fanqie_item_id": item_id,
                "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": "" if d.get("code") == 0 else json.dumps(d, ensure_ascii=False),
            }
        )

    conn = db.connect(ROOT / "demo.db")
    for c in chapters:
        conn.execute(
            "UPDATE chapters SET fanqie_item_id=?, status=?, published_at=?, words=? "
            "WHERE novel_id=(SELECT id FROM novels WHERE book_id=?) AND seq=?",
            (
                c["fanqie_item_id"],
                c["status"],
                c["published_at"],
                c.get("words", 0),
                BOOK_ID,
                c["seq"],
            ),
        )
    conn.commit()
    conn.close()
    print("DONE", chapters)


if __name__ == "__main__":
    main()
