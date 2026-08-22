"""DB lifecycle tests: public dispose() releases engines and stays re-openable."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import text

from novel_editorial.core.config import load_settings
from novel_editorial.core.workspace import create_workspace
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, Draft, DraftVersion, Workspace


def _seeded_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[DB, str]:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    workspace = create_workspace(db, title="处置之书", genre="悬疑")
    return db, workspace.id


def test_dispose_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, workspace_id = _seeded_db(tmp_path, monkeypatch)

    db.dispose()
    db.dispose()
    db.dispose()

    # Engines stay usable after dispose: they reconnect lazily.
    db.ping()
    with db.workspace_session(workspace_id) as session:
        assert session.query(Agent).count() == 4


def test_dispose_clears_engine_cache_and_releases_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, _ = _seeded_db(tmp_path, monkeypatch)
    assert db._workspace_engines  # one workspace engine is cached

    db.dispose()

    assert db._workspace_engines == {}
    # SQLite file handles must be released so the data directory can be
    # removed (the Windows cleanup path the panel demo relies on).
    shutil.rmtree(db.settings.data_dir)
    assert not db.settings.data_dir.exists()


def test_workspace_reopens_after_dispose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, workspace_id = _seeded_db(tmp_path, monkeypatch)

    db.dispose()

    # Reopening re-initializes the workspace engine (schema at head) and the
    # global registry stays readable.
    with db.global_session() as session:
        found = session.get(Workspace, workspace_id)
        assert found is not None
        assert found.title == "处置之书"

    with db.workspace_session(workspace_id) as session:
        draft = Draft(
            workspace_id=workspace_id,
            title="第一章",
            status="draft",
            current_version=1,
        )
        session.add(draft)
        session.flush()
        session.add(
            DraftVersion(
                draft_id=draft.id,
                version=1,
                content="雨夜开场，钩子埋下。",
                reason="initial",
            )
        )
        session.commit()
        draft_id = draft.id

    db.dispose()
    with db.workspace_session(workspace_id) as session:
        rows = session.execute(
            text("SELECT title, current_version FROM drafts WHERE id = :draft_id"),
            {"draft_id": draft_id},
        ).one()
        assert rows == ("第一章", 1)
