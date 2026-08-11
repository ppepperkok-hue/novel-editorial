"""Detect AI-flavoured writing: flowery words, filler phrases, weak rhythm.

Usage: python tools/ai_taste_check.py --chapter-id N [--db demo.db]
       python tools/ai_taste_check.py --file text.txt
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import db  # noqa: E402

FLOWERY = [
    "璀璨", "耀眼", "磅礴", "深邃", "浩瀚", "凛冽", "炽热", "幽深", "玄奥", "古朴",
    "恢弘", "震撼", "惊艳", "沸腾", "激荡", "澎湃", "缱绻", "氤氲", "旖旎", "峥嵘",
    "逶迤", "潋滟", "斑驳", "绰约", "呢喃", "澄澈", "静谧", "苍茫", "辽阔", "巍峨",
    "蜿蜒", "笼罩", "萦绕", "弥漫", "迸发", "喷薄", "倾泻", "翻涌", "铺天盖地",
    "如诗如画", "美轮美奂", "如梦似幻", "不可思议", "无法言喻", "难以名状",
    "心潮澎湃", "热血沸腾", "气势磅礴", "威压滔天", "深不可测", "高深莫测",
    "神秘莫测", "玄之又玄", "仙气飘飘", "不怒自威",
]

FILLER = [
    "突然", "不由自主", "情不自禁", "微微一愣", "缓缓说道", "一股强大的气息",
    "与此同时", "这一刻", "就在这时", "不是…而是", "值得注意的是", "使得",
    "仿佛", "似乎", "隐约", "轻轻", "微微", "缓缓", "默默", "暗暗",
]

EXCLAMATION_PATTERN = re.compile(
    r"[！！]{2,}|[？？]{2,}|！？|？！|\?{2,}|！\?|？!"
)


def count_occurrences(text, words):
    hits = {}
    for w in words:
        c = text.count(w)
        if c:
            hits[w] = c
    return hits


def detect(text):
    if not text:
        return {"score": 0, "flowery": {}, "filler": {}, "density": 0, "notes": []}
    total = len(text)
    per500 = max(1, total / 500)
    flowery = count_occurrences(text, FLOWERY)
    filler = count_occurrences(text, FILLER)
    flowery_n = sum(flowery.values())
    filler_n = sum(filler.values())
    density = round(flowery_n / per500, 2)
    notes = []
    if density > 2:
        notes.append(f"华丽辞藻密度 {density}/500字，超过阈值 2")
    elif density > 0:
        notes.append(f"华丽辞藻密度 {density}/500字，可接受但留意")
    if filler_n > 6:
        notes.append(f"AI 味短语命中 {filler_n} 次（{', '.join(list(filler)[:5])}…）")
    exclam = len(EXCLAMATION_PATTERN.findall(text))
    if exclam > 3:
        notes.append(f"连续感叹/问号 {exclam} 处")
    # parallel four-character stacking heuristic: count adjacent 4-char
    # sequences by their real positions (text.find() gave wrong offsets when
    # a phrase repeated).
    positions = [m.start() for m in re.finditer(r"[\u4e00-\u9fff]{4}", text)]
    runs = 0
    i = 0
    while i < len(positions) - 1:
        if positions[i + 1] - positions[i] == 4:
            j = i + 1
            while j < len(positions) - 1 and positions[j + 1] - positions[j] == 4:
                j += 1
            if j > i:
                runs += 1
            i = j + 1
        else:
            i += 1
    if runs >= 2:
        notes.append(f"疑似四字排比堆砌 {runs} 处")
    score = min(100, round(flowery_n * 8 + filler_n * 3 + exclam * 4 + runs * 6))
    return {
        "score": score,
        "flowery": flowery,
        "filler": filler,
        "density": density,
        "notes": notes,
        "chars": total,
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="AI 味检测")
    ap.add_argument("--chapter-id", type=int)
    ap.add_argument("--file")
    ap.add_argument("--db", default="demo.db")
    args = ap.parse_args()

    text = ""
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.chapter_id:
        db_path = Path(args.db)
        if not db_path.is_absolute():
            db_path = ROOT / db_path
        conn = db.connect(db_path)
        try:
            row = conn.execute(
                "SELECT content FROM chapter_content WHERE chapter_id=?", (args.chapter_id,)
            ).fetchone()
            text = row["content"] if row else ""
        finally:
            conn.close()
    report = detect(text)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
