import json
import sqlite3
from pathlib import Path

import sqlalchemy as sa
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.retrieval import (
    LAYER_NOTE,
    LAYER_SETTING,
    delete_embedding,
    delete_embedding_safe,
    upsert_embedding,
    upsert_embedding_safe,
)
from novel_editorial.llm.embeddings import build_embedding_client
from novel_editorial.store.db import DB, workspace_db_path
from novel_editorial.store.models import MemoryEmbedding

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch, title: str = "检索之书") -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _db() -> DB:
    return DB(load_settings())


def _vectors(db: DB, workspace_id: str) -> list[MemoryEmbedding]:
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(MemoryEmbedding)
            .order_by(MemoryEmbedding.id)
            .all()
        )


def test_upsert_embedding_creates_row(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    settings = load_settings()

    row = upsert_embedding(
        db,
        workspace_id,
        layer=LAYER_NOTE,
        source_id="n1",
        text="雨夜归乡",
    )

    assert row.workspace_id == workspace_id
    assert row.layer == LAYER_NOTE
    assert row.source_id == "n1"
    assert row.dim == settings.embedding_dim
    assert json.loads(row.vector) == build_embedding_client(settings).embed("雨夜归乡")
    assert row.updated_at is not None
    assert len(_vectors(db, workspace_id)) == 1


def test_upsert_embedding_same_key_overwrites(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    settings = load_settings()

    upsert_embedding(
        db,
        workspace_id,
        layer=LAYER_NOTE,
        source_id="n1",
        text="旧内容",
    )
    upsert_embedding(
        db,
        workspace_id,
        layer=LAYER_NOTE,
        source_id="n1",
        text="新内容",
    )

    rows = _vectors(db, workspace_id)
    assert len(rows) == 1
    assert json.loads(rows[0].vector) == build_embedding_client(settings).embed(
        "新内容"
    )


def test_upsert_embedding_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    upsert_embedding(
        db,
        workspace_id,
        layer=LAYER_SETTING,
        source_id="s1",
        text="同一段设定",
    )
    upsert_embedding(
        db,
        workspace_id,
        layer=LAYER_SETTING,
        source_id="s1",
        text="同一段设定",
    )

    assert len(_vectors(db, workspace_id)) == 1


def test_delete_embedding_removes_row(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    upsert_embedding(
        db,
        workspace_id,
        layer=LAYER_NOTE,
        source_id="n1",
        text="要删的向量",
    )

    assert delete_embedding(db, workspace_id, layer=LAYER_NOTE, source_id="n1") is True
    assert _vectors(db, workspace_id) == []


def test_delete_embedding_missing_row_is_success(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    assert delete_embedding(db, workspace_id, layer=LAYER_NOTE, source_id="nope") is False
    assert _vectors(db, workspace_id) == []


def test_embeddings_are_isolated_between_workspaces(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")
    db = _db()

    upsert_embedding(
        db,
        workspace_a,
        layer=LAYER_NOTE,
        source_id="n1",
        text="甲书秘密",
    )
    upsert_embedding(
        db,
        workspace_b,
        layer=LAYER_NOTE,
        source_id="n1",
        text="乙书秘密",
    )

    assert len(_vectors(db, workspace_a)) == 1
    assert len(_vectors(db, workspace_b)) == 1
    assert delete_embedding(db, workspace_a, layer=LAYER_NOTE, source_id="n1") is True
    assert len(_vectors(db, workspace_b)) == 1


def test_upsert_safe_warns_on_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    def boom(*args, **kwargs):
        raise RuntimeError("embedding backend down")

    monkeypatch.setattr("novel_editorial.core.retrieval.upsert_embedding", boom)
    result = upsert_embedding_safe(
        db,
        workspace_id,
        layer=LAYER_NOTE,
        source_id="n1",
        text="无所谓",
    )

    assert result is False
    captured = capsys.readouterr()
    assert "warning: embedding index skipped" in captured.err
    assert "embedding backend down" in captured.err


def test_delete_safe_warns_on_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    def boom(*args, **kwargs):
        raise RuntimeError("delete failed")

    monkeypatch.setattr("novel_editorial.core.retrieval.delete_embedding", boom)
    result = delete_embedding_safe(db, workspace_id, layer=LAYER_NOTE, source_id="n1")

    assert result is False
    captured = capsys.readouterr()
    assert "warning: embedding index delete skipped" in captured.err
    assert "delete failed" in captured.err


def test_memory_embedding_model_columns() -> None:
    columns = set(MemoryEmbedding.__table__.columns.keys())
    assert columns == {
        "id",
        "workspace_id",
        "layer",
        "source_id",
        "vector",
        "dim",
        "updated_at",
    }
    table = MemoryEmbedding.__table__
    assert isinstance(table, sa.Table)
    assert any(
        constraint.name == "uq_memory_embeddings_layer_source"
        for constraint in table.constraints
    )


def test_embedding_migration_upgrades_from_92a0(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = workspace_db_path(settings, workspace_id)
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE IF EXISTS memory_embeddings")
    connection.execute("DELETE FROM alembic_version")
    connection.execute(
        "INSERT INTO alembic_version (version_num) VALUES ('92a0cb3a3bb1')"
    )
    connection.commit()
    connection.close()

    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        inspector = sa.inspect(session.get_bind())
        assert "memory_embeddings" in inspector.get_table_names()
        index_names = {
            index["name"] for index in inspector.get_indexes("memory_embeddings")
        }
        assert "ix_memory_embeddings_workspace_id" in index_names

    row = upsert_embedding(
        db,
        workspace_id,
        layer=LAYER_NOTE,
        source_id="backfilled",
        text="迁移后的索引",
    )
    assert row.dim == settings.embedding_dim


def test_embedding_migration_replay_is_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = workspace_db_path(settings, workspace_id)

    for _ in range(2):
        connection = sqlite3.connect(path)
        connection.execute("DROP TABLE IF EXISTS memory_embeddings")
        connection.execute("DELETE FROM alembic_version")
        connection.execute(
            "INSERT INTO alembic_version (version_num) VALUES ('92a0cb3a3bb1')"
        )
        connection.commit()
        connection.close()

        db = DB(settings)
        with db.workspace_session(workspace_id) as session:
            inspector = sa.inspect(session.get_bind())
            assert "memory_embeddings" in inspector.get_table_names()
        row = upsert_embedding(
            db,
            workspace_id,
            layer=LAYER_SETTING,
            source_id="s1",
            text="重放后仍可写",
        )
        assert row.dim == settings.embedding_dim
