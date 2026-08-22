"""SQLAlchemy models: global registry + per-workspace databases."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    """Global registry entry for one work."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200))
    genre: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(
        String(20), default="writing", server_default="writing"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WorkspaceStructureNode(Base):
    """One node in a workspace's optional structure tree (volume/chapter/section)."""

    __tablename__ = "workspace_structure_nodes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    parent_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("workspace_structure_nodes.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="writing")
    draft_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Outline(Base):
    """One version of a workspace's optional outline plan (N13 J2)."""

    __tablename__ = "outlines"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "version", name="uq_outlines_workspace_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentRole:
    EDITOR_IN_CHIEF = "editor_in_chief"
    EDITOR = "editor"
    WRITER = "writer"
    REVIEWER = "reviewer"


#: Personality-parameter fields (N27-C). Values are integers in 0-10 and feed
#: the free-will behavior selector later; they live on the profile (per
#: workspace) and are never overridden by global config.
PERSONALITY_PARAM_FIELDS: tuple[str, ...] = (
    "proactivity",
    "stubbornness",
    "talkativeness",
    "patience",
)

#: Per-role personality-parameter defaults (0-10), justified by the role's
#: DEFAULT_BAND profile text. The Alembic migration backfills existing rows
#: with the same numbers, so model and migration must stay in sync.
#:
#: editor_in_chief: proactivity 6 (稳抓主线、主动牵头), stubbornness 7
#:   (主线问题从不含糊), talkativeness 4 (说话留三分余地), patience 8
#:   (焦虑阈值高，只在主线失控时明显波动).
#: editor: proactivity 8 (每章跟读、追读体验至上), stubbornness 6
#:   (与总编意见常不一致但可商量), talkativeness 7 (批评直率、话多),
#:   patience 3 (对拖稿忍耐度低).
#: writer: proactivity 5 (手感型创作者，靠指令与反馈推进), stubbornness 6
#:   (怕退稿但嘴上从不认输), talkativeness 5 (会带入角色情绪表达),
#:   patience 4 (被退稿会低落但恢复快).
#: reviewer: proactivity 4 (冷静严谨，只盯逻辑与伏笔), stubbornness 8
#:   (发现前后矛盾必退稿、从不放过一个洞), talkativeness 3 (话不多但句句
#:   在点子上), patience 7 (几乎不被情绪影响判断).
ROLE_PERSONALITY_PARAMS: dict[str, tuple[int, int, int, int]] = {
    AgentRole.EDITOR_IN_CHIEF: (6, 7, 4, 8),
    AgentRole.EDITOR: (8, 6, 7, 3),
    AgentRole.WRITER: (5, 6, 5, 4),
    AgentRole.REVIEWER: (4, 8, 3, 7),
}


class Agent(Base):
    """One partner in a workspace's editorial band."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(50))
    personality: Mapped[str] = mapped_column(Text, default="")
    stance: Mapped[str] = mapped_column(Text, default="")
    values: Mapped[str] = mapped_column(Text, default="")
    aesthetic: Mapped[str] = mapped_column(Text, default="")
    emotion_baseline: Mapped[str] = mapped_column(Text, default="")
    mood: Mapped[str] = mapped_column(Text, default="平静")
    work_habits: Mapped[str] = mapped_column(Text, default="")
    weaknesses: Mapped[str] = mapped_column(Text, default="")
    relationship_presets: Mapped[str] = mapped_column(Text, default="")
    private_motive: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    proactivity: Mapped[int] = mapped_column(Integer, nullable=False)
    stubbornness: Mapped[int] = mapped_column(Integer, nullable=False)
    talkativeness: Mapped[int] = mapped_column(Integer, nullable=False)
    patience: Mapped[int] = mapped_column(Integer, nullable=False)

    def __init__(self, **kwargs: object) -> None:
        """Apply per-role personality-parameter defaults on construction.

        Every creation path (create_agent, seed_band, tests) goes through this
        constructor, so role-appropriate values are filled even when the
        caller does not pass them; an unknown role falls back to a neutral 5.
        """
        role = kwargs.get("role")
        if isinstance(role, str) and role in ROLE_PERSONALITY_PARAMS:
            defaults = ROLE_PERSONALITY_PARAMS[role]
        else:
            defaults = (5, 5, 5, 5)
        for field, value in zip(
            PERSONALITY_PARAM_FIELDS, defaults, strict=True
        ):
            kwargs.setdefault(field, value)
        super().__init__(**kwargs)


class AgentMemory(Base):
    """A private note owned by one partner in a workspace."""

    __tablename__ = "agent_memories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    agent_id: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    strength: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


class MotiveKind(StrEnum):
    """Stable motive kinds (N27); the enum value doubles as the stored string."""

    FORESHADOW = "foreshadow"
    CONFLICT = "conflict"
    GOAL = "goal"
    IMPRESSION = "impression"
    PENDING_ISSUE = "pending_issue"


class AgentMotive(Base):
    """One thing a partner is carrying (N27): not a todo, no deadline, no claim.

    A motive only biases future behavior. It has no due date, no assignee and
    no claim/accept semantics; it can be left alone, fade (decay lowers
    strength but never deletes) or be cleared explicitly.
    """

    __tablename__ = "agent_motives"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    agent_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    strength: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    source: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_touched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class PlotThread(Base):
    """A narrative thread (foreshadow / goal / hook) tracked across chapters."""

    __tablename__ = "plot_threads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="planted")
    chapter: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Message(Base):
    """One message in a workspace conversation."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    role: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StyleAnchor(Base):
    """Per-workspace style baseline: description and forbidden words."""

    __tablename__ = "style_anchors"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    forbidden_words: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Draft(Base):
    """A draft in a workspace; versions accumulate under it."""

    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    writer_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default=None
    )
    title: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class DraftVersion(Base):
    """One version of a draft."""

    __tablename__ = "draft_versions"
    __table_args__ = (
        UniqueConstraint("draft_id", "version", name="uq_draft_versions_draft_version"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    draft_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SettingEntry(Base):
    """One versioned world-setting entry in a workspace."""

    __tablename__ = "setting_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="")
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class SettingVersion(Base):
    """One version of a setting entry."""

    __tablename__ = "setting_versions"
    __table_args__ = (
        UniqueConstraint("entry_id", "version", name="uq_setting_versions_entry_version"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    entry_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Inspiration(Base):
    """One lightweight inspiration/material snippet in a workspace (N15)."""

    __tablename__ = "inspirations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(
        String(20), default="灵感", server_default="灵感"
    )
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Review(Base):
    """A review comment on a draft from the author or an agent."""

    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    draft_id: Mapped[str] = mapped_column(String(32), index=True)
    role: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Decision(Base):
    """An author decision (accept / reject / note) on a draft."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    draft_id: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(100), default="作者")
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Event(Base):
    """One visible collaboration event in a workspace."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    type: Mapped[str] = mapped_column(String(50))
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    actor: Mapped[str] = mapped_column(String(100))
    payload: Mapped[str] = mapped_column(Text, default="{}")


class BehaviorTimeline(Base):
    """One append-only record of an impression, relationship, or viewpoint change."""

    __tablename__ = "behavior_timeline"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    agent_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    target: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    before_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MemoryEmbedding(Base):
    """Vector index row for one memory note or setting entry (N7)."""

    __tablename__ = "memory_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "layer", "source_id", name="uq_memory_embeddings_layer_source"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    layer: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[str] = mapped_column(String(32))
    vector: Mapped[str] = mapped_column(Text)
    dim: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
