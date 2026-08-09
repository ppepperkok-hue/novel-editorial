"""网文热点爬取：榜单页 HTML 抓取（尽力而为）+ CSV 手工兜底。

注意：番茄/起点榜单可能由前端渲染或有反爬，抓不到时降级为 CSV 输入，
不阻塞流水线。选题灵感参考 DaisyWriter 与 webnovel-reverse-analysis。
"""

import argparse
import csv
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

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


def clean_title(raw):
    return re.sub(r"<[^>]+>", "", raw).strip()


def parse_rank_html(html, source="qidian"):
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


def refresh(out_path="hot_topics.json", sources=None, fetcher=None):
    """抓取各榜单并落盘 hot_topics.json；单个源失败不影响整体。"""
    sources = sources or SOURCES
    fetcher = fetcher or fetch_rank
    results = []
    for source in sources:
        try:
            html = fetcher(source)
            titles = parse_rank_html(html, source=source["name"])
            results.append({
                "source": source["name"],
                "url": source["url"],
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(titles),
                "titles": titles[:50],
            })
        except Exception as exc:  # noqa: BLE001
            results.append({
                "source": source["name"],
                "url": source["url"],
                "error": str(exc),
                "titles": [],
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
