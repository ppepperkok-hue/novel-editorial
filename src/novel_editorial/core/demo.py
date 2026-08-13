"""End-to-end demo: one command runs the full M1 loop with a mock LLM."""

from __future__ import annotations

from novel_editorial.core.chat import (
    AUTHOR_ACTOR,
    PROACTIVE_PAYLOAD,
    PROACTIVE_QUESTION,
    build_agent_prompt,
    get_agent,
    list_messages,
    record_message,
    resolve_target_role,
)
from novel_editorial.core.config import Settings
from novel_editorial.core.decision import decide
from novel_editorial.core.draft import generate_draft, get_draft_version
from novel_editorial.core.workspace import create_workspace
from novel_editorial.llm.client import LLMMessage, build_client
from novel_editorial.quality.gate import check_quality
from novel_editorial.store.db import DB
from novel_editorial.store.models import AgentRole


def run_demo(settings: Settings) -> dict:
    """Run a deterministic demo: workspace -> talk (with proactive) -> draft -> gate -> accept."""
    db = DB(settings)
    db.init_schema()
    workspace = create_workspace(db, title="演示之书", genre="演示")
    workspace_id = workspace.id
    client = build_client(settings)

    author_message = "我们写一个雨夜故事：侦探在雨夜回到故乡，发现旧案重演。"
    target_role = resolve_target_role(author_message)
    agent = get_agent(db, workspace_id, target_role)
    history = list_messages(db, workspace_id)
    prompt = build_agent_prompt(workspace, agent, history, latest_message=author_message)
    reply = client.complete([LLMMessage(role="user", content=prompt)]).content
    record_message(db, workspace_id, role="author", actor=AUTHOR_ACTOR, content=author_message)
    record_message(db, workspace_id, role="agent", actor=agent.name, content=reply)

    editor = get_agent(db, workspace_id, AgentRole.EDITOR)
    record_message(
        db,
        workspace_id,
        role="agent",
        actor=editor.name,
        content=PROACTIVE_QUESTION,
        payload=PROACTIVE_PAYLOAD,
    )

    draft = generate_draft(
        db,
        workspace_id,
        title="第一章 雨夜",
        client=client,
        quality_threshold=settings.quality_threshold,
    )
    version = get_draft_version(db, workspace_id, draft.id, draft.current_version)
    report = check_quality(version.content, threshold=settings.quality_threshold)
    decide(db, workspace_id, draft.id, action="accept")
    return {
        "workspace_id": workspace_id,
        "draft_id": draft.id,
        "quality": report,
    }
