import json
import sqlite3
from pathlib import Path

import sqlalchemy as sa
from typer.testing import CliRunner

import novel_editorial.core.retrieval as retrieval_module
from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.memory import (
    add_memory_note,
    archive_memory_notes,
)
from novel_editorial.core.retrieval import (
    LAYER_NOTE,
    LAYER_SETTING,
    SemanticHit,
    delete_embedding,
    delete_embedding_safe,
    reindex_embeddings,
    render_semantic_hit,
    semantic_search,
    upsert_embedding,
    upsert_embedding_safe,
)
from novel_editorial.core.setting import add_setting
from novel_editorial.llm.embeddings import build_embedding_client
from novel_editorial.store.db import DB, workspace_db_path
from novel_editorial.store.models import Agent, MemoryEmbedding

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


def _writer_id(db: DB, workspace_id: str) -> str:
    with db.workspace_session(workspace_id) as session:
        writer = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, role="writer")
            .first()
        )
        assert writer is not None
        return writer.id


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


def test_semantic_search_hits_n_gram_similar_note(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer_id = _writer_id(db, workspace_id)
    note = add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content="雨夜回乡 客船靠岸",
    )

    hits = semantic_search(db, workspace_id, "雨夜归乡 客船")

    assert hits
    assert hits[0].layer == LAYER_NOTE
    assert hits[0].source_id == note.id
    assert hits[0].score > 0.0
    assert hits[0].content == "雨夜回乡 客船靠岸"
    assert hits[0].detail == "写手"


def test_semantic_search_skips_archived_note(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer_id = _writer_id(db, workspace_id)
    note = add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content="雨夜回乡 客船靠岸",
    )
    archive_memory_notes(db, workspace_id, [note.id])

    hits = semantic_search(db, workspace_id, "雨夜归乡 客船")

    assert hits == []


def test_semantic_search_skips_deleted_sources(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    upsert_embedding(
        db,
        workspace_id,
        layer=LAYER_NOTE,
        source_id="ghost-note",
        text="雨夜回乡 客船靠岸",
    )
    upsert_embedding(
        db,
        workspace_id,
        layer=LAYER_SETTING,
        source_id="ghost-setting",
        text="雨夜归乡 客船",
    )

    hits = semantic_search(db, workspace_id, "雨夜归乡 客船")

    assert hits == []


def test_semantic_search_empty_index_degrades_silently(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    hits = semantic_search(db, workspace_id, "任何词")

    assert hits == []
    assert capsys.readouterr().err == ""


def test_semantic_search_embed_failure_warns_and_degrades(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer_id = _writer_id(db, workspace_id)
    add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content="雨夜回乡 客船靠岸",
    )

    class FailingEmbedder:
        def embed(self, text: str) -> list[float]:
            raise RuntimeError("embedding request failed")

    monkeypatch.setattr(
        "novel_editorial.core.retrieval.build_embedding_client",
        lambda settings: FailingEmbedder(),
    )
    hits = semantic_search(db, workspace_id, "雨夜归乡 客船")

    assert hits == []
    captured = capsys.readouterr()
    assert "warning: semantic search skipped" in captured.err
    assert "embedding request failed" in captured.err


def test_semantic_search_backend_unavailable_warns_and_degrades(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer_id = _writer_id(db, workspace_id)
    add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content="雨夜回乡 客船靠岸",
    )

    def boom(*args, **kwargs):
        raise RuntimeError("embedding backend down")

    monkeypatch.setattr(
        "novel_editorial.core.retrieval.build_embedding_client", boom
    )
    hits = semantic_search(db, workspace_id, "雨夜归乡 客船")

    assert hits == []
    captured = capsys.readouterr()
    assert "warning: semantic search skipped" in captured.err
    assert "embedding backend down" in captured.err


def test_semantic_search_top_k_orders_by_score(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer_id = _writer_id(db, workspace_id)
    exact = add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content="雨夜归乡 客船",
    )
    partial = add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content="雨夜归乡",
    )
    add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content="完全无关的内容甲",
    )

    hits = semantic_search(db, workspace_id, "雨夜归乡 客船", top_k=2)

    assert [hit.source_id for hit in hits] == [exact.id, partial.id]
    assert [hit.score for hit in hits] == sorted(
        (hit.score for hit in hits), reverse=True
    )


