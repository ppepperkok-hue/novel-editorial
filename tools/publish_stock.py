"""Publish N chapters from the stock pool (status='reviewed') to Fanqie.

Replicates the n8n publish chain: new_article -> cover_article -> publish_article.
Run from the pipeline root: python tools/publish_stock.py [--chapters N]
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import config, db  # noqa: E402
from novel_pipeline.services import audit  # noqa: E402

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


def load_env():
    """Shared env loader: ~/.n8n/.env filled in by config.load_env()."""
    return config.load_env()


def http_form(url, fields, env):
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Cookie": env.get("FANQIE_COOKIE", ""),
            "X-Secsdk-Csrf-Token": env.get("FANQIE_CSRF_TOKEN", ""),
            "User-Agent": UA,
            "Origin": "https://fanqienovel.com",
            "Referer": "https://fanqienovel.com/main/writer/",
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return json.loads(raw.decode("gbk", "ignore"))


def esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def to_html(text):
    paras = [p.strip() for p in str(text or "").splitlines() if p.strip()]
    if len(paras) <= 1:
        t = (paras[0] if paras else "").strip()
        paras = []
        buf = ""
        for ch in t:
            buf += ch
            if len(buf) >= 80 and "，。！？；".__contains__(ch):
                paras.append(buf.strip())
                buf = ""
        if buf.strip():
            paras.append(buf.strip())
    return "".join("<p>" + esc(p) + "</p>" for p in paras)


def publish_chapter(conn, chapter, env):
    """Publish one chapter; returns (ok, item_id, error)."""
    novel = conn.execute(
        "SELECT id, book_id FROM novels WHERE id=?",
        (chapter["novel_id"],),
    ).fetchone()
    book_id = str((novel["book_id"] if novel else "") or env.get("FANQIE_BOOK_ID", ""))
    if not book_id:
        return False, None, "缺少 book_id（新书未绑定）"

    content_html = to_html(chapter["content"] if chapter["content"] else "")
    title = chapter["title"] or f"第 {chapter['seq']} 章"

    # 1. create draft
    res = http_form(
        "https://fanqienovel.com/api/author/article/new_article/v0/",
        {
            "book_id": book_id,
            "need_reuse": "0",
            "aid": "2503",
            "app_name": "muye_novel",
        },
        env,
    )
    if res.get("code") != 0:
        return False, None, f"new_article: {res.get('message') or res}"
    data = res.get("data") or {}
    item_id = str(data.get("item_id") or "")
    if not item_id:
        return False, None, "new_article 未返回 item_id"
    vd = data.get("volume_data") or []
    volume_id = str(data.get("volume_id") or "")
    volume_name = "第一卷"
    if vd:
        hit = next(
            (v for v in vd if str(v.get("volume_id")) == volume_id),
            vd[0],
        )
        volume_id = str(hit.get("volume_id") or volume_id)
        volume_name = str(hit.get("volume_name") or volume_name)

    # 2. save content
    res = http_form(
        "https://fanqienovel.com/api/author/article/cover_article/v0/",
        {
            "book_id": book_id,
            "item_id": item_id,
            "title": title,
            "content": content_html,
            "volume_id": volume_id,
            "volume_name": volume_name,
            "aid": "2503",
            "app_name": "muye_novel",
        },
        env,
    )
    if res.get("code") != 0:
        return False, None, f"cover_article: {res.get('message') or res}"

    # 3. publish
    res = http_form(
        "https://fanqienovel.com/api/author/publish_article/v0/",
        {
            "item_id": item_id,
            "book_id": book_id,
            "content": content_html,
            "title": title,
            "volume_id": volume_id,
            "volume_name": volume_name,
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
        env,
    )
    if res.get("code") != 0:
        return False, None, f"publish_article: {res.get('message') or res}"
    # 4. verify (best-effort): the item should now appear in chapter_list/v1.
    try:
        verify_url = (
            "https://fanqienovel.com/api/author/chapter/chapter_list/v1?"
            + urllib.parse.urlencode(
                {
                    "aid": "2503",
                    "app_name": "muye_novel",
                    "book_id": book_id,
                    "page_index": "0",
                    "page_count": "50",
                }
            )
        )
        vreq = urllib.request.Request(
            verify_url,
            headers={
                "Cookie": env.get("FANQIE_COOKIE", ""),
                "X-Secsdk-Csrf-Token": env.get("FANQIE_CSRF_TOKEN", ""),
                "User-Agent": UA,
                "Origin": "https://fanqienovel.com",
                "Referer": "https://fanqienovel.com/main/writer/",
                "Accept": "application/json, text/plain, */*",
            },
        )
        with urllib.request.urlopen(vreq, timeout=20) as r:
            vbody = json.loads(r.read().decode("utf-8", "ignore"))
        if vbody.get("code") == 0:
            items = ((vbody.get("data") or {}).get("item_list")) or []
            found = any(str(x.get("item_id")) == str(item_id) for x in items)
            if not found:
                return True, item_id, "发布成功但复核未在章节列表找到（可能审核延迟）"
    except Exception:  # noqa: BLE001 - verification is best-effort
        pass
    return True, item_id, ""


def publish_batch(conn, novel_id, target, env):
    """Publish up to `target` reviewed chapters of `novel_id` to Fanqie.

    Library entry shared by the CLI and the Python scheduler. Keeps the n8n
    stock-publish semantics: publish, verify, update status/publish_logs,
    decrement finish_remaining and stop daily runs when a book ends.
    """
    novel = conn.execute(
        "SELECT id, status, finish_remaining FROM novels WHERE id=?",
        (novel_id,),
    ).fetchone()
    if novel is None or novel["status"] == "finished":
        return {
            "target": target,
            "published": 0,
            "failures": [],
            "warnings": ["作品已完结或无此作品，停止发布"],
        }
    rows = conn.execute(
        "SELECT c.id, c.novel_id, c.seq, c.title, c.status, "
        "COALESCE(cc.content, '') AS content "
        "FROM chapters c LEFT JOIN chapter_content cc ON cc.chapter_id=c.id "
        "WHERE c.status='reviewed' AND c.novel_id=? ORDER BY c.seq LIMIT ?",
        (novel_id, target),
    ).fetchall()
    if not rows:
        return {
            "target": target,
            "published": 0,
            "failures": [],
            "warnings": ["存稿池为空"],
        }

    published = 0
    failures = []
    warnings = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    remaining = int(novel["finish_remaining"] or 0)
    for ch in rows:
        try:
            ok, item_id, error = publish_chapter(conn, ch, env)
        except urllib.error.HTTPError as e:
            ok, item_id, error = False, None, f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001
            ok, item_id, error = False, None, str(e)[:200]
        if ok:
            if error:
                warnings.append({"chapter": ch["seq"], "warning": error})
                alerts = ROOT / "alerts.log"
                with alerts.open("a", encoding="utf-8") as f:
                    f.write(
                        f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                        f"章节 {ch['seq']} 发布复核警告：{error}\n"
                    )
            conn.execute(
                "UPDATE chapters SET status='published', fanqie_item_id=?, "
                "published_at=? WHERE id=?",
                (item_id, now, ch["id"]),
            )
            conn.execute(
                "INSERT INTO publish_logs(chapter_id,platform,action,result,error,ai_declared,created_at) "
                "VALUES(?,?,?,?,?,?,datetime('now','localtime'))",
                (ch["id"], "fanqie", "publish", "success", "", 1),
            )
            published += 1
            if remaining > 0:
                remaining -= 1
                if remaining <= 0:
                    conn.execute(
                        "UPDATE novels SET status='finished', finish_remaining=0 WHERE id=?",
                        (novel["id"],),
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO settings(key,value) "
                        "VALUES('daily_enabled','false')"
                    )
                    alerts = ROOT / "alerts.log"
                    with alerts.open("a", encoding="utf-8") as f:
                        f.write(
                            f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                            "小说已完结：收尾完成，日更已自动停止，请到番茄后台标记完结\n"
                        )
                else:
                    conn.execute(
                        "UPDATE novels SET finish_remaining=? WHERE id=?",
                        (remaining, novel["id"]),
                    )
        else:
            conn.execute(
                "INSERT INTO publish_logs(chapter_id,platform,action,result,error,ai_declared,created_at) "
                "VALUES(?,?,?,?,?,?,datetime('now','localtime'))",
                (ch["id"], "fanqie", "publish", "failed", error, 1),
            )
            failures.append({"chapter": ch["seq"], "error": error})
        conn.commit()
    summary = {
        "target": target,
        "published": published,
        "failures": failures,
        "warnings": warnings,
    }
    audit.log(
        conn,
        "publish",
        "stock_batch",
        target_type="novel",
        target_id=novel_id,
        detail=summary,
        source="publish",
    )
    return summary


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="从存稿池发布章节到番茄")
    ap.add_argument("--chapters", type=int, default=0, help="本次发布章数（默认读设置）")
    ap.add_argument("--db", default="demo.db")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    env = load_env()
    try:
        novel = None
        novel_id = None
        for r in conn.execute(
            "SELECT DISTINCT novel_id FROM chapters WHERE status='reviewed' "
            "ORDER BY novel_id"
        ).fetchall():
            cand = conn.execute(
                "SELECT id, status, finish_remaining FROM novels WHERE id=?",
                (r["novel_id"],),
            ).fetchone()
            if cand and cand["status"] != "finished":
                novel = cand
                novel_id = cand["id"]
                break
        if novel is None and conn.execute(
            "SELECT COUNT(*) c FROM chapters WHERE status='reviewed'"
        ).fetchone()["c"]:
            print(json.dumps({"ok": True, "published": 0, "note": "仅剩已完结作品的存稿，停止发布"}, ensure_ascii=False))
            return
        if novel and novel["status"] == "finished":
            print(json.dumps({"ok": True, "published": 0, "note": "作品已完结，停止发布"}, ensure_ascii=False))
            return
        settings = {
            r["key"]: r["value"]
            for r in conn.execute("SELECT key, value FROM settings").fetchall()
        }
        target = args.chapters or int(settings.get("pending_publish") or 0) or int(
            settings.get("daily_chapters") or 2
        )
        target = max(1, min(target, 10))
        if settings.get("pending_publish"):
            conn.execute(
                "UPDATE settings SET value='0' WHERE key='pending_publish'"
            )
            conn.commit()

        summary = publish_batch(conn, novel_id, target, env)
        print(json.dumps({"ok": True, **summary}, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
