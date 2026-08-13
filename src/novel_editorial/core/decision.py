"""Author decision services: accept / reject / note on drafts."""

from __future__ import annotations

from novel_editorial.core.chat import (
    MOOD_ACCEPTED,
    MOOD_REJECTED,
    get_agent,
    update_agent_mood,
)
from novel_editorial.core.draft import get_draft
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import AgentRole, Decision, Draft

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
        session.commit()
    if action == "accept":
        writer = get_agent(db, workspace_id, AgentRole.WRITER)
        update_agent_mood(db, workspace_id, writer, MOOD_ACCEPTED)
    elif action == "reject":
        writer = get_agent(db, workspace_id, AgentRole.WRITER)
        update_agent_mood(db, workspace_id, writer, MOOD_REJECTED)
    return draft
