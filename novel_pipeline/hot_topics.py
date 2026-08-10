"""网文热点爬取：榜单页 HTML 抓取（尽力而为）+ CSV 手工兜底。

注意：番茄/起点榜单可能由前端渲染或有反爬，抓不到时降级为 CSV 输入，
不阻塞流水线。选题灵感参考 DaisyWriter 与 webnovel-reverse-analysis。
"""

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from novel_pipeline.services import knowledge

SOURCES = [
    {"name": "zongheng_rank", "url": "https://www.zongheng.com/rank/", "parser": "zongheng"},
    {"name": "fanqie_rank", "url": "https://fanqienovel.com/rank", "parser": "fanqie"},
    {"name": "qidian_rank", "url": "https://www.qidian.com/rank/hotsales/", "parser": "qidian"},
]

GENRE_KEYWORDS = [
    "重生", "穿越", "系统", "修仙", "都市", "玄幻", "神豪", "直播",
    "电竞", "校园", "总裁", "甜宠", "悬疑", "无限流", "末世", "星际",
    "武侠", "仙侠", "女频", "历史",
]

TITLE_RE = re.compile(r'<a[^>]+class="[^"]*book-name[^"]*"[^>]*>(.*?)</a>', re.S)
TITLE_ATTR_RE = re.compile(r'<a[^>]+title="([^"]{2,50})"')

BROWSER_EXTRACT_JS = (
    "JSON.stringify([...new Set([...document.querySelectorAll('a')]"
    ".filter(a=>(a.href||'').includes('/page/')||(a.href||'').includes('/book/'))"
    ".map(a=>{var p=a;for(var i=0;i<4&&p;i++){p=p.parentElement;"
    "if(p&&(p.innerText||'').length>20){break}}"
    "return {u:a.href,t:p?(p.innerText||''):''}})"
    ".filter(x=>x.t&&x.t.trim().length>2))])"
)

NAV_NOISE = {
    "首页", "书库", "书架", "原创榜", "作家专区", "版权专区", "番茄小说",
    "帮助中心", "作家助手", "登录", "注册", "退出", "排行", "全部作品",
    "完本", "免费", "搜索", "女生网", "客户端", "页游", "起点中文网",
    "起点女生网", "繁体版", "我的书架", "人气榜单", "月票榜", "畅销榜",
    "阅读指数榜", "书友榜", "推荐榜", "收藏榜", "消息()", "GO>", "排行",
}

STATUS_WORDS = {"连载", "完结", "全本", "太监", "停更", "作品状态"}
LATEST_NOISE = {"书籍详情", "加入书架", "立即阅读", "开始阅读", "书友圈"}


def clean_title(raw):
    return re.sub(r"<[^>]+>", "", raw).strip()


def parse_rank_html(html):
    """从榜单 HTML 提取书名列表（best-effort，规则随页面结构演进）。"""
    titles = [clean_title(m) for m in TITLE_RE.findall(html)]
    titles += [clean_title(t) for t in TITLE_ATTR_RE.findall(html)]
    seen, out = set(), []
    for title in titles:
        if title and title not in seen:
            seen.add(title)
            out.append(title)
    return out


def count_keywords(titles):
    counts = {}
    for title in titles:
        for kw in GENRE_KEYWORDS:
            if kw in title:
                counts[kw] = counts.get(kw, 0) + 1
    return sorted(counts.items(), key=lambda item: -item[1])[:10]


