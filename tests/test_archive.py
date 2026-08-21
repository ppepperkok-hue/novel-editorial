"""Tests for N25 S1: workspace archive export/import core service."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.archive import (
    ARCHIVE_FORMAT,
    ARCHIVE_VERSION,
    export_workspace_archive,
    import_workspace_archive,
)
from novel_editorial.core.chat import record_message
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.plot import plant_thread
from novel_editorial.core.setting import add_setting
from novel_editorial.core.structure import (
    STATUS_COMPLETED,
    create_node,
    set_workspace_status,
)
from novel_editorial.core.style import set_style_anchor
from novel_editorial.store.db import DB, list_workspace_ids, workspace_db_path
from novel_editorial.store.events import list_events
from novel_editorial.store.models import (
    Draft,
    DraftVersion,
    StyleAnchor,
    Workspace,
)

runner = CliRunner()

_TABLES = [
    "agents",
    "agent_memories",
    "behavior_timeline",
    "decisions",
    "draft_versions",
    "drafts",
    "events",
    "memory_embeddings",
    "messages",
    "outlines",
    "plot_threads",
    "reviews",
    "setting_entries",
    "setting_versions",
    "style_anchors",
    "workspace_structure_nodes",
]


def _create_workspace(
    tmp_path: Path,
    monkeypatch,
    *,
    title: str = "归档之书",
    genre: str = "网文",
    description: str = "一部可以搬家的作品",
) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(
        app,
        ["works", "create", title, "--genre", genre, "--description", description],
    )
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _db() -> DB:
    return DB(load_settings())


def _seed_workspace(db: DB, workspace_id: str) -> None:
    """Fill a workspace with drafts, versions, messages, settings, structure, style, events."""
    set_workspace_status(db, workspace_id, STATUS_COMPLETED)
    set_style_anchor(db, workspace_id, description="冷峻、克制", forbidden_words="宛如、仿佛")
    add_setting(db, workspace_id, kind="character", name="沈夜", content="雨夜归乡的侦探")
    add_setting(db, workspace_id, kind="timeline", name="旧车站", content="末班车十一点进站")
    volume = create_node(db, workspace_id, kind="volume", title="第一卷")
    create_node(db, workspace_id, kind="chapter", title="第一章", parent_id=volume.id)
    with db.workspace_session(workspace_id) as session:
        draft = _add_draft_with_version(session, workspace_id)
        session.commit()
        assert draft.id
    plant_thread(db, workspace_id, kind="foreshadow", content="黑伞人始终背对站台")
    record_message(db, workspace_id, role="user", actor="作者", content="第一章先按这个写")
    record_message(
        db,
        workspace_id,
        role="agent",
        actor="总编",
        content="基调可以，先写正文",
        payload={"kind": "note"},
    )


def _add_draft_with_version(session, workspace_id: str):
    draft = Draft(workspace_id=workspace_id, title="第一章", current_version=1)
    session.add(draft)
    session.flush()
    session.add(
        DraftVersion(
            draft_id=draft.id,
            version=1,
            content="雨夜的车站空无一人。",
            reason="initial",
        )
    )
    return draft


def _normalized_rows(db: DB, workspace_id: str, table: str) -> list[dict]:
    """Return every row of one data.db table with workspace_id normalized."""
    path = workspace_db_path(db.settings, workspace_id)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
    return [
        {key: ("<ws>" if key == "workspace_id" else value) for key, value in dict(row).items()}
        for row in rows
    ]


def _workspace_id_values(db: DB, workspace_id: str, table: str) -> set[str]:
    path = workspace_db_path(db.settings, workspace_id)
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "workspace_id" not in columns:
            return set()
        return {
            row[0]
            for row in conn.execute(f"SELECT DISTINCT workspace_id FROM {table}")
        }


def _events_without_import_marker(db: DB, workspace_id: str) -> list[dict]:
    rows = _normalized_rows(db, workspace_id, "events")
    return [
        row
        for row in rows
        if "workspace_imported" not in row["payload"]
    ]


def _workspace_count(db: DB) -> int:
    with db.global_session() as session:
        return session.query(Workspace).count()


def _write_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def test_export_import_round_trip_preserves_all_layers(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    _seed_workspace(db, workspace_id)

    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    archive_path = export_workspace_archive(db, workspace_id, export_dir)

    assert re.fullmatch(
        rf"novel-export-{workspace_id}-\d{{8}}-\d{{6}}\.zip", archive_path.name
    )
    with zipfile.ZipFile(archive_path) as zf:
        assert set(zf.namelist()) == {"data.db", "manifest.json"}
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["format"] == ARCHIVE_FORMAT
        assert manifest["version"] == ARCHIVE_VERSION
        assert manifest["workspace"]["id"] == workspace_id
        assert manifest["workspace"]["title"] == "归档之书"
        assert manifest["workspace"]["genre"] == "网文"
        assert manifest["workspace"]["status"] == STATUS_COMPLETED
        assert (
            manifest["files"]["data.db"]
            == hashlib.sha256(zf.read("data.db")).hexdigest()
        )

    imported = import_workspace_archive(db, archive_path)

    assert imported.id != workspace_id
    assert len(imported.id) == 32
    assert re.fullmatch(r"[0-9a-f]{32}", imported.id)
    assert imported.title == "归档之书"
    with db.global_session() as session:
        source = session.get(Workspace, workspace_id)
        restored = session.get(Workspace, imported.id)
        assert source is not None and restored is not None
        assert restored.title == source.title
        assert restored.genre == source.genre
        assert restored.description == source.description
        assert restored.status == source.status
        assert restored.created_at == source.created_at

    for table in _TABLES:
        if table == "events":
            continue
        assert _normalized_rows(db, workspace_id, table) == _normalized_rows(
            db, imported.id, table
        ), table
        values = _workspace_id_values(db, imported.id, table)
        if values:
            assert values == {imported.id}, table

    assert _events_without_import_marker(db, imported.id) == _events_without_import_marker(
        db, workspace_id
    )
    assert len(list_events(db, imported.id)) == len(list_events(db, workspace_id)) + 1

    with db.workspace_session(imported.id) as session:
        anchor = session.query(StyleAnchor).filter_by(workspace_id=imported.id).first()
        assert anchor is not None
        assert anchor.description == "冷峻、克制"
        assert anchor.forbidden_words == "宛如、仿佛"


def test_export_is_read_only(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    _seed_workspace(db, workspace_id)
    data_path = workspace_db_path(db.settings, workspace_id)
    data_before = data_path.read_bytes()
    events_before = len(list_events(db, workspace_id))

    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    export_workspace_archive(db, workspace_id, export_dir)

    assert data_path.read_bytes() == data_before
    assert len(list_events(db, workspace_id)) == events_before
    works = db.settings.data_dir / "works"
    assert {path.name for path in works.iterdir()} == {workspace_id}


def test_export_target_directory_creates_named_zip(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    export_dir = tmp_path / "out"
    export_dir.mkdir()

    archive_path = export_workspace_archive(db, workspace_id, export_dir)

    assert archive_path.parent == export_dir
    assert archive_path.exists()
    with zipfile.ZipFile(archive_path) as zf:
        assert "manifest.json" in zf.namelist()


def test_export_target_file_path(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    target = tmp_path / "custom-name.zip"

    archive_path = export_workspace_archive(db, workspace_id, target)

    assert archive_path == target
    assert target.is_file()


def test_export_target_file_exists_rejected(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    target = tmp_path / "exists.zip"
    target.write_bytes(b"old data")

    with pytest.raises(NovelError) as exc_info:
        export_workspace_archive(db, workspace_id, target)

    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert target.read_bytes() == b"old data"


def test_export_parent_missing_rejected(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    target = tmp_path / "no-such-dir" / "out.zip"

    with pytest.raises(NovelError) as exc_info:
        export_workspace_archive(db, workspace_id, target)

    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert not target.exists()
    assert not target.parent.exists()


def test_export_workspace_not_found(tmp_path: Path, monkeypatch) -> None:
    _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        export_workspace_archive(db, "missing", tmp_path)

    assert exc_info.value.code is ErrorCode.NOT_FOUND
    assert "workspace not found" in exc_info.value.message


def test_import_registers_new_workspace_visible_in_commands(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch, title="搬来之家")
    db = _db()
    _seed_workspace(db, workspace_id)
    archive_path = export_workspace_archive(db, workspace_id, tmp_path / "bundle.zip")

    imported = import_workspace_archive(db, archive_path)

    listed = runner.invoke(app, ["works", "list"])
    assert listed.exit_code == 0, listed.output
    assert imported.id in listed.output
    assert "搬来之家" in listed.output

    shown = runner.invoke(app, ["works", "show", imported.id])
    assert shown.exit_code == 0, shown.output
    assert "搬来之家" in shown.output
    assert "状态: 已完成" in shown.output

    style = runner.invoke(app, ["style", "show", imported.id])
    assert style.exit_code == 0, style.output
    assert "冷峻、克制" in style.output
    assert "宛如、仿佛" in style.output

    events = runner.invoke(app, ["events", "list", imported.id])
    assert events.exit_code == 0, events.output
    assert "workspace_imported" in events.output
    assert workspace_id in events.output

    log = runner.invoke(app, ["log", imported.id])
    assert log.exit_code == 0, log.output
    assert "雨夜的车站空无一人" in log.output


def test_import_missing_archive_not_found(tmp_path: Path, monkeypatch) -> None:
    _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        import_workspace_archive(db, tmp_path / "no-such.zip")

    assert exc_info.value.code is ErrorCode.NOT_FOUND
    assert "archive not found" in exc_info.value.message


def test_import_bad_zip_rejected(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"this is not a zip archive")

    with pytest.raises(NovelError) as exc_info:
        import_workspace_archive(db, bad)

    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert set(list_workspace_ids(db.settings)) == {workspace_id}
    assert _workspace_count(db) == 1


def test_import_missing_manifest_rejected(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    archive = tmp_path / "no-manifest.zip"
    _write_zip(archive, {"data.db": b"anything"})

    with pytest.raises(NovelError) as exc_info:
        import_workspace_archive(db, archive)

    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "manifest" in exc_info.value.message
    assert set(list_workspace_ids(db.settings)) == {workspace_id}


def test_import_missing_data_db_rejected(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    manifest = {
        "format": ARCHIVE_FORMAT,
        "version": ARCHIVE_VERSION,
        "exported_at": "2026-08-21T00:00:00+00:00",
        "workspace": {
            "id": workspace_id,
            "title": "源",
            "genre": "",
            "description": "",
            "status": "writing",
            "created_at": "2026-08-21T00:00:00+00:00",
        },
        "files": {"data.db": "0" * 64},
    }
    archive = tmp_path / "no-data.zip"
    _write_zip(archive, {"manifest.json": json.dumps(manifest).encode("utf-8")})

    with pytest.raises(NovelError) as exc_info:
        import_workspace_archive(db, archive)

    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "missing data.db" in exc_info.value.message


def test_import_unsupported_version_rejected(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    manifest = {
        "format": ARCHIVE_FORMAT,
        "version": 2,
        "exported_at": "2026-08-21T00:00:00+00:00",
        "workspace": {
            "id": workspace_id,
            "title": "源",
            "genre": "",
            "description": "",
            "status": "writing",
            "created_at": "2026-08-21T00:00:00+00:00",
        },
        "files": {"data.db": "0" * 64},
    }
    archive = tmp_path / "v2.zip"
    _write_zip(
        archive,
        {
            "manifest.json": json.dumps(manifest).encode("utf-8"),
            "data.db": b"data",
        },
    )

    with pytest.raises(NovelError) as exc_info:
        import_workspace_archive(db, archive)

    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "version" in exc_info.value.message
    assert set(list_workspace_ids(db.settings)) == {workspace_id}


def test_import_sha_mismatch_rejected(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    manifest = {
        "format": ARCHIVE_FORMAT,
        "version": ARCHIVE_VERSION,
        "exported_at": "2026-08-21T00:00:00+00:00",
        "workspace": {
            "id": workspace_id,
            "title": "源",
            "genre": "",
            "description": "",
            "status": "writing",
            "created_at": "2026-08-21T00:00:00+00:00",
        },
        "files": {"data.db": "0" * 64},
    }
    archive = tmp_path / "sha-mismatch.zip"
    _write_zip(
        archive,
        {
            "manifest.json": json.dumps(manifest).encode("utf-8"),
            "data.db": b"real bytes",
        },
    )

    with pytest.raises(NovelError) as exc_info:
        import_workspace_archive(db, archive)

    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "sha256" in exc_info.value.message
    assert set(list_workspace_ids(db.settings)) == {workspace_id}


def test_import_failure_cleans_extraction_temp(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    tmp_root = tmp_path / "import-tmp"
    tmp_root.mkdir()
    counter = 0

    def fake_mkdtemp(*args, **kwargs) -> str:
        nonlocal counter
        counter += 1
        path = tmp_root / f"extract-{counter}"
        path.mkdir()
        return str(path)

    monkeypatch.setattr("novel_editorial.core.archive.tempfile.mkdtemp", fake_mkdtemp)
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"garbage")

    with pytest.raises(NovelError):
        import_workspace_archive(db, bad)

    assert list(tmp_root.iterdir()) == []
    assert set(list_workspace_ids(db.settings)) == {workspace_id}


def test_import_failure_cleans_half_created_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    archive = export_workspace_archive(db, workspace_id, tmp_path / "bundle.zip")

    def boom(*args, **kwargs):
        raise RuntimeError("migration failed")

    monkeypatch.setattr("novel_editorial.core.archive.run_migrations", boom)

    with pytest.raises(RuntimeError):
        import_workspace_archive(db, archive)

    assert set(list_workspace_ids(db.settings)) == {workspace_id}
    assert _workspace_count(db) == 1
    works = db.settings.data_dir / "works"
    assert {path.name for path in works.iterdir()} == {workspace_id}


def test_import_failure_after_registration_rolls_back(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    archive = export_workspace_archive(db, workspace_id, tmp_path / "bundle.zip")

    def boom(*args, **kwargs):
        raise RuntimeError("event failed")

    monkeypatch.setattr("novel_editorial.core.archive.record_event", boom)

    with pytest.raises(RuntimeError):
        import_workspace_archive(db, archive)

    assert set(list_workspace_ids(db.settings)) == {workspace_id}
    assert _workspace_count(db) == 1
    works = db.settings.data_dir / "works"
    assert {path.name for path in works.iterdir()} == {workspace_id}


def test_import_rewrites_quoted_table_names(tmp_path: Path, monkeypatch) -> None:
    """A table name with embedded quotes must not leak a raw sqlite3 error."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    archive = export_workspace_archive(db, workspace_id, tmp_path / "base.zip")

    with zipfile.ZipFile(archive) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        data_db = zf.read("data.db")
    hacked = tmp_path / "hacked.db"
    hacked.write_bytes(data_db)
    conn = sqlite3.connect(hacked)
    try:
        conn.execute(
            'CREATE TABLE "weird""name" (id TEXT PRIMARY KEY, workspace_id TEXT)'
        )
        conn.execute(
            'INSERT INTO "weird""name" (id, workspace_id) VALUES (?, ?)',
            ("row-1", workspace_id),
        )
        conn.commit()
    finally:
        conn.close()
    manifest["files"]["data.db"] = hashlib.sha256(hacked.read_bytes()).hexdigest()
    quoted_archive = tmp_path / "quoted.zip"
    with zipfile.ZipFile(quoted_archive, "w") as zf:
        zf.write(hacked, arcname="data.db")
        zf.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False),
        )

    imported = import_workspace_archive(db, quoted_archive)

    assert imported.id != workspace_id
    with sqlite3.connect(workspace_db_path(db.settings, imported.id)) as conn:
        rows = conn.execute('SELECT workspace_id FROM "weird""name"').fetchall()
    assert rows == [(imported.id,)]


