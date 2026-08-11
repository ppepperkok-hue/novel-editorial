"""Auto-fill post-meeting action items from daily-run evidence.

After a daily run completes, pending agent_actions for the active book are
checked against today's pipeline outputs (published chapters, quality
reports, knowledge-base changes, character evolution). A cheap flash call
decides done/pending with a result note; on LLM failure a deterministic
keyword rule set is used so the meeting backlog never silently stalls.

Usage:
    python tools/auto_fill_actions.py [--db demo.db] [--novel-id N]
                                     [--days 1] [--dry-run] [--no-llm]
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import config, db  # noqa: E402
from novel_editorial.llm_client import chat_deepseek  # noqa: E402
from novel_editorial.services import activity  # noqa: E402
from novel_editorial.services import audit  # noqa: E402


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def resolve_novel_id(conn, novel_id=0):
    if novel_id:
        return int(novel_id)
    row = conn.execute(
        "SELECT id FROM novels WHERE status='publishing' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row:
        return row["id"]
    row = conn.execute("SELECT id FROM novels ORDER BY id DESC LIMIT 1").fetchone()
    return row["id"] if row else 0


def collect_evidence(conn, novel_id, days=1):
    """Aggregate today's pipeline outputs as evidence for action items."""
    from datetime import timedelta  # noqa: PLC0415

    since = (datetime.now() - timedelta(days=max(0, int(days or 1) - 1))).strftime("%Y-%m-%d")
    evidence = {"date": since, "novel_id": novel_id}

    rows = conn.execute(
        "SELECT pl.action, pl.result, pl.chapter_id, pl.error, pl.created_at "
        "FROM publish_logs pl JOIN chapters c ON c.id=pl.chapter_id "
        "WHERE pl.created_at >= ? AND c.novel_id=? ORDER BY pl.id",
        (since, novel_id),
    ).fetchall()
    evidence["publish_logs"] = [dict(r) for r in rows]

    rows = conn.execute(
        "SELECT seq, title, status, words, published_at FROM chapters "
        "WHERE novel_id=? AND published_at >= ? AND status='published' "
        "ORDER BY seq",
        (novel_id, since),
    ).fetchall()
    evidence["published_chapters"] = [dict(r) for r in rows]

    pub_ids = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM chapters WHERE novel_id=? "
            "AND published_at >= ? AND status='published'",
            (novel_id, since),
        ).fetchall()
    ]
    if pub_ids:
        marks = ",".join("?" * len(pub_ids))
        rows = conn.execute(
            f"SELECT chapter_id, passed FROM quality_reports "
            f"WHERE chapter_id IN ({marks}) ORDER BY id",
            pub_ids,
        ).fetchall()
        evidence["quality_reports"] = [dict(r) for r in rows]
    else:
        evidence["quality_reports"] = []

    rows = conn.execute(
        "SELECT category, entity, version, updated_at FROM novel_knowledge "
        "WHERE novel_id=? AND updated_at >= ? ORDER BY category, entity",
        (novel_id, since),
    ).fetchall()
    evidence["knowledge_changes"] = [dict(r) for r in rows]

    rows = conn.execute(
        "SELECT name, created_at FROM character_evolution "
        "WHERE novel_id=? AND created_at >= ? ORDER BY id",
        (novel_id, since),
    ).fetchall()
    evidence["character_changes"] = [dict(r) for r in rows]

    row = conn.execute(
        "SELECT title, genre, tags, abstract, protagonists, volume_goal "
        "FROM novels WHERE id=?",
        (novel_id,),
    ).fetchone()
    evidence["novel"] = dict(row) if row else {}
    return evidence


def rules_decide(task, evidence):
    """Deterministic fallback: keyword match against today's evidence."""
    text = str(task or "")
    published = evidence.get("published_chapters") or []
    pub_titles = "、".join(f"第{c['seq']}章 {c['title']}" for c in published)
    logs = evidence.get("publish_logs") or []
    ok_logs = [r for r in logs if r.get("result") == "success"]
    knowledge = evidence.get("knowledge_changes") or []
    quality = evidence.get("quality_reports") or []
    chars = evidence.get("character_changes") or []

    if published or ok_logs:
        if any(k in text for k in ("发布", "章节", "写", "更新", "补更", "存稿")):
            reason = (
                f"今日发布/产出章节：{pub_titles}"
                if pub_titles
                else f"今日发布记录 {len(ok_logs)} 条"
            )
            return True, reason
        if any(k in text for k in ("书名", "简介", "标签", "主角", "作品资料", "卷目标")):
            return True, "今日日更跑通，作品资料链路已正常产出"
    if knowledge and any(k in text for k in ("设定", "伏笔", "世界观", "台账", "知识")):
        entities = "、".join(f"{e['category']}·{e['entity']}" for e in knowledge[:6])
        return True, f"今日设定知识库变更：{entities}"
    if quality and any(k in text for k in ("审稿", "质量", "润色", "终审")):
        passed = sum(1 for r in quality if r.get("passed"))
        return True, f"今日质量门通过 {passed} 章"
    if chars and any(k in text for k in ("角色", "人设", "成长")):
        names = "、".join(c["name"] for c in chars[:6])
        return True, f"今日角色成长轨迹更新：{names}"
    return False, ""


