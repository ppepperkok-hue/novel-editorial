"""Draft and memory-pack services."""

from __future__ import annotations

from difflib import unified_diff

from novel_editorial.core.chat import get_agent, get_workspace_or_raise, record_message
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.review import list_reviews
from novel_editorial.core.style import get_style_anchor
from novel_editorial.llm.client import LLMClient, LLMMessage
from novel_editorial.store.db import DB, list_workspace_ids
from novel_editorial.store.models import Agent, AgentRole, Draft, DraftVersion


def build_memory_pack(db: DB, workspace_id: str) -> str:
    workspace = get_workspace_or_raise(db, workspace_id)
    anchor = get_style_anchor(db, workspace_id)
    lines = [
        f"作品：《{workspace.title}》（{workspace.genre}）",
        f"简介：{workspace.description}",
    ]
    if anchor.description:
        lines.append(f"风格说明：{anchor.description}")
    if anchor.forbidden_words:
        lines.append(f"禁忌词：{anchor.forbidden_words}")
    lines.append("章纲：暂无（占位）")
    return "\n".join(lines)


def _build_writer_prompt(
    workspace,
    writer: Agent,
    memory_pack: str,
    title: str,
    *,
    previous_content: str | None = None,
    reviews: list | None = None,
    revision_reason: str | None = None,
) -> str:
    lines = [
        f"你是作品《{workspace.title}》的{writer.name}。\n"
        f"你的性格：{writer.personality}\n"
        f"你的立场：{writer.stance}\n"
        f"写作记忆包：\n{memory_pack}\n"
        f"请为章节《{title}》产出正文，符合上述风格，不要出现禁忌词。"
    ]
    if previous_content:
        lines.append(f"\n上一版正文：\n{previous_content}")
    if reviews:
        review_lines = "\n".join(f"- {r.actor}：{r.content}" for r in reviews)
        lines.append(f"\n收到的意见：\n{review_lines}")
    if revision_reason:
        lines.append(f"\n修订要求：{revision_reason}")
    if previous_content or reviews:
        lines.append("\n请针对上述意见修订正文，不要从头重写。")
    return "\n".join(lines)


def generate_draft(
    db: DB,
    workspace_id: str,
    *,
    title: str,
    client: LLMClient,
) -> Draft:
    workspace = get_workspace_or_raise(db, workspace_id)
    writer = get_agent(db, workspace_id, AgentRole.WRITER)
    memory_pack = build_memory_pack(db, workspace_id)
    prompt = _build_writer_prompt(workspace, writer, memory_pack, title)
    content = client.complete([LLMMessage(role="user", content=prompt)]).content
    if not content.strip():
        raise NovelError(ErrorCode.LLM_ERROR, "LLM returned empty draft content")
    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).filter_by(workspace_id=workspace_id, title=title).first()
        if draft is None:
            draft = Draft(workspace_id=workspace_id, title=title)
            session.add(draft)
            session.flush()
        draft.current_version += 1
        reason = "initial" if draft.current_version == 1 else "revision"
        session.add(
            DraftVersion(
                draft_id=draft.id,
                version=draft.current_version,
                content=content,
                reason=reason,
            )
        )
        session.commit()
        return draft


def revise_draft(
    db: DB,
    workspace_id: str,
    draft_id: str,
    *,
    reason: str,
    client: LLMClient,
) -> Draft:
    current = get_draft(db, workspace_id, draft_id)
    if current.status == "accepted":
        raise NovelError(ErrorCode.USAGE_ERROR, "cannot revise an accepted draft")
    workspace = get_workspace_or_raise(db, workspace_id)
    writer = get_agent(db, workspace_id, AgentRole.WRITER)
    memory_pack = build_memory_pack(db, workspace_id)
    previous = get_draft_version(db, workspace_id, draft_id, current.current_version)
    reviews = list_reviews(db, workspace_id, draft_id)
    prompt = _build_writer_prompt(
        workspace,
        writer,
        memory_pack,
        current.title,
        previous_content=previous.content,
        reviews=reviews,
        revision_reason=reason,
    )
    content = client.complete([LLMMessage(role="user", content=prompt)]).content
    if not content.strip():
        raise NovelError(ErrorCode.LLM_ERROR, "LLM returned empty draft content")
    with db.workspace_session(workspace_id) as session:
        draft = (
            session.query(Draft)
            .filter_by(workspace_id=workspace_id, id=draft_id)
            .first()
        )
        if draft is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"draft not found: {draft_id}")
        draft.current_version += 1
        draft.status = "draft"
        session.add(
            DraftVersion(
                draft_id=draft.id,
                version=draft.current_version,
                content=content,
                reason=reason or "revision",
            )
        )
        session.commit()
    if any(r.role == "agent" for r in reviews):
        record_message(
            db,
            workspace_id,
            role="agent",
            actor=writer.name,
            content=(
                f"写手反驳：我看了意见后重新修订了正文。修订理由：{reason or 'revision'}。"
                "这版针对反馈做了调整，请再审。"
            ),
            payload={"initiator": "agent", "kind": "rebuttal"},
        )
    return draft


def list_drafts(db: DB, workspace_id: str) -> list[Draft]:
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(Draft)
            .filter_by(workspace_id=workspace_id)
            .order_by(Draft.updated_at.desc())
            .all()
        )


def get_draft(db: DB, workspace_id: str, draft_id: str) -> Draft:
    with db.workspace_session(workspace_id) as session:
        draft = (
            session.query(Draft)
            .filter_by(workspace_id=workspace_id, id=draft_id)
            .first()
        )
    if draft is None:
        raise NovelError(ErrorCode.NOT_FOUND, f"draft not found: {draft_id}")
    return draft


def get_draft_version(db: DB, workspace_id: str, draft_id: str, version: int) -> DraftVersion:
    with db.workspace_session(workspace_id) as session:
        draft_version = (
            session.query(DraftVersion)
            .filter_by(draft_id=draft_id, version=version)
            .first()
        )
    if draft_version is None:
        raise NovelError(ErrorCode.NOT_FOUND, f"draft version not found: {draft_id} v{version}")
    return draft_version


def diff_versions(first: DraftVersion, second: DraftVersion) -> str:
    lines = list(
        unified_diff(
            first.content.splitlines(),
            second.content.splitlines(),
            fromfile=f"v{first.version}",
            tofile=f"v{second.version}",
            lineterm="",
        )
    )
    return "\n".join(lines)


def find_draft_anywhere(db: DB, draft_id: str) -> Draft:
    """Locate a draft across workspace databases by id."""
    for workspace_id in list_workspace_ids(db.settings):
        with db.workspace_session(workspace_id) as session:
            draft = session.query(Draft).filter_by(id=draft_id).first()
            if draft is not None:
                return draft
    raise NovelError(ErrorCode.NOT_FOUND, f"draft not found: {draft_id}")
