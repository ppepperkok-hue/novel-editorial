"""Editorial workday (R4-1): open -> morning -> producing -> awaiting_close
-> closing (manual). The workday is the primary driver: nothing autonomous
happens while the office is closed.

Library entry:
    workday.open(conn, chapters=None, trigger="manual", mode="write", ...)
    workday.close(conn, run_id, ...)
    workday.resume(conn, run_id, ...)

The daily_runs row created here is the same row the produce chain updates
(workday_run_id), so the panel sees one workday, not two runs.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import config, db  # noqa: E402
from novel_editorial.services import audit  # noqa: E402
from tools import app_settings, preflight, producers  # noqa: E402

MODES = ("write", "org", "meeting", "free")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _j(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _update(conn, run_id, **fields):
    sets = ", ".join(f"{k}=?" for k in fields)
    conn.execute(
        f"UPDATE daily_runs SET {sets}, updated_at=? WHERE run_id=?",
        (*fields.values(), _now(), run_id),
    )
    conn.commit()


def _current_novel_id(conn):
    row = conn.execute("SELECT id FROM novels ORDER BY id DESC LIMIT 1").fetchone()
    return row["id"] if row else 0


def _diaries_written(conn, novel_id, started_at):
    """True when daily diaries already exist inside this workday window."""
    row = conn.execute(
        "SELECT COUNT(*) c FROM agent_diaries "
        "WHERE novel_id=? AND diary_type='daily' AND created_at>=?",
        (novel_id or 0, str(started_at or "")),
    ).fetchone()
    return bool(row and row["c"])


def _default_producer(conn):
    """Workday producer from settings; the novel chain remains the default."""
    name = app_settings.get_str(conn, "workday_producer", "novel")
    return name if name in producers.PRODUCERS else "novel"


def _recover_stale_open(conn, stale_hours=12):
    """Recover workday rows stuck mid-run by a crashed process, mirroring
    daily_runs.recover_stale_runs. awaiting_close is a deliberate decision
    point, so it is never auto-recovered."""
    row = conn.execute(
        "SELECT run_id, phase, status FROM daily_runs "
        "WHERE source='workday' AND phase NOT IN ('finished','awaiting_close') "
        "AND started_at < datetime('now','localtime',?) "
        "ORDER BY id DESC LIMIT 1",
        (f"-{int(stale_hours)} hours",),
    ).fetchone()
    if row is None:
        return None
    conn.execute(
        "UPDATE daily_runs SET status='failed', phase='finished', "
        "finished_at=datetime('now','localtime'), error=?, detail=? "
        "WHERE run_id=?",
        (
            "进程中断或超时（孤立恢复）",
            _j({"recovered": True, "stale_phase": row["phase"]}),
            row["run_id"],
        ),
    )
    conn.commit()
    audit.log(
        conn, "workday", "stale_recovered",
        target_type="run", target_id=row["run_id"],
        detail={"phase": row["phase"], "status": row["status"], "stale_hours": stale_hours},
    )
    return row["run_id"]


def _morning_plan(conn, run_id, mode, boss_instruction, dry_run, db_path):
    """Editor-in-chief (or deterministic fallback) sets today's plan."""
    if mode == "write":
        plan = {
            "produce": True, "producer": _default_producer(conn),
            "target": None, "chapters": None, "meeting": False,
            "focus": "按今日产出计划执行",
        }
    elif mode == "org":
        plan = {
            "produce": False, "producer": "none", "target": 0,
            "chapters": 0, "meeting": False,
            "focus": "整理日：知识库/人物卡/消息/议题",
        }
    elif mode == "meeting":
        plan = {
            "produce": False, "producer": "none", "target": 0,
            "chapters": 0, "meeting": True, "focus": "开会日：启动会议",
        }
    else:
        plan = {
            "produce": True, "producer": _default_producer(conn),
            "target": None, "chapters": None, "meeting": False,
            "focus": "主编现场决定",
        }
    if mode == "free" or (boss_instruction and mode not in ("org", "meeting")):
        task = (
            "你是主编。今日老板指令：" + str(boss_instruction or "自由安排")
            + "。请只输出 JSON：{produce(bool), producer(产出器名，默认 novel), "
            "target(整数或null), "
            "meeting(bool), focus(一句话)}。"
        )
        if dry_run:
            text = (
                '{"produce": true, "producer": "novel", "target": null, '
                '"meeting": false, '
                '"focus": "按任务板与今日主题安排"}'
            )
        else:
            from tools import agent_tool_loop  # noqa: PLC0415

            r = agent_tool_loop.run(
                "eic", task, temperature=0.2, max_tokens=800,
                novel_id=0, db_path=str(db_path),
            )
            text = r.get("text") or ""
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            parsed = json.loads(text[start:end])
            if isinstance(parsed, dict):
                plan = {
                    "produce": bool(parsed.get("produce", plan["produce"])),
                    "producer": str(parsed.get("producer") or "novel"),
                    "target": parsed.get("target") or parsed.get("chapters") or None,
                    "chapters": parsed.get("target") or parsed.get("chapters") or None,
                    "meeting": bool(parsed.get("meeting", False)),
                    "focus": str(parsed.get("focus") or plan["focus"])[:200],
                }
        except (ValueError, json.JSONDecodeError):
            pass  # deterministic fallback stays
    if not dry_run:
        _update(conn, run_id, today_plan=_j(plan), phase="morning")
    return plan


