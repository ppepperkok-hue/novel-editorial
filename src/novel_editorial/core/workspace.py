"""Workspace services."""

from __future__ import annotations

from novel_editorial.core.style import set_style_anchor
from novel_editorial.core.templates import BandTemplate
from novel_editorial.store.db import DB, seed_band, seed_default_band
from novel_editorial.store.models import Workspace


def create_workspace(
    db: DB,
    *,
    title: str,
    genre: str = "",
    description: str = "",
    template: BandTemplate | None = None,
) -> Workspace:
    with db.global_session() as session:
        workspace = Workspace(title=title, genre=genre, description=description)
        session.add(workspace)
        session.commit()
        workspace_id = workspace.id
    db.create_workspace_db(workspace_id)
    if template is None:
        seed_default_band(db, workspace_id)
    else:
        seed_band(db, workspace_id, template.band)
        if template.style_description:
            set_style_anchor(
                db,
                workspace_id,
                description=template.style_description,
                forbidden_words="",
            )
    return workspace
