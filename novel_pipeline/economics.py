"""副业盈利测算：输入成本与收益参数，估算月净利与盈亏平衡。

番茄全勤现实门槛：签约 + 累计有效过审 10 万字 + 当月听读分成 ≥ 500 元 +
每日更新 4000/6000 字且当日过审。本模块把这一门槛显式建模。
"""

import argparse
import json
import sys

ATTENDANCE_GATE_SHARE = 500.0  # 激活全勤所需当月听读分成（元）


def monthly_model(cost_per_chapter=0.3, chapters_per_day=2, days=30,
                  full_attendance=600.0, listening_share=100.0,
                  share_rate=0.05, other_income=0.0, overhead=0.0):
    chapters = chapters_per_day * days
    cost = cost_per_chapter * chapters
    attendance_active = listening_share >= ATTENDANCE_GATE_SHARE
    attendance_bonus = full_attendance if attendance_active else 0.0
    share_bonus = listening_share * share_rate if attendance_active else 0.0
    income = attendance_bonus + listening_share + share_bonus + other_income

    base_gap = cost + overhead - attendance_bonus - other_income
    if attendance_active:
        required = base_gap / (1 + share_rate)
        effective = max(required, ATTENDANCE_GATE_SHARE) if full_attendance > 0 else required
    else:
        required = base_gap
        effective = max(required, 0.0)

    return {
        "chapters": chapters,
        "cost": round(cost, 2),
        "attendance_active": attendance_active,
        "attendance_bonus": round(attendance_bonus, 2),
        "listening_share": round(listening_share, 2),
        "share_bonus": round(share_bonus, 2),
        "other_income": round(other_income, 2),
        "overhead": round(overhead, 2),
        "income": round(income, 2),
        "profit": round(income - cost - overhead, 2),
        "break_even_listening_share": round(effective, 2),
        "note": "盈亏平衡的听读分成为估算值；全勤实际还需满足 10 万字与日更门槛",
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="副业盈利测算")
    ap.add_argument("--cost-per-chapter", type=float, default=0.3)
    ap.add_argument("--chapters-per-day", type=int, default=2)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--full-attendance", type=float, default=600.0)
    ap.add_argument("--listening-share", type=float, default=100.0)
    ap.add_argument("--share-rate", type=float, default=0.05)
    ap.add_argument("--other-income", type=float, default=0.0)
    ap.add_argument("--overhead", type=float, default=0.0)
    args = ap.parse_args()
    print(json.dumps(monthly_model(
        cost_per_chapter=args.cost_per_chapter,
        chapters_per_day=args.chapters_per_day,
        days=args.days,
        full_attendance=args.full_attendance,
        listening_share=args.listening_share,
        share_rate=args.share_rate,
        other_income=args.other_income,
        overhead=args.overhead,
    ), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
