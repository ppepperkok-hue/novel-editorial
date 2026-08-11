"""Auto-create a new Fanqie book for a confirmed novel, then bind book_id.

Endpoint (validated against the real writer console, 2026-08-11):
    POST /api/author/book/create/v0/
Prereqs:
    GET /api/author/book/category_list/v0/?gender= -> label list
        (label in {"主分类", "主题", "角色", "情节"})
    GET /api/author/activity/activity_list/v0/     -> default activity
After creation:
    GET /api/author/volume/volume_list/v1/?book_id=  -> volume_id

Platform limit: at most 1 new book per day (Fanqie side).
Auth: same cookie + CSRF token used by publish_stock.py.

Request shape (copied from the browser's real POST body):
    aid, app_name, book_name, roles (JSON array string), category (comma
    joined category ids), gender, thumb_uri (default cover), abstract,
    activity_id, is_self_pic, group_category_id (main category id, only
    sent when an activity is selected).

Run from the pipeline root:
    python tools/create_book.py --novel-id N
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import config, db  # noqa: E402
from novel_pipeline.services import audit, ending  # noqa: E402

BASE = "https://fanqienovel.com"
COMMON = {"aid": "2503", "app_name": "muye_novel"}
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

DEFAULT_THUMB_URI = "novel-static/7107d91219967759d105674fa8393923"
MAIN_LABEL = "主分类"
EXTRA_LABELS = ("主题", "角色", "情节")
MAX_EXTRA_LABELS = 2
MAX_PROTAGONISTS = 2

# Female-only genres; anything with a male keyword below stays male (gender=1).
_FEMALE_GENRES = {"言情", "女频", "现代言情", "古代言情", "仙侠言情", "豪门", "宫斗"}
_MALE_KEYWORDS = ("仙侠", "玄幻", "武侠", "男频", "都市", "科幻")


def load_env():
    """Shared env loader: ~/.n8n/.env filled in by config.load_env()."""
    return config.load_env()


def http_json(method, path, fields, env):
    if method == "POST":
        url = BASE + path + "?" + urllib.parse.urlencode(COMMON)
        body = urllib.parse.urlencode({**COMMON, **fields}).encode("utf-8")
    else:
        url = BASE + path + "?" + urllib.parse.urlencode({**COMMON, **fields})
        body = None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
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


def _gender(genre):
    if any(g in genre for g in _FEMALE_GENRES) and not any(
        m in genre for m in _MALE_KEYWORDS
    ):
        return 0
    return 1


def _clean_protagonist_name(name):
    """Strip annotations like （孙悟空） or /alias; Fanqie rejects those chars."""
    import re

    name = re.sub(r"（[^）]*）", "", str(name or ""))
    name = re.sub(r"\([^)]*\)", "", name)
    name = name.split("/")[0].strip()
    return name[:5]


def _category_name(c):
    return c.get("name") or c.get("category_name") or ""


def _category_id(c):
    return c.get("category_id") or c.get("id") or 0


def _pick_main_category(categories, genre):
    """Pick exactly one main category (label == 主分类).

    Fanqie's category_list is actually the *label* list: every entry has
    ``label`` in {"主分类", "主题", "角色", "情节"}. Only one main category may
    be sent; matching is exact first, then substring either way, then first.
    """
    mains = [
        c for c in categories or []
        if (c.get("label") or "") == MAIN_LABEL and _category_id(c)
    ]
    if not mains:
        return None
    for c in mains:
        if _category_name(c) == genre:
            return c
    for c in mains:
        name = _category_name(c)
        if genre and (genre in name or name in genre):
            return c
    return mains[0]


def _pick_extra_categories(categories, tags, max_count=MAX_EXTRA_LABELS):
    """Pick theme/role/plot labels matching the novel tags (at most 2)."""
    extras = [
        c for c in categories or []
        if (c.get("label") or "") in EXTRA_LABELS and _category_id(c)
    ]
    tags = [str(t) for t in (tags or []) if str(t).strip()]
    picked = []
    for c in extras:
        name = _category_name(c)
        if not name:
            continue
        if name in tags or any(name in t or t in name for t in tags):
            picked.append(c)
        if len(picked) >= max_count:
            break
    return picked


def _build_abstract(text):
    abstract = " ".join(
        line.strip() for line in str(text or "").splitlines() if line.strip()
    )
    if len(abstract) < 50:
        abstract += "。" * (50 - len(abstract))
    return abstract


def _get_categories(env, gender):
    res = http_json(
        "GET", "/api/author/book/category_list/v0/", {"gender": gender}, env
    )
    if res.get("code") != 0:
        raise RuntimeError(f"category_list: {res.get('message') or res}")
    data = res.get("data")
    return data if isinstance(data, list) else []


def _get_activity_id(env, gender, main_category_id):
    """Pick the default activity that supports the chosen main category.

    The writer console blocks creating a book without an activity, and only
    offers activities whose ``group_categorys`` (``"{gender}_{category_id}"``)
    contains the selected main category. ``is_default_choose=1`` wins.
    Returns "" when nothing matches; the create call then omits
    ``group_category_id`` exactly like the console does.
    """
    res = http_json(
        "GET", "/api/author/activity/activity_list/v0/", {}, env
    )
    if res.get("code") != 0:
        return ""
    data = res.get("data") or {}
    acts = (
        data.get("activity_list", [])
        if isinstance(data, dict)
        else (data if isinstance(data, list) else [])
    )
    key = f"{gender}_{main_category_id}"
    supported = [
        a for a in acts
        if not a.get("group_categorys") or key in (a.get("group_categorys") or [])
    ]
    for a in supported:
        if a.get("is_default_choose") == 1:
            return str(a.get("activity_id") or "")
    if supported:
        return str(supported[0].get("activity_id") or "")
    return ""


def _get_volume_id(env, book_id):
    res = http_json(
        "GET", "/api/author/volume/volume_list/v1/", {"book_id": book_id}, env
    )
    if res.get("code") != 0:
        raise RuntimeError(f"volume_list: {res.get('message') or res}")
    data = res.get("data")
    volumes = data if isinstance(data, list) else (data or {}).get("volume_list", [])
    if volumes:
        return str(volumes[0].get("volume_id") or "")
    return ""


def create_book_on_fanqie(conn, novel_id):
    """Create the book on Fanqie and bind it to the local novel row."""
    row = conn.execute(
        "SELECT id, title, genre, abstract, premise, protagonists, tags, status, book_id "
        "FROM novels WHERE id=?",
        (novel_id,),
    ).fetchone()
    if row is None:
        return {"ok": False, "error": f"novel {novel_id} not found"}
    if row["status"] != "ready":
        return {"ok": False, "error": f"状态不是 ready（当前 {row['status']}），请先确认创意"}
    if row["book_id"]:
        return {"ok": False, "error": f"已绑定 book_id={row['book_id']}，无需重复建书"}

    env = load_env()
    if not env.get("FANQIE_COOKIE"):
        return {"ok": False, "error": "缺少 FANQIE_COOKIE，请先配置番茄登录态"}

    title = str(row["title"] or "").strip()[:50]
    genre = str(row["genre"] or "").strip()
    if not title or not genre:
        return {"ok": False, "error": "书名或类型为空，无法建书"}

    tags = []
    try:
        tags = json.loads(row["tags"] or "[]")
    except (TypeError, json.JSONDecodeError):
        tags = []
    protagonists = []
    try:
        protagonists = json.loads(row["protagonists"] or "[]")
    except (TypeError, json.JSONDecodeError):
        protagonists = []

    gender = _gender(genre)
    try:
        categories = _get_categories(env, gender)
        main = _pick_main_category(categories, genre)
        if main is None:
            return {"ok": False, "error": "未能从番茄分类列表中找到主分类"}
        extras = _pick_extra_categories(categories, tags)
        activity_id = _get_activity_id(env, gender, int(_category_id(main)))
        p_names = [
            _clean_protagonist_name(p.get("name"))
            for p in protagonists[:MAX_PROTAGONISTS]
        ]
        p_names = [n for n in p_names if n][:MAX_PROTAGONISTS]
        fields = {
            "book_name": title,
            "roles": json.dumps(p_names, ensure_ascii=False, separators=(",", ":")),
            "category": ",".join(
                str(_category_id(c)) for c in [main, *extras]
            ),
            "gender": str(gender),
            "thumb_uri": DEFAULT_THUMB_URI,
            "abstract": _build_abstract(row["abstract"] or row["premise"] or ""),
            "activity_id": activity_id,
            "is_self_pic": "0",
        }
        if activity_id:
            fields["group_category_id"] = str(_category_id(main))
        res = http_json("POST", "/api/author/book/create/v0/", fields, env)
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, ValueError) as exc:
        return {"ok": False, "error": f"建书请求失败：{exc}"}

    if res.get("code") != 0:
        msg = str(res.get("message") or res)
        if "每天" in msg or "当日" in msg or "每日" in msg:
            msg += "（番茄每天最多创建 1 本新书，失败当天无法重试）"
        return {"ok": False, "error": f"番茄拒绝建书：{msg}"}

    data = res.get("data") or {}
    book_id = str(data.get("book_id") or "")
    if not book_id:
        return {"ok": False, "error": f"建书响应缺少 book_id：{res}"}

    volume_id = ""
    try:
        volume_id = _get_volume_id(env, book_id)
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, ValueError):
        volume_id = ""

    bound = ending.bind_book(conn, novel_id, book_id, volume_id)
    if not bound.get("ok"):
        return {"ok": False, "error": f"建书成功但绑定失败：{bound.get('error')}", "book_id": book_id}

    audit.log(
        conn,
        "ending",
        "create_book",
        target_type="novel",
        target_id=novel_id,
        detail={"book_id": book_id, "volume_id": volume_id, "gender": gender,
                "category": fields["category"],
                "group_category_id": fields.get("group_category_id", ""),
                "activity_id": activity_id, "thumb_uri": DEFAULT_THUMB_URI},
    )
    conn.commit()
    return {
        "ok": True,
        "book_id": book_id,
        "volume_id": volume_id,
        "note": f"已在番茄创建《{title}》并绑定 book_id={book_id}",
    }


def main():
    ap = argparse.ArgumentParser(description="Auto-create a Fanqie book and bind it")
    ap.add_argument("--db", default=str(config.DB_PATH))
    ap.add_argument("--novel-id", type=int, required=True)
    args = ap.parse_args()
    conn = db.connect(Path(args.db))
    try:
        result = create_book_on_fanqie(conn, args.novel_id)
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
