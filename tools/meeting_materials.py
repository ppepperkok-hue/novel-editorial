"""R4-2: meeting materials assembled per kind.

Weekly and planning reuse the battle-tested architects; other kinds build on
the book context and attach only the blocks their registry declares
(failures for incident, drafts for learning, finish metrics for review,
topic pool for free meetings, latest chapter for critique).
"""

from __future__ import annotations

from tools import architect_weekly, meeting_kinds


def build_materials(conn, novel_id, kind="topic", topic=""):
    spec = meeting_kinds.MEETING_KINDS.get(
        kind, meeting_kinds.MEETING_KINDS["topic"]
    )
    keys = spec["materials_keys"]
    if "planning" in keys:
        materials = architect_weekly.build_planning_materials(conn)
    else:
        materials = architect_weekly.build_materials(
            conn, novel_id, allow_empty=(novel_id == 0)
        )
    if materials is None:
        return None
    ctx = materials["context"]
    if "failures" in keys:
        ctx["failure_runs"] = [
            dict(r)
            for r in conn.execute(
                "SELECT run_id, status, error, started_at FROM daily_runs "
                "WHERE status IN ('failed','partial') "
                "ORDER BY id DESC LIMIT 5"
            ).fetchall()
        ]
    if "drafts" in keys:
        ctx["knowledge_drafts"] = [
            dict(r)
            for r in conn.execute(
                "SELECT id, title, content, status FROM knowledge_drafts "
                "ORDER BY id DESC LIMIT 10"
            ).fetchall()
        ]
    if "finish" in keys:
        ctx["finish_metrics"] = {
            "published": ctx.get("published_chapters", 0),
            "target": ctx.get("target_chapters", 0),
            "open_plot_threads": len(ctx.get("open_plot_threads") or []),
            "last_chapter_seq": ctx.get("last_chapter_seq", 0),
        }
    if "topic_pool" in keys:
        scope = "AND ref_novel_id=?" if novel_id else ""
        params = (int(novel_id),) if novel_id else ()
        ctx["topic_pool"] = [
            dict(r)
            for r in conn.execute(
                "SELECT from_agent, subject, body FROM agent_messages "
                "WHERE kind='topic_request' AND status!='archived' "
                + scope
                + " ORDER BY id DESC LIMIT 8",
                params,
            ).fetchall()
        ]
    if "chapter" in keys:
        row = conn.execute(
            "SELECT id, seq, title, status FROM chapters "
            "WHERE novel_id=? ORDER BY seq DESC LIMIT 1",
            (novel_id,),
        ).fetchone()
        ctx["latest_chapter"] = dict(row) if row else None
    return materials
