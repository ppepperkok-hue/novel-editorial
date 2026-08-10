"""Auto-create a new Fanqie book for a confirmed novel, then bind book_id.

Endpoint (validated by OpenNovel and webnovel-writer-opencode):
    POST /api/author/book/create/v0/
Prereqs:
    GET /api/author/book/category_list/v0/?gender=   -> category_id
    GET /api/author/book/group_category_list/v0/?gender= -> label ids
After creation:
    GET /api/author/volume/volume_list/v1/?book_id=  -> volume_id

Platform limit: at most 1 new book per day (Fanqie side).
Auth: same cookie + CSRF token used by publish_stock.py.

Run from the pipeline root:
    python tools/create_book.py --novel-id N
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
from novel_pipeline.services import audit, ending  # noqa: E402

BASE = "https://fanqienovel.com"
COMMON = {"aid": "2503", "app_name": "muye_novel"}
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

# Female-only genres; anything with a male keyword below stays male (gender=1).
_FEMALE_GENRES = {"言情", "女频", "现代言情", "古代言情", "仙侠言情", "豪门", "穿越", "宫斗"}
_MALE_KEYWORDS = ("仙侠", "玄幻", "武侠", "男频", "都市", "科幻")


def load_env():
    env = {}
    if config.N8N_ENV_FILE.exists():
        for line in config.N8N_ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def http_json(method, path, fields, env):
    if method == "POST":
        url = BASE + path + "?" + urllib.parse.urlencode(COMMON)
        body = urllib.parse.urlencode(fields).encode("utf-8")
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


def _find_category_id(categories, genre):
    def get_name(c):
        return c.get("name") or c.get("category_name") or ""

    for c in categories or []:
        if get_name(c) == genre:
            return int(c["category_id"])
    for c in categories or []:
        name = get_name(c)
        if genre in name or name in genre:
            return int(c["category_id"])
    if categories:
        return int(categories[0]["category_id"])
    return 0


def _find_label_ids(labels, genre, tags, max_count=4):
    def get_name(l):
        return l.get("label_name") or l.get("name") or ""

    def get_id(l):
        v = l.get("label_id") or l.get("id") or l.get("category_id")
        return str(v) if v else ""

    tokens = set((genre or "") + " " + " ".join(tags or []))
    selected = []
    for l in labels or []:
        name = get_name(l)
        lid = get_id(l)
        if not name or not lid:
            continue
        if any(ch in name for ch in tokens) or name in genre or name in tags:
            selected.append(lid)
        if len(selected) >= max_count:
            break
    if not selected:
        selected = [get_id(l) for l in (labels or [])[:2] if get_id(l)]
    return selected


def _build_abstract(text):
    abstract = " ".join(
        line.strip() for line in str(text or "").splitlines() if line.strip()
    )
    if len(abstract) < 50:
        abstract += "。" * (50 - len(abstract))
    return abstract


def _get_category_id(env, gender, genre):
    res = http_json(
        "GET", "/api/author/book/category_list/v0/", {"gender": gender}, env
    )
    if res.get("code") != 0:
        raise RuntimeError(f"category_list: {res.get('message') or res}")
    data = res.get("data")
    categories = data if isinstance(data, list) else (data or {}).get("category_list", [])
    return _find_category_id(categories, genre)


def _get_label_ids(env, gender, genre, tags):
    res = http_json(
        "GET", "/api/author/book/group_category_list/v0/", {"gender": gender}, env
    )
    if res.get("code") != 0:
        raise RuntimeError(f"group_category_list: {res.get('message') or res}")
    data = res.get("data")
    labels = []
    if isinstance(data, list):
        labels = data
    elif isinstance(data, dict):
        for group in data.get("group_list") or data.get("label_list") or []:
            if isinstance(group, dict):
                labels.extend(group.get("label_list") or group.get("labels") or [])
    return _find_label_ids(labels, genre, tags)


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
        category_id = _get_category_id(env, gender, genre)
        label_ids = _get_label_ids(env, gender, genre, tags)
        p_names = [_clean_protagonist_name(p.get("name")) for p in protagonists[:2]]
        p1 = p_names[0] if len(p_names) > 0 else ""
        p2 = p_names[1] if len(p_names) > 1 else ""
        res = http_json(
            "POST",
            "/api/author/book/create/v0/",
            {
                "book_name": title,
                "gender": str(gender),
                "abstract": _build_abstract(row["abstract"] or row["premise"] or ""),
                "category_id": str(category_id),
                "original_type": "1",
                "label_id_list": ",".join(label_ids),
                "protagonist_name_1": p1,
                "protagonist_name_2": p2,
            },
            env,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, ValueError) as exc:
        return {"ok": False, "error": f"建书请求失败：{exc}"}

    if res.get("code") != 0:
        msg = str(res.get("message") or res)
        if "每天" in msg or "当日" in msg or "1" in msg:
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
                "category_id": category_id, "label_ids": label_ids},
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
