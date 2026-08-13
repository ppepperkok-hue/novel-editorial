"""Style anchor services."""

from __future__ import annotations

import re

from novel_editorial.store.db import DB
from novel_editorial.store.models import StyleAnchor

_KEYWORD_SEPARATOR_RE = re.compile(r"[、，,；;。！？!?…—–·・\-\s]+")


def extract_style_keywords(description: str) -> frozenset[str]:
    """Extract keyword phrases from a style description.

    Separator-delimited descriptions (顿号/逗号/空格 etc.) yield each separated
    token as one keyword; an unseparated run of text yields every consecutive
    2-4 character substring. Empty, blank, or separator-only descriptions yield
    an empty set.
    """
    text = (description or "").strip()
    if not text:
        return frozenset()
    tokens = [token for token in _KEYWORD_SEPARATOR_RE.split(text) if token]
    if not tokens:
        return frozenset()
    if len(tokens) > 1:
        return frozenset(token for token in tokens if len(token) >= 2)
    run = tokens[0]
    return frozenset(
        run[start : start + length]
        for length in (2, 3, 4)
        for start in range(len(run) - length + 1)
    )


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
