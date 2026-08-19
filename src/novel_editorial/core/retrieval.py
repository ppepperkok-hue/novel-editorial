"""Semantic memory retrieval: vector index sync and semantic search (N7 I1/I2)."""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

from novel_editorial.core.config import load_settings
from novel_editorial.llm.embeddings import build_embedding_client
from novel_editorial.store.db import DB
from novel_editorial.store.models import (
    Agent,
    AgentMemory,
    MemoryEmbedding,
    SettingEntry,
)

LAYER_NOTE = "note"
LAYER_SETTING = "setting"

SNIPPET_WIDTH = 40


@dataclass
class SemanticHit:
    """One semantic match against a memory note or setting entry."""

    layer: str
    source_id: str
    score: float
    content: str
    detail: str
    name: str = ""
    label: str = ""


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _setting_label(kind: str) -> str:
    """Map a setting kind to its Chinese label without a top-level import cycle."""
    from novel_editorial.core.setting import KIND_LABELS

    return KIND_LABELS.get(kind, kind)


def _cosine(left: list[float], right: list[float]) -> float:
    """Cosine similarity with zero-vector guards for non-normalized API vectors."""
    dot = sum(x * y for x, y in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(x * x for x in left))
    right_norm = math.sqrt(sum(y * y for y in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _fold_snippet(content: str, keyword: str) -> str:
    """Trim collapsed content around the keyword, mirroring views._snippet."""
    collapsed = " ".join(content.split())
    index = collapsed.lower().find(keyword.lower())
    if index < 0:
        index = 0
    start = max(0, index - SNIPPET_WIDTH)
    end = min(len(collapsed), index + len(keyword) + SNIPPET_WIDTH)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(collapsed) else ""
    return f"{prefix}{collapsed[start:end]}{suffix}"


def upsert_embedding(
    db: DB,
    workspace_id: str,
    *,
    layer: str,
    source_id: str,
    text: str,
) -> MemoryEmbedding:
    """Embed ``text`` and write or refresh the index row for (layer, source_id)."""
    vector = build_embedding_client(load_settings()).embed(text)
    serialized = json.dumps(vector)
    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(MemoryEmbedding)
            .filter_by(layer=layer, source_id=source_id)
            .first()
        )
        if row is None:
            row = MemoryEmbedding(
                workspace_id=workspace_id,
                layer=layer,
                source_id=source_id,
                vector=serialized,
                dim=len(vector),
            )
            session.add(row)
        else:
            row.vector = serialized
            row.dim = len(vector)
            row.updated_at = _now_utc()
        session.commit()
        return row


def delete_embedding(
    db: DB,
    workspace_id: str,
    *,
    layer: str,
    source_id: str,
) -> bool:
    """Delete the index row for (layer, source_id); a missing row is a no-op."""
    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(MemoryEmbedding)
            .filter_by(layer=layer, source_id=source_id)
            .first()
        )
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def upsert_embedding_safe(
    db: DB,
    workspace_id: str,
    *,
    layer: str,
    source_id: str,
    text: str,
) -> bool:
    """Upsert an embedding, degrading to a stderr warning on failure.

    The vector index is derived sediment: a sync failure must never roll the
    business write back, so every exception is caught and reported.
    """
    try:
        upsert_embedding(
            db,
            workspace_id,
            layer=layer,
            source_id=source_id,
            text=text,
        )
    except Exception as exc:
        print(f"warning: embedding index skipped: {exc}", file=sys.stderr)
        return False
    return True


def delete_embedding_safe(
    db: DB,
    workspace_id: str,
    *,
    layer: str,
    source_id: str,
) -> bool:
    """Delete an embedding, degrading to a stderr warning on failure."""
    try:
        delete_embedding(
            db,
            workspace_id,
            layer=layer,
            source_id=source_id,
        )
    except Exception as exc:
        print(f"warning: embedding index delete skipped: {exc}", file=sys.stderr)
        return False
    return True


