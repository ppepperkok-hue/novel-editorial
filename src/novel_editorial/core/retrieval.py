"""Semantic memory retrieval: vector index sync for memory notes and settings (N7 I1)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from novel_editorial.core.config import load_settings
from novel_editorial.llm.embeddings import build_embedding_client
from novel_editorial.store.db import DB
from novel_editorial.store.models import MemoryEmbedding

LAYER_NOTE = "note"
LAYER_SETTING = "setting"


def _now_utc() -> datetime:
    return datetime.now(UTC)


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
