"""Ending readiness check (S16): the judge evaluates the active novel weekly
before the meeting, so the editorial office enters the finishing phase
proactively instead of waiting for an explicit decision."""

from __future__ import annotations

import json
from datetime import datetime

from novel_pipeline import config, db
from novel_pipeline.services import activity, audit
from tools import agent_tool_loop, editorial_steps


def _j(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _collect_indicators(conn, novel_id):
    novel = conn.execute(
        "SELECT id, title, status, target_chapters, finish_remaining, "
        "finish_note, volume_goal FROM novels WHERE id=?",
        (novel_id,),
    ).fetchone()
    if novel is None:
        return None
    published = conn.execute(
        "SELECT COUNT(*) c FROM chapters WHERE novel_id=? AND status='published'",
        (novel_id,),
    ).fetchone()["c"]
    threads = [
        str(r["description"])
        for r in conn.execute(
            "SELECT description FROM plot_threads WHERE novel_id=? AND status='open' "
            "ORDER BY planted_chapter LIMIT 8",
            (novel_id,),
        ).fetchall()
    ]
    summaries = [
        str(r["summary"])[:200]
        for r in conn.execute(
            "SELECT cs.summary FROM chapter_summaries cs "
            "JOIN chapters c ON c.id=cs.chapter_id "
            "WHERE c.novel_id=? ORDER BY c.seq DESC LIMIT 3",
            (novel_id,),
        ).fetchall()
    ]
    return {
        "id": novel["id"],
        "title": novel["title"],
        "status": novel["status"],
        "target_chapters": novel["target_chapters"] or 0,
        "finish_remaining": novel["finish_remaining"] or 0,
        "volume_goal": novel["volume_goal"] or "",
        "published_chapters": published,
        "open_plot_threads": threads,
        "recent_summaries": summaries,
    }


def check(conn, novel_id=0, dry_run=False, db_path=None):
    """Evaluate the active novel; applies finishing state when recommended."""
    if not novel_id:
        row = conn.execute(
            "SELECT id FROM novels WHERE status IN ('publishing','finishing') "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        novel_id = row["id"] if row else 0
    if not novel_id:
        return {"ok": True, "evaluated": False, "note": "没有连载中的作品"}
    indicators = _collect_indicators(conn, novel_id)
    if indicators is None:
        return {"ok": False, "error": "novel not found"}
    task = (
        "完结评估请求。作品信息：" + _j(indicators)
        + "。按你的规则输出 JSON。"
    )
    try:
        result = agent_tool_loop.run(
            "ending_judge",
            task,
            temperature=0.2,
            max_tokens=1200,
            novel_id=novel_id,
            db_path=db_path or config.DB_PATH,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"ending_judge failed: {str(exc)[:200]}"}
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "ending_judge failed")}
    obj = editorial_steps.robust_json(result.get("text") or "")
    if not isinstance(obj, dict):
        return {"ok": False, "error": "ending_judge output unparseable"}
    should_finish = bool(obj.get("should_finish"))
    remaining = max(0, int(obj.get("remaining_chapters") or 0))
    reasons = [str(x) for x in (obj.get("reasons") or []) if str(x)]
    changed = False
    if should_finish and not dry_run:
        cur = conn.execute(
            "UPDATE novels SET status='finishing', finish_remaining=?, finish_note=? "
            "WHERE id=? AND status IN ('publishing','finishing')",
            (remaining, "；".join(reasons)[:500] or "周检判定进入收尾", novel_id),
        )
        conn.commit()
        changed = cur.rowcount > 0
    audit.log(
        conn,
        "ending",
        "weekly_check",
        target_type="novel",
        target_id=novel_id,
        detail={
            "should_finish": should_finish,
            "remaining_chapters": remaining,
            "reasons": reasons,
            "story_progress": obj.get("story_progress"),
            "risks": obj.get("risks"),
            "dry_run": dry_run,
        },
    )
    activity.log_activity(
        conn,
        "ending_judge",
        novel_id,
        "ending_check",
        "周检完结评估",
        {
            "should_finish": should_finish,
            "remaining": remaining,
            "changed": changed,
        },
    )
    return {
        "ok": True,
        "evaluated": True,
        "novel_id": novel_id,
        "should_finish": should_finish,
        "remaining_chapters": remaining,
        "reasons": reasons,
        "changed": changed,
        "dry_run": dry_run,
    }


def main():
    import argparse
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="周检完结评估")
    ap.add_argument("--db", default=str(config.DB_PATH))
    ap.add_argument("--novel-id", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    conn = db.connect(args.db)
    try:
        print(
            json.dumps(
                check(conn, novel_id=args.novel_id, dry_run=args.dry_run, db_path=args.db),
                ensure_ascii=False,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
