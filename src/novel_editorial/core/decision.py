"""Author decision services: accept / reject / note on drafts.

Decisions are the N28-A feedback source: after the decision transaction
commits, accept resolves the writer's draft goal motive and boosts the
writer's proactivity drift, while reject creates/strengthens the writer's
pending_issue motive and boosts the stubbornness drift. Every write-back runs
through the safe entry points (post-hoc, warning-only on failure) so a motive
or drift failure never rolls the verdict back.
"""

from __future__ import annotations

from novel_editorial.core.behavior import record_behavior_entry_safe
from novel_editorial.core.chat import (
    AUTHOR_ACTOR,
    MOOD_ACCEPTED,
    MOOD_REJECTED,
    _update_agent_mood_in_session,
    apply_drift_safe,
)
from novel_editorial.core.draft import get_draft
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.motives import clear_motives_safe, upsert_motive_feedback_safe
from novel_editorial.core.natural_discussion import check_summon_trigger_safe
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, AgentRole, Decision, Draft, MotiveKind

DRAFT_STATUS = "draft"
ACCEPTED_STATUS = "accepted"
REJECTED_STATUS = "rejected"


def decide(
    db: DB,
    workspace_id: str,
    draft_id: str,
    *,
    action: str,
    content: str = "",
) -> Draft:
    get_draft(db, workspace_id, draft_id)
    writer_id: str | None = None
    reject_target = draft_id
    with db.workspace_session(workspace_id) as session:
        draft = (
            session.query(Draft)
            .filter_by(workspace_id=workspace_id, id=draft_id)
            .first()
        )
        if draft is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"draft not found: {draft_id}")
        if action == "accept":
            if draft.status == ACCEPTED_STATUS:
                raise NovelError(ErrorCode.USAGE_ERROR, "draft is already accepted")
            if draft.status == "quality_failed":
                raise NovelError(
                    ErrorCode.USAGE_ERROR, "cannot accept a draft that failed the quality gate"
                )
            draft.status = ACCEPTED_STATUS
        elif action == "reject":
            if draft.status not in (DRAFT_STATUS, "quality_failed"):
                raise NovelError(
                    ErrorCode.USAGE_ERROR,
                    f"cannot reject a draft in status {draft.status}",
                )
            draft.status = REJECTED_STATUS
        elif action == "note":
            if not content.strip():
                raise NovelError(ErrorCode.USAGE_ERROR, "note requires --content")
        else:
            raise NovelError(ErrorCode.USAGE_ERROR, f"unknown decision action: {action}")
        if action == "reject":
            reject_target = draft.title.strip() or draft_id
        session.add(
            Decision(
                workspace_id=workspace_id,
                draft_id=draft_id,
                action=action,
                content=content,
            )
        )
        if action in ("accept", "reject"):
            writer = (
                session.query(Agent)
                .filter_by(workspace_id=workspace_id, role=AgentRole.WRITER)
                .first()
            )
            if writer is None:
                raise NovelError(
                    ErrorCode.NOT_FOUND,
                    f"agent not found in workspace: {AgentRole.WRITER}",
                )
            mood = MOOD_ACCEPTED if action == "accept" else MOOD_REJECTED
            _update_agent_mood_in_session(session, workspace_id, writer.id, mood)
            writer_id = writer.id
        session.commit()
    if writer_id is not None:
        accepted = action == "accept"
        record_behavior_entry_safe(
            db,
            workspace_id,
            agent_id=writer_id,
            kind="relationship",
            target=AUTHOR_ACTOR,
            summary="稿子被认可" if accepted else "稿子被退回",
            source=f"decision:{action}",
        )
        record_behavior_entry_safe(
            db,
            workspace_id,
            agent_id=writer_id,
            kind="impression",
            target=AUTHOR_ACTOR,
            summary="认可我的产出" if accepted else "对我的要求高",
            source=f"decision:{action}",
        )
        # N28-A feedback write-backs (post-hoc, safe-degraded): acceptance
        # resolves the draft goal and the writer is energized; rejection
        # leaves a pending issue and makes the writer hold their ground.
        if accepted:
            clear_motives_safe(
                db,
                workspace_id,
                agent_id=writer_id,
                kind=MotiveKind.GOAL.value,
                source_prefix="event:draft_",
            )
            apply_drift_safe(
                db,
                workspace_id,
                writer_id,
                "proactivity",
                1,
                event="decision:accept",
            )
        else:
            upsert_motive_feedback_safe(
                db,
                workspace_id,
                writer_id,
                kind=MotiveKind.PENDING_ISSUE.value,
                content="被退稿了，这事还惦记着",
                source="decision:reject",
            )
            apply_drift_safe(
                db,
                workspace_id,
                writer_id,
                "stubbornness",
                1,
                event="decision:reject",
            )
            # N29 trigger check (S3 实际召集): after the reject accumulates,
            # summon the natural discussion once when the writer is a
            # candidate (pool == 0, not cooling). Safe-degraded: a failure
            # only warns and never rolls the verdict.
            check_summon_trigger_safe(
                db,
                workspace_id,
                agent_id=writer_id,
                target=reject_target,
            )
    return draft