def semantic_search(
    db: DB,
    workspace_id: str,
    query: str,
    top_k: int | None = None,
) -> list[SemanticHit]:
    """Return the top semantic matches for ``query`` inside one workspace.

    Rows are scored with cosine similarity against the query embedding and
    read back from the live note/setting tables, so archived notes and deleted
    sources are skipped. An empty index degrades silently; an embedding
    failure warns on stderr and degrades to an empty result (fail-closed).
    """
    settings = load_settings()
    if top_k is None:
        top_k = settings.embedding_top_k
    with db.workspace_session(workspace_id) as session:
        rows = (
            session.query(MemoryEmbedding)
            .filter_by(workspace_id=workspace_id)
            .order_by(MemoryEmbedding.id)
            .all()
        )
        if not rows:
            return []
    try:
        query_vector = build_embedding_client(settings).embed(query)
    except Exception as exc:
        print(f"warning: semantic search skipped: {exc}", file=sys.stderr)
        return []

    scored: list[tuple[float, MemoryEmbedding]] = []
    for row in rows:
        try:
            vector = json.loads(row.vector)
        except (TypeError, ValueError):
            continue
        if not isinstance(vector, list):
            continue
        try:
            values = [float(value) for value in vector]
        except (TypeError, ValueError):
            continue
        if row.dim is not None and len(values) != row.dim:
            continue
        if len(values) != len(query_vector):
            continue
        scored.append((_cosine(query_vector, values), row))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = scored[:top_k]

    note_ids = [row.source_id for _, row in top if row.layer == LAYER_NOTE]
    setting_ids = [row.source_id for _, row in top if row.layer == LAYER_SETTING]
    hits: list[SemanticHit] = []
    with db.workspace_session(workspace_id) as session:
        notes: dict[str, AgentMemory] = {}
        if note_ids:
            notes = {
                note.id: note
                for note in session.query(AgentMemory)
                .filter(
                    AgentMemory.workspace_id == workspace_id,
                    AgentMemory.id.in_(note_ids),
                )
                .all()
            }
        entries: dict[str, SettingEntry] = {}
        if setting_ids:
            entries = {
                entry.id: entry
                for entry in session.query(SettingEntry)
                .filter(
                    SettingEntry.workspace_id == workspace_id,
                    SettingEntry.id.in_(setting_ids),
                )
                .all()
            }
        agent_ids = {note.agent_id for note in notes.values()}
        agents: dict[str, Agent] = {}
        if agent_ids:
            agents = {
                agent.id: agent
                for agent in session.query(Agent)
                .filter(
                    Agent.workspace_id == workspace_id,
                    Agent.id.in_(agent_ids),
                )
                .all()
            }
        for score, row in top:
            if row.layer == LAYER_NOTE:
                note = notes.get(row.source_id)
                if note is None or note.archived_at is not None:
                    continue
                owner = agents.get(note.agent_id)
                detail = owner.name if owner is not None else note.agent_id
                hits.append(
                    SemanticHit(
                        layer=LAYER_NOTE,
                        source_id=note.id,
                        score=score,
                        content=note.content,
                        detail=detail,
                    )
                )
            elif row.layer == LAYER_SETTING:
                entry = entries.get(row.source_id)
                if entry is None:
                    continue
                hits.append(
                    SemanticHit(
                        layer=LAYER_SETTING,
                        source_id=entry.id,
                        score=score,
                        content=entry.content,
                        detail=f"{entry.source} v{entry.current_version}",
                        name=entry.name,
                        label=_setting_label(entry.kind),
                    )
                )
    return hits


def reindex_embeddings(db: DB, workspace_id: str) -> int:
    """Rebuild every note/setting embedding row in one workspace.

    Covers all notes including archived ones (archived vectors are kept for
    history and excluded at query time, matching the archived-note query), so
    the result is idempotent. Per-row failures warn and continue; the return
    value is the number of successfully upserted rows.
    """
    with db.workspace_session(workspace_id) as session:
        sources = [
            (LAYER_NOTE, note.id, note.content)
            for note in session.query(AgentMemory)
            .filter_by(workspace_id=workspace_id)
            .order_by(AgentMemory.id)
            .all()
        ]
        sources += [
            (LAYER_SETTING, entry.id, entry.content)
            for entry in session.query(SettingEntry)
            .filter_by(workspace_id=workspace_id)
            .order_by(SettingEntry.id)
            .all()
        ]
    succeeded = 0
    for layer, source_id, content in sources:
        if upsert_embedding_safe(
            db,
            workspace_id,
            layer=layer,
            source_id=source_id,
            text=content,
        ):
            succeeded += 1
    return succeeded


def render_semantic_hit(hit: SemanticHit, keyword: str) -> str:
    """Render one semantic hit in the established [layer] citation style."""
    snippet = _fold_snippet(hit.content, keyword)
    suffix = f"[语义 {hit.score:.2f}]"
    if hit.layer == LAYER_NOTE:
        return f"[笔记] {snippet}（来源: {hit.detail}）{suffix}"
    if hit.layer == LAYER_SETTING:
        return (
            f"[设定] {hit.label}：{hit.name}——{snippet}"
            f"（来源: {hit.detail}）{suffix}"
        )
    return f"[{hit.layer}] {snippet}（来源: {hit.detail}）{suffix}"