def test_import_non_sqlite_data_db_rejected_cleanly(
    tmp_path: Path, monkeypatch
) -> None:
    """Garbage data.db with a self-consistent manifest is a clean USAGE_ERROR."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    garbage = b"not a sqlite database, but the manifest sha256 matches"
    manifest = {
        "format": ARCHIVE_FORMAT,
        "version": ARCHIVE_VERSION,
        "exported_at": "2026-08-21T00:00:00+00:00",
        "workspace": {
            "id": workspace_id,
            "title": "源",
            "genre": "",
            "description": "",
            "status": "writing",
            "created_at": "2026-08-21T00:00:00+00:00",
        },
        "files": {"data.db": hashlib.sha256(garbage).hexdigest()},
    }
    archive = tmp_path / "non-sqlite.zip"
    _write_zip(
        archive,
        {
            "manifest.json": json.dumps(manifest).encode("utf-8"),
            "data.db": garbage,
        },
    )

    tmp_root = tmp_path / "import-tmp"
    tmp_root.mkdir()
    counter = 0

    def fake_mkdtemp(*args, **kwargs) -> str:
        nonlocal counter
        counter += 1
        path = tmp_root / f"extract-{counter}"
        path.mkdir()
        return str(path)

    monkeypatch.setattr("novel_editorial.core.archive.tempfile.mkdtemp", fake_mkdtemp)

    with pytest.raises(NovelError) as exc_info:
        import_workspace_archive(db, archive)

    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "not a SQLite database" in exc_info.value.message
    assert set(list_workspace_ids(db.settings)) == {workspace_id}
    assert _workspace_count(db) == 1
    assert list(tmp_root.iterdir()) == []


def test_import_magic_prefix_garbage_rejected_cleanly(
    tmp_path: Path, monkeypatch
) -> None:
    """SQLite magic prefix + garbage data.db is a clean USAGE_ERROR, no residue."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    garbage = b"SQLite format 3\x00" + b"\xde\xad\xbe\xef" * 64
    manifest = {
        "format": ARCHIVE_FORMAT,
        "version": ARCHIVE_VERSION,
        "exported_at": "2026-08-21T00:00:00+00:00",
        "workspace": {
            "id": workspace_id,
            "title": "源",
            "genre": "",
            "description": "",
            "status": "writing",
            "created_at": "2026-08-21T00:00:00+00:00",
        },
        "files": {"data.db": hashlib.sha256(garbage).hexdigest()},
    }
    archive = tmp_path / "magic-garbage.zip"
    _write_zip(
        archive,
        {
            "manifest.json": json.dumps(manifest).encode("utf-8"),
            "data.db": garbage,
        },
    )

    tmp_root = tmp_path / "import-tmp"
    tmp_root.mkdir()
    counter = 0

    def fake_mkdtemp(*args, **kwargs) -> str:
        nonlocal counter
        counter += 1
        path = tmp_root / f"extract-{counter}"
        path.mkdir()
        return str(path)

    monkeypatch.setattr("novel_editorial.core.archive.tempfile.mkdtemp", fake_mkdtemp)

    with pytest.raises(NovelError) as exc_info:
        import_workspace_archive(db, archive)
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "not a SQLite database" in exc_info.value.message

    works = db.settings.data_dir / "works"
    assert {path.name for path in works.iterdir()} == {workspace_id}
    assert _workspace_count(db) == 1
    assert list(tmp_root.iterdir()) == []

    cli_result = runner.invoke(app, ["works", "import", str(archive)])
    assert cli_result.exit_code == 2
    assert "not a SQLite database" in cli_result.output
    assert "DatabaseError" not in cli_result.output
    assert {path.name for path in works.iterdir()} == {workspace_id}
    assert _workspace_count(db) == 1
    assert list(tmp_root.iterdir()) == []
