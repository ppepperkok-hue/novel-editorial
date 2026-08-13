"""Workspace services."""

from __future__ import annotations

from novel_editorial.store.db import DB, seed_default_band
from novel_editorial.store.models import Workspace


def create_workspace(
    db: DB,
    *,
    title: str,
    genre: str = "",
    description: str = "",
) -> Workspace:
    with db.global_session() as session:
        workspace = Workspace(title=title, genre=genre, description=description)
        session.add(workspace)
        session.commit()
        workspace_id = workspace.id
    db.create_workspace_db(workspace_id)
    seed_default_band(db, workspace_id)
    return workspace
