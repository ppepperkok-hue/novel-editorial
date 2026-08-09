"""数据回采与反馈：读章节阅读数据 CSV，计算完读率/追读率，标记低质章节。"""

import argparse
import csv
import statistics
import sys

DEFAULT_THRESHOLDS = {"finish_rate": 0.20, "follow_rate": 0.30}


def load_reader_stats(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    "chapter": int(r["chapter"]),
                    "finish_rate": float(r["finish_rate"]),
                    "follow_rate": float(r["follow_rate"]),
                })
            except (KeyError, ValueError, TypeError):
                continue
    return rows


def low_performers(rows, thresholds=None):
    t = thresholds or DEFAULT_THRESHOLDS
    return [
        r["chapter"] for r in rows
        if r["finish_rate"] < t["finish_rate"] or r["follow_rate"] < t["follow_rate"]
    ]


def feedback_report(rows, thresholds=None):
    if not rows:
        return {"chapters": 0, "avg_finish": 0.0, "avg_follow": 0.0, "low_chapters": []}
    avg_finish = statistics.mean(r["finish_rate"] for r in rows)
    avg_follow = statistics.mean(r["follow_rate"] for r in rows)
    return {
        "chapters": len(rows),
        "avg_finish": round(avg_finish, 4),
        "avg_follow": round(avg_follow, 4),
        "low_chapters": low_performers(rows, thresholds),
        "note": "低于阈值的章节应反查大纲节奏与章节钩子",
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="数据回采反馈")
    ap.add_argument("--file", required=True, help="章节阅读数据 CSV")
    ap.add_argument("--finish-threshold", type=float, default=DEFAULT_THRESHOLDS["finish_rate"])
    ap.add_argument("--follow-threshold", type=float, default=DEFAULT_THRESHOLDS["follow_rate"])
    args = ap.parse_args()
    rows = load_reader_stats(args.file)
    thresholds = {"finish_rate": args.finish_threshold, "follow_rate": args.follow_threshold}
    print(feedback_report(rows, thresholds))


if __name__ == "__main__":
    main()
