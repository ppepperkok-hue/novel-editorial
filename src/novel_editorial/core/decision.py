"""Author decision services: accept / reject / note on drafts."""

from __future__ import annotations

from novel_editorial.core.behavior import record_behavior_entry_safe
from novel_editorial.core.chat import (
    AUTHOR_ACTOR,
    MOOD_ACCEPTED,
    MOOD_REJECTED,
    _update_agent_mood_in_session,
)
from novel_editorial.core.draft import get_draft
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, AgentRole, Decision, Draft

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
    return draft