def fetch_rank(source, timeout=20):
    req = urllib.request.Request(
        source["url"],
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


_BB_CMD = None


def _bb_cmd():
    """Resolve a reliable bb-browser invocation (node cli.js, no shell)."""
    global _BB_CMD
    if _BB_CMD is not None:
        return _BB_CMD
    which = shutil.which("bb-browser") or ""
    if which.endswith(".js"):
        _BB_CMD = ["node", which]
        return _BB_CMD
    if Path(which).suffix.lower() in (".cmd", ".bat", ".ps1"):
        cli = Path(which).resolve().parent / "node_modules" / "bb-browser" / "dist" / "cli.js"
        if cli.exists():
            _BB_CMD = ["node", str(cli)]
            return _BB_CMD
    _BB_CMD = ["bb-browser"]
    return _BB_CMD


def _bb_run(args, timeout=60):
    return subprocess.run(
        [*_bb_cmd(), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def parse_browser_books(items, source):
    """Parse browser-extracted {u,t} items into book details.

    Fanqie items (href /page/): lines = title, author, tags/intro.
    Qidian items (href /book/): lines = rank, title, author, tags,
    status, intro, 最新更新, chapter, time.
    """
    books = []
    for item in items or []:
        href = str(item.get("u") or "")
        lines = [
            knowledge.clean_title(l)
            for l in str(item.get("t") or "").splitlines()
        ]
        lines = [l for l in lines if l and l not in NAV_NOISE]
        if not lines:
            continue
        title = ""
        author = ""
        intro_lines = []
        latest = ""
        if "/page/" in href:
            # fanqie: title / author / tags+intro
            title = lines[0] if lines else ""
            author = lines[1] if len(lines) > 1 else ""
            rest = lines[2:]
        else:
            # qidian: rank / title / author / tags / status / intro / 最新更新...
            idx = 0
            if lines and lines[0].isdigit():
                idx = 1
            title = lines[idx] if len(lines) > idx else ""
            author = lines[idx + 1] if len(lines) > idx + 1 else ""
            rest = lines[idx + 2 :]
        intro_lines = []
        for i, line in enumerate(rest):
            if "更新" in line:
                latest = " ".join(t for t in rest[i : i + 3] if t)
                break
            intro_lines.append(line)
        if not title or len(title) > 40:
            continue
        intro = ""
        for line in intro_lines:
            if not line:
                continue
            if line.startswith(("[", "（", "(", "【")):
                continue
            if line in STATUS_WORDS:
                continue
            if len(line) <= 15 and ("·" in line or "：" in line or "|" in line):
                continue
            if len(line) <= 8 and "卷" in line:
                continue
            intro = (intro + " " + line).strip()
            if len(intro) >= 120:
                intro = intro[:120]
                break
        latest = " ".join(
            t for t in latest.split() if t not in LATEST_NOISE
        )
        books.append(
            {
                "title": title,
                "author": author,
                "intro": intro[:120],
                "latest": latest[:60],
                "url": href,
                "source": source,
            }
        )
    seen, out = set(), []
    for b in books:
        if b["title"] not in seen:
            seen.add(b["title"])
            out.append(b)
    return out[:50]


def fetch_rank_browser(source):
    """Fetch a rank page through bb-browser (real browser identity).

    bb-browser daemon may restart, so a fresh tab is opened per fetch and
    closed afterwards; tab ids are never cached.
    """
    out = _bb_run(["open", source["url"], "--json"])
    if out.returncode != 0:
        raise RuntimeError(f"bb-browser open failed: {out.stderr.strip()[:200]}")
    try:
        opened = json.loads(out.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"bb-browser open output unparsable: {exc}") from exc
    tab = opened["result"].get("tab") or opened["result"].get("tabId")
    if not tab:
        raise RuntimeError("bb-browser returned no tab id")
    time.sleep(4)
    eval_out = _bb_run(["eval", BROWSER_EXTRACT_JS, "--tab", tab, "--json"])
    try:
        _bb_run(["eval", "window.close()", "--tab", tab, "--json"], timeout=20)
    except Exception:  # noqa: BLE001 - closing is best-effort
        pass
    if eval_out.returncode != 0:
        raise RuntimeError(f"bb-browser eval failed: {eval_out.stderr.strip()[:200]}")
    try:
        payload = json.loads(eval_out.stdout.strip())
        raw = payload["result"]["result"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"bb-browser eval output unparsable: {exc}") from exc
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = [raw]
    return parse_browser_books(raw, source["name"])


def refresh(out_path="hot_topics.json", sources=None, fetcher=None, browser_fallback=True):
    """抓取各榜单并落盘 hot_topics.json；单个源失败不影响整体。"""
    sources = sources or SOURCES
    fetcher = fetcher or fetch_rank
    results = []
    for source in sources:
        method = "html"
        error = ""
        try:
            html = fetcher(source)
            titles = parse_rank_html(html)
        except Exception as exc:  # noqa: BLE001
            titles = []
            error = str(exc)
        books = []
        if not titles and browser_fallback:
            method = "browser"
            try:
                books = fetch_rank_browser(source)
                titles = [b["title"] for b in books]
                error = ""
            except Exception as exc:  # noqa: BLE001
                error = f"html: {error or 'empty'}; browser: {str(exc)[:200]}"
        results.append({
                "source": source["name"],
                "url": source["url"],
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "method": method,
                "count": len(titles),
                "titles": titles[:50],
                "books": books,
                "error": error,
            })
    payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sources": results,
        "top_keywords": count_keywords(
            [title for r in results for title in r.get("titles", [])]
        ),
    }
    Path(out_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def from_csv(path):
    """CSV 兜底：列 title,genre,heat（可选）。"""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append({
                "title": r.get("title", ""),
                "genre": r.get("genre", ""),
                "heat": r.get("heat", ""),
            })
    titles = [r["title"] for r in rows if r["title"]]
    return {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": f"csv:{path}",
        "rows": rows,
        "titles": titles,
        "top_keywords": count_keywords(titles),
    }


def to_premise_candidates(payload, n=3):
    """把热点结果转成 Planner 选题候选：参考热门题材、换一套设定。"""
    titles = [t for src in payload.get("sources", []) for t in src.get("titles", [])]
    titles = titles or payload.get("titles", [])
    return [
        f"参考热门题材《{t}》写一本网文：题材类型相同，但世界观、金手指与主角身份全部换新，避免同质化"
        for t in titles[:n]
    ]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="网文热点爬取")
    ap.add_argument("--refresh", action="store_true", help="抓取在线榜单并写 hot_topics.json")
    ap.add_argument("--from-csv", metavar="FILE", help="从 CSV 手工数据生成热点（兜底）")
    ap.add_argument("--out", default="hot_topics.json")
    args = ap.parse_args()
    if args.refresh:
        payload = refresh(out_path=args.out)
    elif args.from_csv:
        payload = from_csv(args.from_csv)
        Path(args.out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        raise SystemExit("请指定 --refresh 或 --from-csv FILE")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