def _parse_json(text):
    if not text:
        return None
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return None
    try:
        value = json.loads(m.group(0))
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, list):
        return None
    return [v for v in value if isinstance(v, dict) and v.get("id") is not None]


def llm_decide(actions, evidence):
    """One flash call deciding every pending action; returns {id: (status, result)}."""
    system = (
        "你是网文流水线的行动项回填器。根据今日流水线产出证据，判断每个会后任务"
        "是否已有明确完成证据。只输出 JSON 数组，每项 "
        '{"id": <数字>, "status": "done"|"pending", "result": "<一句完成证据或保持原因>"}。'
        "证据不足时保持 pending，不要臆测。"
    )
    user = json.dumps(
        {
            "今日产出证据": evidence,
            "待判定行动项": [
                {
                    "id": a["id"],
                    "agent": a["agent"],
                    "task": a["task"],
                    "detail": a.get("detail") or {},
                }
                for a in actions
            ],
        },
        ensure_ascii=False,
    )
    resp = chat_deepseek(
        "deepseek-v4-flash",
        system,
        user,
        temperature=0.2,
        max_tokens=1200,
    )
    items = _parse_json(resp.get("text") or "")
    if not items:
        return None
    decisions = {}
    ids = {a["id"] for a in actions}
    for item in items:
        try:
            aid = int(item["id"])
        except (TypeError, ValueError):
            continue
        if aid not in ids:
            continue
        status = str(item.get("status") or "").strip().lower()
        if status not in ("done", "pending"):
            continue
        decisions[aid] = (status, str(item.get("result") or "")[:500])
    return decisions


def run(db_path, novel_id=0, days=1, dry_run=False, use_llm=True):
    conn = db.connect(db_path)
    try:
        novel_id = resolve_novel_id(conn, novel_id)
        evidence = collect_evidence(conn, novel_id, days)
        pending = [
            a
            for a in activity.list_actions(
                conn, status=("pending", "claimed", "in_progress"), limit=500
            )
            if int(a["novel_id"] or 0) in (0, novel_id)
        ]
        if not pending:
            return {
                "ok": True,
                "checked": 0,
                "done": [],
                "kept_pending": [],
                "method": "none",
                "evidence": evidence,
            }

        decisions = None
        method = "rules"
        if use_llm:
            try:
                decisions = llm_decide(pending, evidence)
                if decisions is not None:
                    method = "llm"
            except Exception:  # noqa: BLE001 - fall back to rules on any LLM failure
                decisions = None

        done_ids, kept = [], []
        for a in pending:
            if decisions is not None and a["id"] in decisions:
                status, result = decisions[a["id"]]
            else:
                status, result = rules_decide(a["task"], evidence)
            status = "done" if status is True or status == "done" else "pending"
            if status == "done":
                done_ids.append({"id": a["id"], "agent": a["agent"], "result": result})
                if not dry_run:
                    activity.update_action(conn, a["id"], "done", result)
                    audit.log(
                        conn,
                        "agent",
                        "auto_fill_action",
                        target_type="action",
                        target_id=a["id"],
                        detail={
                            "agent": a["agent"],
                            "task": a["task"][:200],
                            "result": result[:300],
                            "method": method,
                        },
                    )
            else:
                kept.append({"id": a["id"], "agent": a["agent"], "result": result})
        return {
            "ok": True,
            "checked": len(pending),
            "done": done_ids,
            "kept_pending": kept,
            "method": method,
            "dry_run": dry_run,
            "evidence": evidence,
        }
    finally:
        conn.close()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="按日更产出自动回填会后行动项")
    ap.add_argument("--db", default=str(ROOT / "demo.db"))
    ap.add_argument("--novel-id", type=int, default=0)
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true", help="只判定不落库")
    ap.add_argument("--no-llm", action="store_true", help="只用规则判定，不调 LLM")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    result = run(
        str(db_path),
        novel_id=args.novel_id,
        days=args.days,
        dry_run=args.dry_run,
        use_llm=not args.no_llm,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