def open(conn, chapters=None, trigger="manual", mode="write", boss_instruction="",
         dry_run=False, db_path=None):
    """Open the office and run a workday up to the awaiting_close decision
    point. Never auto-closes: the boss decides (close / meeting / resume)."""
    if mode not in MODES:
        return {"ok": False, "error": f"mode must be one of {MODES}"}
    if db_path is None:
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
    db_path = str(Path(db_path).resolve())
    # R11-A2-03: a process killed during opening/morning/producing must not
    # lock the office forever; stale rows are recovered like daily_runs.
    _recover_stale_open(conn)
    active = conn.execute(
        "SELECT run_id, phase, status FROM daily_runs "
        "WHERE source='workday' AND phase!='finished' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if active is not None:
        return {
            "ok": False,
            "error": (
                f"上一个工作日尚未收工（#{active['run_id']}，"
                f"阶段 {active['phase']}），请先收工或继续"
            ),
            "locked": False,
        }
    lock_path = ROOT / "n8n_tmp" / (Path(db_path).stem + ".lock")
    locked, reason = preflight.acquire_lock(lock_path)
    if not locked:
        return {"ok": False, "error": str(reason), "locked": False}
    run_id = (
        "workday-" + datetime.now().strftime("%Y%m%d%H%M%S")
        + "-" + uuid.uuid4().hex[:6]
    )
    novel_id = _current_novel_id(conn)
    if not dry_run:
        conn.execute(
            "INSERT INTO daily_runs(run_id, novel_id, trigger, source, status, "
            "phase, mode, boss_instruction, started_at, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                run_id, novel_id, trigger, "workday", "running", "opening",
                mode, str(boss_instruction or "")[:200], _now(), _now(),
            ),
        )
        conn.commit()
    try:
        plan = _morning_plan(
            conn, run_id, mode, boss_instruction, dry_run, db_path
        )
        if not dry_run:
            try:
                from tools import mailroom  # noqa: PLC0415

                mailroom.broadcast(
                    conn, "eic", list(config.AGENT_NAMES),
                    subject="开工",
                    body="编辑部开工了。今日安排：" + _j(plan),
                    novel_id=novel_id,
                )
            except Exception as exc:  # noqa: BLE001
                audit.log(
                    conn, "workday", "open_broadcast_failed",
                    target_type="run", target_id=run_id,
                    detail={"error": str(exc)[:200]},
                )
        produce = None
        if plan.get("produce"):
            if not dry_run:
                _update(conn, run_id, phase="producing")
            producer = plan.get("producer") or "novel"
            if producer not in producers.PRODUCERS:
                audit.log(
                    conn, "workday", "producer_fallback",
                    target_type="run", target_id=run_id,
                    detail={"requested": producer, "fallback": "novel"},
                )
                producer = "novel"
            produce = producers.run_producer(
                producer,
                conn,
                target=chapters or plan.get("target"),
                trigger=trigger,
                dry_run=dry_run,
                db_path=db_path,
                workday_run_id=run_id,
                lock_held=True,
            )
        else:
            if not dry_run:
                _update(conn, run_id, published=0, status="skipped")
            produce = {"status": "skipped", "published": 0}
        if not dry_run:
            _update(conn, run_id, phase="awaiting_close")
        return {
            "ok": True,
            "run_id": run_id,
            "status": "awaiting_close",
            "mode": mode,
            "plan": plan,
            "produce": produce,
        }
    except Exception as exc:  # noqa: BLE001
        if not dry_run:
            _update(
                conn, run_id, status="failed", phase="finished",
                error=str(exc)[:400],
            )
        return {"ok": False, "error": str(exc)[:400], "run_id": run_id}
    finally:
        preflight.release_lock(lock_path)


