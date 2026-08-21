"""SQLAlchemy models: global registry + per-workspace databases."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

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
