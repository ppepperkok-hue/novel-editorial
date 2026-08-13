"""Style anchor services."""

from __future__ import annotations

from novel_editorial.store.db import DB
from novel_editorial.store.models import StyleAnchor


def get_style_anchor(db: DB, workspace_id: str) -> StyleAnchor:
    with db.workspace_session(workspace_id) as session:
        anchor = session.query(StyleAnchor).filter_by(workspace_id=workspace_id).first()
        if anchor is None:
            anchor = StyleAnchor(workspace_id=workspace_id)
            session.add(anchor)
            session.commit()
        # Load attributes while the session is open, then detach safely.
        _ = (anchor.description, anchor.forbidden_words)
        session.expunge(anchor)
    return anchor


def set_style_anchor(
    db: DB,
    workspace_id: str,
    *,
    description: str,
    forbidden_words: str,
) -> StyleAnchor:
    with db.workspace_session(workspace_id) as session:
        anchor = session.query(StyleAnchor).filter_by(workspace_id=workspace_id).first()
        if anchor is None:
            anchor = StyleAnchor(
                workspace_id=workspace_id,
                description=description,
                forbidden_words=forbidden_words,
            )
            session.add(anchor)
        else:
            anchor.description = description
            anchor.forbidden_words = forbidden_words
        session.commit()
        _ = (anchor.description, anchor.forbidden_words)
        session.expunge(anchor)
        return anchor