def resume(conn, run_id, chapters=None, dry_run=False, db_path=None):
    """Continue producing from the decision point (partial follow-up)."""
    row = conn.execute("SELECT * FROM daily_runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        return {"ok": False, "error": "run not found"}
    if row["phase"] != "awaiting_close":
        return {"ok": False, "error": f"cannot resume from phase {row['phase']}"}
    if db_path is None:
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
    db_path = str(Path(db_path).resolve())
    lock_path = ROOT / "n8n_tmp" / (Path(db_path).stem + ".lock")
    locked, reason = preflight.acquire_lock(lock_path)
    if not locked:
        return {"ok": False, "error": str(reason), "locked": False}
    try:
        if not dry_run:
            _update(conn, run_id, phase="producing", status="running")
        try:
            plan = json.loads(row["today_plan"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            plan = {}
        producer = plan.get("producer") or "novel"
        if producer not in producers.PRODUCERS:
            producer = "novel"
        result = producers.run_producer(
            producer,
            conn,
            target=chapters or plan.get("target"),
            trigger="manual",
            dry_run=dry_run,
            db_path=db_path,
            workday_run_id=run_id,
            lock_held=True,
            skip_diaries=_diaries_written(conn, row["novel_id"], row["started_at"]),
        )
        if not dry_run:
            _update(conn, run_id, phase="awaiting_close")
        return {"ok": True, "run_id": run_id, "status": "awaiting_close", "produce": result}
    finally:
        preflight.release_lock(lock_path)


def close(conn, run_id, dry_run=False, db_path=None):
    """Manually close the workday: collaborate -> diaries -> backlog ->
    broadcast -> terminal status. This is the only way to finish a workday."""
    row = conn.execute("SELECT * FROM daily_runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        return {"ok": False, "error": "run not found"}
    if row["status"] == "finished":
        return {"ok": False, "error": "already finished"}
    if row["phase"] not in ("awaiting_close", "producing"):
        return {"ok": False, "error": f"cannot close from phase {row['phase']}"}
    if db_path is None:
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
    db_path = str(Path(db_path).resolve())
    lock_path = ROOT / "n8n_tmp" / (Path(db_path).stem + ".lock")
    locked, reason = preflight.acquire_lock(lock_path)
    if not locked:
        return {"ok": False, "error": str(reason), "locked": False}
    try:
        return _close_locked(conn, run_id, dry_run, row)
    finally:
        preflight.release_lock(lock_path)


def _close_locked(conn, run_id, dry_run, row):
    if not dry_run:
        _update(conn, run_id, phase="closing")
    unread = conn.execute(
        "SELECT COUNT(*) c FROM agent_messages WHERE status='unread'"
    ).fetchone()["c"]
    open_promises = conn.execute(
        "SELECT COUNT(*) c FROM agent_promises WHERE status='open'"
    ).fetchone()["c"]
    pending_actions = conn.execute(
        "SELECT COUNT(*) c FROM agent_actions "
        "WHERE status IN ('pending','claimed','in_progress')"
    ).fetchone()["c"]
    collab = {
        "unread_messages": unread,
        "open_promises": open_promises,
        "pending_actions": pending_actions,
    }
    if not dry_run:
        _update(conn, run_id, collab_summary=_j(collab))
    if not dry_run:
        # R10-A2-01: daily() 的 _wrapup 已在 produce 日写过 daily 日记，
        # close 只补写非产出日（org/meeting 等），避免同一工作日双写。
        already_diaries = _diaries_written(conn, row["novel_id"], row["started_at"])
        if already_diaries:
            audit.log(
                conn, "workday", "diaries_skipped",
                target_type="run", target_id=run_id,
                detail={"reason": "daily diaries already written by the produce chain"},
            )
        else:
            try:
                from tools import write_diaries  # noqa: PLC0415

                write_diaries.write(conn, row["novel_id"] or 0, "daily")
            except Exception as exc:  # noqa: BLE001
                audit.log(
                    conn, "workday", "diaries_failed",
                    target_type="run", target_id=run_id,
                    detail={"error": str(exc)[:200]},
                )
    published = int(row["published"] or 0)
    produce_status = str(row["status"] or "running")
    legacy = {}
    if produce_status in ("partial", "failed"):
        legacy["pending"] = "昨日主产出未完成，今天晨会优先处理"
    if pending_actions:
        legacy["pending_actions"] = pending_actions
    if produce_status in ("completed", "skipped"):
        final_status = "completed_with_pending" if legacy else "completed"
    elif published > 0:
        final_status = "partial"
    else:
        final_status = "failed"
    if not dry_run:
        try:
            from tools import mailroom  # noqa: PLC0415

            mailroom.broadcast(
                conn, "eic", list(config.AGENT_NAMES),
                subject="收工",
                body="今天的工作结束了。收工小结：" + _j(collab),
                novel_id=row["novel_id"] or 0,
            )
            _milestone_broadcast(conn, row["novel_id"] or 0)
        except Exception as exc:  # noqa: BLE001
            audit.log(
                conn, "workday", "broadcast_failed",
                target_type="run", target_id=run_id,
                detail={"error": str(exc)[:200]},
            )
    if not dry_run:
        _update(
            conn, run_id, status=final_status, phase="finished",
            legacy=_j(legacy),
        )
        audit.log(
            conn, "workday", "closed",
            target_type="run", target_id=run_id,
            detail={"status": final_status, "published": published, "legacy": legacy},
        )
    return {
        "ok": final_status in ("completed", "completed_with_pending"),
        "run_id": run_id, "status": final_status,
        "published": published, "collab": collab, "legacy": legacy,
    }


def _milestone_broadcast(conn, novel_id):
    """R4-3: celebrate published chapters at 100-chapter milestones once each."""
    total = conn.execute(
        "SELECT COUNT(*) c FROM chapters "
        "WHERE novel_id=? AND status='published'",
        (novel_id,),
    ).fetchone()["c"]
    if not total or total % 100 != 0:
        return
    dup = conn.execute(
        "SELECT id FROM audit_logs WHERE action='milestone' "
        "AND target_id=? AND detail LIKE ?",
        (str(novel_id), f'%"chapters": {total}%'),
    ).fetchone()
    if dup:
        return
    from tools import mailroom  # noqa: PLC0415

    mailroom.broadcast(
        conn, "eic", list(config.AGENT_NAMES),
        subject="里程碑",
        body=f"作品已发布第 {total} 章，编辑部一起纪念一下。",
        novel_id=novel_id,
    )
    audit.log(
        conn, "meeting", "milestone",
        target_type="novel", target_id=str(novel_id),
        detail={"chapters": total},
    )


def main():
    """CLI: python tools/workday.py --action open|close|resume [--mode ...]"""
    import argparse  # noqa: PLC0415

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="editorial workday")
    ap.add_argument("--action", choices=["open", "close", "resume"], required=True)
    ap.add_argument("--db", default="demo.db")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--mode", default="write", choices=list(MODES))
    ap.add_argument("--chapters", type=int, default=None)
    ap.add_argument("--trigger", default="manual", choices=["manual", "scheduled"])
    ap.add_argument("--boss", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    try:
        if args.action == "open":
            result = open(
                conn, chapters=args.chapters, trigger=args.trigger,
                mode=args.mode, boss_instruction=args.boss,
                dry_run=args.dry_run, db_path=str(db_path),
            )
        elif args.action == "close":
            result = close(conn, args.run_id, dry_run=args.dry_run, db_path=str(db_path))
        else:
            result = resume(
                conn, args.run_id, chapters=args.chapters,
                dry_run=args.dry_run, db_path=str(db_path),
            )
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
