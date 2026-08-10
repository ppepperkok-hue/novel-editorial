"""Knowledge keeper: scheduled maintenance of prompts/knowledge packages.

Reads hot topics, current knowledge packages, pending drafts and recent
quality/reader signals, then asks the 博闻 (knowledge_keeper) agent to
produce auto_updates (market packages only), draft_suggestions and
deprecations. Market updates are applied immediately and audited; craft
suggestions and deprecations land in knowledge_drafts for human review.

CLI:
    python tools/knowledge_keeper.py [--db PATH] [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import config, db  # noqa: E402
from novel_pipeline.llm_client import chat_deepseek, estimate_cost  # noqa: E402
from novel_pipeline.services import audit, knowledge  # noqa: E402


def _parse_json(text):
    if not text:
        return None
    try:
        return json.loads(text[text.find("{") : text.rfind("}") + 1])
    except (ValueError, IndexError):
        return None


def _input_payload(conn):
    packages = []
    for item in knowledge.list_knowledge():
        full = knowledge.read_knowledge(item["file"])
        packages.append(
            {
                "file": item["file"],
                "title": item["title"],
                "type": item["type"],
                "agents": item["agents"],
                "updated_at": item["updated_at"],
                "body_tail": (full["body"] if full else "")[-800:],
            }
        )
    hot = {}
    if config.HOT_TOPICS_JSON.exists():
        try:
            hot = json.loads(config.HOT_TOPICS_JSON.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            hot = {}
    drafts = knowledge.list_drafts(conn, status="draft")[:30]
    quality = conn.execute(
        "SELECT COUNT(*) total, COALESCE(SUM(passed),0) passed "
        "FROM quality_reports"
    ).fetchone()
    failed = conn.execute(
        "SELECT COUNT(*) c FROM publish_logs WHERE result='failed' "
        "AND created_at >= datetime('now','localtime','-7 days')"
    ).fetchone()
    return {
        "packages": packages,
        "hot_topics": {
            "updated_at": hot.get("updated_at", ""),
            "top_keywords": hot.get("top_keywords", []),
            "sources": [
                {
                    "source": s.get("source"),
                    "method": s.get("method"),
                    "count": s.get("count", 0),
                    "error": s.get("error", ""),
                }
                for s in (hot.get("sources") or [])
            ],
            "titles": [
                t
                for s in (hot.get("sources") or [])
                for t in (s.get("titles") or [])
            ][:60],
        },
        "pending_drafts": [
            {
                "id": d["id"],
                "kind": d["kind"],
                "title": d["title"],
                "content": d["content"][:400],
                "agents": d["agents"],
                "source": d["source"],
            }
            for d in drafts
        ],
        "quality": {
            "total": quality["total"] or 0,
            "passed": quality["passed"] or 0,
        },
        "publish_failed_7d": failed["c"] or 0,
    }


def run(conn, dry_run=False):
    payload = _input_payload(conn)
    agent_md = (config.AGENTS_DIR / "knowledge_keeper.md").read_text(encoding="utf-8")
    prompt = (
        "请按你的[日常维护模式]维护知识库。只输出JSON，不要其他文字。"
        "输入数据：" + json.dumps(payload, ensure_ascii=False)
    )
    if dry_run:
        text = (
            '{"auto_updates": [], "draft_suggestions": '
            '[{"title":"dry-run 建议","content":"观察一周再定","agents":["planner"]}], '
            '"deprecations": []}'
        )
    else:
        resp = chat_deepseek(
            "deepseek-v4-flash", agent_md, prompt,
            temperature=0.3, max_tokens=2400,
        )
        text = resp["text"]
        conn.execute(
            "INSERT INTO cost_logs(novel_id,node_name,model,prompt_tokens,completion_tokens,cost,created_at) "
            "VALUES(?,?,?,?,?,?,datetime('now','localtime'))",
            (
                0,
                "知识管家",
                resp["model"],
                int(resp["usage"].get("prompt_tokens") or 0),
                int(resp["usage"].get("completion_tokens") or 0),
                estimate_cost(resp["model"], resp["usage"]),
            ),
        )
        conn.commit()
    parsed = _parse_json(text) or {}
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "auto_updates": [i.get("file") for i in (parsed.get("auto_updates") or [])],
            "draft_suggestions": len(parsed.get("draft_suggestions") or []),
            "deprecations": len(parsed.get("deprecations") or []),
        }

    market_files = {
        item["file"]
        for item in knowledge.list_knowledge()
        if item["type"] == "market"
    }
    auto = []
    skipped = []
    for item in parsed.get("auto_updates") or []:
        file = str(item.get("file") or "")
        body = str(item.get("body") or "").strip()
        if file not in market_files or not body:
            continue
        full = knowledge.read_knowledge(file)
        if full is None:
            continue
        old_len = len((full.get("body") or "").strip())
        if old_len and len(body) < old_len * 0.5:
            # model shrank the package too much: route to human review
            knowledge.add_draft(
                conn, "knowledge",
                f"知识包更新建议：{full['meta'].get('title') or file}",
                body,
                agent="knowledge_keeper",
                source="keeper:auto",
                agents=full["meta"].get("agents") or [],
            )
            skipped.append(file)
            continue
        meta = dict(full["meta"])
        meta["keywords"] = full["meta"].get("keywords") or []
        meta["source"] = full["meta"].get("source") or ""
        knowledge.write_knowledge(file, meta, body)
        audit.log(
            conn, "knowledge", "keeper_auto_update",
            target_type="knowledge", target_id=file,
            detail={"updated_at": full["meta"].get("updated_at")},
        )
        auto.append(file)

    drafts = 0
    for item in parsed.get("draft_suggestions") or []:
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        if not title or not content:
            continue
        agents = item.get("agents") or []
        if isinstance(agents, str):
            agents = [agents]
        knowledge.add_draft(
            conn, "knowledge", title, content,
            agent="knowledge_keeper", source="keeper:auto",
            agents=[a for a in agents if a],
        )
        drafts += 1

    deprecated = 0
    for item in parsed.get("deprecations") or []:
        file = str(item.get("file") or "")
        reason = str(item.get("reason") or "").strip()
        if not file or not reason:
            continue
        knowledge.add_draft(
            conn, "deprecation", f"废弃知识包：{file}",
            reason, agent="knowledge_keeper", source="keeper:auto",
            agents=[],
        )
        deprecated += 1
    audit.log(
        conn, "knowledge", "keeper_run",
        detail={"auto_updates": auto, "drafts": drafts, "deprecations": deprecated},
    )
    from novel_pipeline.services import activity  # noqa: PLC0415

    activity.log_activity(
        conn,
        "knowledge_keeper",
        0,
        "knowledge",
        "知识管家维护完成",
        {
            "auto_updates": auto,
            "skipped_to_draft": skipped,
            "draft_suggestions": drafts,
            "deprecations": deprecated,
        },
    )
    return {
        "ok": True,
        "auto_updates": auto,
        "skipped_to_draft": skipped,
        "draft_suggestions": drafts,
        "deprecations": deprecated,
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="知识管家定时维护")
    ap.add_argument("--db", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    path = Path(args.db) if args.db else config.DB_PATH
    conn = db.connect(path)
    try:
        result = run(conn, dry_run=args.dry_run)
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
