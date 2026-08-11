"""生成演示数据：让监控面板第一次打开就有可看的示例（书、章节、质量报告、发布日志）。"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import db

DEMO_NOVEL = {
    "title": "重启：从高三教室开始",
    "genre": "都市重生",
    "premise": "林舟重生回到高考前三个月，用未来记忆改写全家命运。",
    "selling_point": "重生改写命运",
}


def seed(conn, chapters=5, published=2, reviewed=2):
    if min(chapters, published, reviewed) < 0:
        raise ValueError("chapters/published/reviewed must be non-negative")
    published = min(published, chapters)
    reviewed = min(reviewed, chapters - published)
    draft = chapters - published - reviewed
    nid = db.add_novel(
        conn,
        DEMO_NOVEL["title"],
        DEMO_NOVEL["genre"],
        DEMO_NOVEL["premise"],
        selling_point=DEMO_NOVEL["selling_point"],
        platform="fanqie",
    )
    vid = db.add_volume(conn, nid, 1, "第一卷：高考前的三个月")
    statuses = ["published"] * published + ["reviewed"] * reviewed + ["draft"] * draft
    for seq, status in enumerate(statuses, start=1):
        cid = db.add_chapter(conn, nid, vid, seq, f"第{seq}章 演示章节")
        words = 1800 + seq * 50
        if status == "draft":
            conn.execute("UPDATE chapters SET words=?, status='draft' WHERE id=?", (words, cid))
            conn.commit()
            continue
        score = round(7.0 + (seq % 3) * 0.8, 1)
        db.update_chapter_after_review(conn, cid, words, score, True)
        db.add_quality_report(
            conn,
            cid,
            {"words": 9, "plot": 8, "style": 7, "punctuation": 9, "coherence": 8},
            True,
            revision_count=seq % 3,
        )
        if status == "published":
            db.add_publish_log(conn, cid, "fanqie", "publish", "ok", ai_declared=1)
            conn.execute("UPDATE chapters SET status='published' WHERE id=?", (cid,))
            conn.commit()
    return nid


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="生成监控面板演示数据")
    ap.add_argument("--db", default="demo.db")
    ap.add_argument("--chapters", type=int, default=5)
    ap.add_argument("--published", type=int, default=2)
    ap.add_argument("--reviewed", type=int, default=2)
    args = ap.parse_args()
    if min(args.chapters, args.published, args.reviewed) < 0:
        print("seed 失败：chapters/published/reviewed must be non-negative", file=sys.stderr)
        sys.exit(1)
    conn = db.connect(args.db)
    nid = seed(conn, chapters=args.chapters, published=args.published,
               reviewed=args.reviewed)
    print(f"演示数据已写入 {args.db}：小说 ID={nid}，共 {args.chapters} 章。")


if __name__ == "__main__":
    main()
