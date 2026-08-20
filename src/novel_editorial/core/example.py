"""Example editorial-office seeding (N11 R1).

One call to :func:`seed_example_workspace` builds a deterministic, fully
populated sample workspace -- style anchor, settings, outline, structure,
conversation, a pending draft, plot threads, memory notes, behavior traces and
the matching event stream -- without mutating any existing workspace or
configuration. Under the default configuration
(``NOVEL_EMBEDDING_BACKEND=local``) no LLM or embedding API is ever called;
when the user explicitly configures the ``api`` embedding backend, setting and
memory writes follow the existing retrieval-freshness semantics and call the
embedding API (real calls with a key, degraded stderr warnings without one).
Every run creates a brand-new workspace; sample text lives in module constants
(mirroring ``DEFAULT_BAND``) and no resource files are added.

The example quality gate uses the fixed internal threshold
:data:`EXAMPLE_QUALITY_THRESHOLD` so the pending-draft demo stays stable
under any user configuration; callers may still override it explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass

from novel_editorial.core.behavior import (
    list_behavior_timeline,
    record_behavior_entry,
)
from novel_editorial.core.chat import (
    AUTHOR_ACTOR,
    PROACTIVE_PAYLOAD,
    PROACTIVE_QUESTION,
    get_agent,
    list_messages,
    record_message,
)
from novel_editorial.core.draft import list_drafts
from novel_editorial.core.memory import add_memory_note, list_memory_notes
from novel_editorial.core.outline import create_outline, list_outline_versions
from novel_editorial.core.plot import list_threads, plant_thread
from novel_editorial.core.setting import add_setting, list_settings
from novel_editorial.core.structure import (
    KIND_CHAPTER,
    KIND_VOLUME,
    STATUS_COMPLETED,
    create_node,
    list_structure,
    set_node_status,
)
from novel_editorial.core.style import (
    extract_style_keywords,
    set_style_anchor,
)
from novel_editorial.core.workspace import create_workspace
from novel_editorial.events import EventType
from novel_editorial.quality.gate import check_quality
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events, record_event
from novel_editorial.store.models import (
    AgentRole,
    Draft,
    DraftVersion,
)

EXAMPLE_TITLE = "示例·雨夜车站"
EXAMPLE_GENRE = "悬疑"
EXAMPLE_QUALITY_THRESHOLD = 8
EXAMPLE_DESCRIPTION = (
    "雨夜，末班车驶入旧车站。侦探沈夜回乡，发现十年前失踪的列车重新到站。"
)

STYLE_DESCRIPTION = "平实克制短句"
STYLE_FORBIDDEN_WORDS = "璀璨、宛如"

EXAMPLE_SETTINGS: tuple[dict[str, str], ...] = (
    {
        "kind": "character",
        "name": "沈夜",
        "content": "雨夜归乡的侦探，十年前离开旧车站，随身带着一只旧皮箱。",
    },
    {
        "kind": "timeline",
        "name": "旧车站",
        "content": "末班车每晚十一点进站；十年前雨夜有一趟车失踪，至今无人找到。",
    },
    {
        "kind": "world",
        "name": "钟楼",
        "content": "小镇钟楼自十年前停摆，指针停在十一点，居民习惯不去提起。",
    },
)

OUTLINE_CONTENT = (
    "第一章 雨夜：沈夜乘末班车回到旧车站，发现十年前失踪的列车重现。"
    "第二章 线索：他在值班室找到半张旧车票，票面日期正是十年前失踪那晚。"
    "第三章 钟楼：钟楼指针停在十一点，与列车到站时间重合，旧案有了新解释。"
)

VOLUME_TITLE = "第一卷 旧车站"
CHAPTER_TITLES: tuple[str, ...] = ("第一章 雨夜", "第二章 线索", "第三章 钟楼")

AUTHOR_OPENING = (
    "我们写一个雨夜故事：侦探沈夜在雨夜回到故乡，"
    "发现十年前失踪的列车重新到站。"
)
EDITOR_IN_CHIEF_REPLY = (
    "主线清晰，故事成立。悬疑的锚点在钟楼与列车失踪的重合，"
    "先按这个方向走，第一章我盯着车站的雨夜氛围。"
)

EXAMPLE_THREADS: tuple[dict[str, str], ...] = (
    {
        "kind": "foreshadow",
        "content": "黑伞人始终背对站台，没露出脸，伞面缝着旧车站的站徽。",
        "chapter": "第一章 雨夜",
    },
    {
        "kind": "foreshadow",
        "content": "值班室的旧车票只剩半张，票号与十一年前那趟车一致。",
        "chapter": "第二章 线索",
    },
)

EXAMPLE_NOTES: tuple[str, ...] = (
    "沈夜的旧皮箱里有一张没寄出的信，是十年前离开时留下的——这条线留到第三章再收。",
    "车站的钟声只在列车进站那一刻响，这个细节要守住，不能写错。",
)

DRAFT_TITLE = "第一章 雨夜"
DRAFT_CONTENT = (
    "雨下了一整夜。车站的灯忽明忽暗，末班车进站时，钟声停了。\n\n"
    "沈夜提着旧皮箱走下月台。候车室里只有一个人，撑黑伞，背对着他。\n\n"
    "十年前，这趟车在雨夜失踪。十年后，它又准时到站。\n\n"
    "他数过台阶，一共十三级，每一级都是湿的。\n\n"
    "墙上挂着一面钟。指针停在十一点，钟摆不动。\n\n"
    "检票口没有人。闸机还开着，像在等他。"
)

@dataclass(frozen=True)
class ExampleResult:
    """One seeded example workspace and its preloaded layer counts."""

    workspace_id: str
    title: str
    genre: str
    settings: int
    outline: int
    structure_nodes: int
    messages: int
    drafts: int
    threads: int
    notes: int
    behavior_entries: int
    events: int


def seed_example_workspace(
    db: DB,
    *,
    quality_threshold: int | None = None,
) -> ExampleResult:
    """Create the 《示例·雨夜车站》 workspace with every editorial layer.

    The function is deterministic (fixed text) and idempotent at the workspace
    level (each run creates a new workspace id) and never touches existing
    workspaces or configuration. Under the default local embedding backend no
    LLM or embedding API is called; an explicit ``api`` embedding backend
    triggers the existing upsert-embedding calls from setting and memory
    writes. ``quality_threshold`` defaults to
    ``EXAMPLE_QUALITY_THRESHOLD`` so the demo stays draft + pending decision
    under any user configuration; pass an explicit value to override (the
    draft status and the quality-gate events still follow
    :func:`generate_draft` semantics: the two gate events are only recorded
    when the gate passes).
    """
    workspace = create_workspace(
        db,
        title=EXAMPLE_TITLE,
        genre=EXAMPLE_GENRE,
        description=EXAMPLE_DESCRIPTION,
    )
    workspace_id = workspace.id

    set_style_anchor(
        db,
        workspace_id,
        description=STYLE_DESCRIPTION,
        forbidden_words=STYLE_FORBIDDEN_WORDS,
    )
    for entry in EXAMPLE_SETTINGS:
        add_setting(
            db,
            workspace_id,
            kind=entry["kind"],
            name=entry["name"],
            content=entry["content"],
        )
    create_outline(
        db,
        workspace_id,
        content=OUTLINE_CONTENT,
        actor="总编",
        reason="initial",
    )

    volume = create_node(
        db,
        workspace_id,
        kind=KIND_VOLUME,
        title=VOLUME_TITLE,
    )
    chapter_nodes = [
        create_node(
            db,
            workspace_id,
            kind=KIND_CHAPTER,
            title=title,
            parent_id=volume.id,
        )
        for title in CHAPTER_TITLES
    ]
    set_node_status(db, workspace_id, chapter_nodes[0].id, STATUS_COMPLETED)

    editor_in_chief = get_agent(db, workspace_id, AgentRole.EDITOR_IN_CHIEF)
    editor = get_agent(db, workspace_id, AgentRole.EDITOR)
    writer = get_agent(db, workspace_id, AgentRole.WRITER)
    record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content=AUTHOR_OPENING,
    )
    record_message(
        db,
        workspace_id,
        role="agent",
        actor=editor_in_chief.name,
        content=EDITOR_IN_CHIEF_REPLY,
    )
    record_message(
        db,
        workspace_id,
        role="agent",
        actor=editor.name,
        content=PROACTIVE_QUESTION,
        payload=PROACTIVE_PAYLOAD,
    )

    for thread in EXAMPLE_THREADS:
        plant_thread(
            db,
            workspace_id,
            kind=thread["kind"],
            content=thread["content"],
            chapter=thread["chapter"],
        )
    for note in EXAMPLE_NOTES:
        add_memory_note(db, workspace_id, writer.id, actor="写手", content=note)

    record_behavior_entry(
        db,
        workspace_id,
        agent_id=editor.id,
        kind="impression",
        target="沈夜",
        summary="开场人物的第一印象：克制、寡言，动作比台词多。",
        source="试读第一章",
    )
    record_behavior_entry(
        db,
        workspace_id,
        agent_id=writer.id,
        kind="viewpoint",
        target=DRAFT_TITLE,
        summary="雨夜车站的冷感是这章的底色，节奏用短句推。",
        source="写作笔记",
    )

    threshold = (
        quality_threshold
        if quality_threshold is not None
        else EXAMPLE_QUALITY_THRESHOLD
    )
    quality_report = check_quality(
        DRAFT_CONTENT,
        threshold=threshold,
        style_keywords=extract_style_keywords(STYLE_DESCRIPTION),
    )
    draft_status = "draft" if quality_report.passed else "quality_failed"

    with db.workspace_session(workspace_id) as session:
        draft = Draft(
            workspace_id=workspace_id,
            title=DRAFT_TITLE,
            writer_id=writer.id,
            status=draft_status,
            current_version=1,
        )
        session.add(draft)
        session.flush()
        session.add(
            DraftVersion(
                draft_id=draft.id,
                version=1,
                content=DRAFT_CONTENT,
                reason="initial",
            )
        )
        session.commit()
        draft_id = draft.id

    record_event(
        db,
        workspace_id,
        type=EventType.DRAFT_CREATED,
        actor=writer.name,
        payload={"draft_id": draft_id, "title": DRAFT_TITLE},
    )
    if quality_report.passed:
        record_event(
            db,
            workspace_id,
            type=EventType.QUALITY_GATE_PASSED,
            actor="system",
            payload={
                "draft_id": draft_id,
                "version": 1,
                "score": quality_report.score,
            },
        )
        record_event(
            db,
            workspace_id,
            type=EventType.DECISION_REQUESTED,
            actor="system",
            payload={"draft_id": draft_id, "version": 1},
        )

    return ExampleResult(
        workspace_id=workspace_id,
        title=workspace.title,
        genre=workspace.genre,
        settings=len(list_settings(db, workspace_id)),
        outline=len(list_outline_versions(db, workspace_id)),
        structure_nodes=len(list_structure(db, workspace_id)),
        messages=len(list_messages(db, workspace_id)),
        drafts=len(list_drafts(db, workspace_id)),
        threads=len(list_threads(db, workspace_id)),
        notes=len(list_memory_notes(db, workspace_id)),
        behavior_entries=len(list_behavior_timeline(db, workspace_id, limit=1000)),
        events=len(list_events(db, workspace_id, limit=1000)),
    )