def test_semantic_search_default_top_k_from_settings(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("NOVEL_EMBEDDING_TOP_K", "2")
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer_id = _writer_id(db, workspace_id)
    for content in ("雨夜归乡 客船", "雨夜归乡", "完全无关的内容甲"):
        add_memory_note(
            db,
            workspace_id,
            writer_id,
            actor="写手",
            content=content,
        )

    hits = semantic_search(db, workspace_id, "雨夜归乡 客船")

    assert len(hits) == 2
    assert hits[0].source_id != hits[1].source_id


def test_semantic_search_isolated_between_workspaces(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")
    db = _db()
    writer_a = _writer_id(db, workspace_a)
    writer_b = _writer_id(db, workspace_b)
    note_a = add_memory_note(
        db,
        workspace_a,
        writer_a,
        actor="写手",
        content="雨夜回乡 客船靠岸",
    )
    note_b = add_memory_note(
        db,
        workspace_b,
        writer_b,
        actor="写手",
        content="烈日当空 黄沙扑面",
    )

    hits_a = semantic_search(db, workspace_a, "雨夜归乡 客船")
    hits_b = semantic_search(db, workspace_b, "雨夜归乡 客船")

    assert hits_a and all(hit.source_id == note_a.id for hit in hits_a)
    assert hits_b and all(hit.source_id == note_b.id for hit in hits_b)


def test_reindex_embeddings_is_idempotent_and_counts(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer_id = _writer_id(db, workspace_id)
    note = add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content="雨夜回乡",
    )
    archived = add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content="旧档案",
    )
    archive_memory_notes(db, workspace_id, [archived.id])
    add_setting(
        db,
        workspace_id,
        kind="world",
        name="客船",
        content="客船靠岸",
        source="作者",
    )
    with db.workspace_session(workspace_id) as session:
        session.query(MemoryEmbedding).delete()
        session.commit()

    assert note.id != archived.id
    assert reindex_embeddings(db, workspace_id) == 3
    assert len(_vectors(db, workspace_id)) == 3
    assert reindex_embeddings(db, workspace_id) == 3
    assert len(_vectors(db, workspace_id)) == 3


def test_reindex_embeddings_counts_partial_failures(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer_id = _writer_id(db, workspace_id)
    add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content="雨夜回乡",
    )
    add_setting(
        db,
        workspace_id,
        kind="world",
        name="客船",
        content="客船靠岸",
        source="作者",
    )
    original = retrieval_module.upsert_embedding_safe

    def flaky(
        db: DB,
        workspace_id: str,
        *,
        layer: str,
        source_id: str,
        text: str,
    ) -> bool:
        if layer == LAYER_SETTING:
            return False
        return original(
            db,
            workspace_id,
            layer=layer,
            source_id=source_id,
            text=text,
        )

    monkeypatch.setattr(
        "novel_editorial.core.retrieval.upsert_embedding_safe", flaky
    )

    assert reindex_embeddings(db, workspace_id) == 1


def test_render_semantic_hit_note(tmp_path: Path, monkeypatch) -> None:
    hit = SemanticHit(
        layer=LAYER_NOTE,
        source_id="n1",
        score=0.87,
        content="雨夜回乡 客船靠岸",
        detail="写手",
    )

    rendered = render_semantic_hit(hit, "雨夜归乡 客船")

    assert rendered.startswith("[笔记] ")
    assert "（来源: 写手）" in rendered
    assert rendered.endswith("[语义 0.87]")


def test_render_semantic_hit_setting(tmp_path: Path, monkeypatch) -> None:
    hit = SemanticHit(
        layer=LAYER_SETTING,
        source_id="s1",
        score=0.91,
        content="客船靠岸",
        detail="作者 v2",
        name="客船",
        label="世界观",
    )

    rendered = render_semantic_hit(hit, "雨夜")

    assert rendered.startswith("[设定] 世界观：客船——")
    assert "（来源: 作者 v2）" in rendered
    assert rendered.endswith("[语义 0.91]")
