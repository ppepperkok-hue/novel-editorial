"""Tests for N13 J1: workspace structure tree and progress status model."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.structure import (
    KIND_CHAPTER,
    KIND_SECTION,
    KIND_VOLUME,
    STATUS_COMPLETED,
    STATUS_SHELVED,
    STATUS_WRITING,
    VALID_KINDS,
    VALID_STATUSES,
    count_structure,
    create_node,
    list_structure,
    move_node,
    remove_node,
    rename_node,
    set_node_status,
    set_workspace_status,
)
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import Draft, Workspace, WorkspaceStructureNode

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch, title: str = "结构之书") -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _db() -> DB:
    return DB(load_settings())


def _event_kinds(db: DB, workspace_id: str) -> list[str]:
    events = list_events(db, workspace_id)
    return [json.loads(event.payload).get("kind") for event in events]


def test_structure_constants() -> None:
    assert VALID_KINDS == (KIND_VOLUME, KIND_CHAPTER, KIND_SECTION)
    assert VALID_STATUSES == (
        STATUS_WRITING,
        STATUS_COMPLETED,
        STATUS_SHELVED,
    )


def test_workspace_status_defaults_to_writing(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    with db.global_session() as session:
        workspace = session.get(Workspace, workspace_id)
        assert workspace is not None
        assert workspace.status == STATUS_WRITING


def test_create_root_nodes_of_any_kind_and_auto_sort(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    volume = create_node(db, workspace_id, kind=KIND_VOLUME, title="第一卷")
    chapter = create_node(db, workspace_id, kind=KIND_CHAPTER, title="楔子")
    section = create_node(db, workspace_id, kind=KIND_SECTION, title="开篇")

    assert len(volume.id) == 32
    assert volume.workspace_id == workspace_id
    assert volume.parent_id is None
    assert volume.sort_order == 1
    assert volume.status == STATUS_WRITING
    assert chapter.sort_order == 2
    assert section.sort_order == 3
    assert [node.id for node in list_structure(db, workspace_id)] == [
        volume.id,
        chapter.id,
        section.id,
    ]


def test_create_nested_volume_chapter_section(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    volume = create_node(db, workspace_id, kind=KIND_VOLUME, title="第一卷")
    chapter = create_node(
        db, workspace_id, kind=KIND_CHAPTER, title="第一章", parent_id=volume.id
    )
    section = create_node(
        db, workspace_id, kind=KIND_SECTION, title="第一节", parent_id=chapter.id
    )

    assert chapter.parent_id == volume.id
    assert chapter.sort_order == 1
    assert section.parent_id == chapter.id
    with db.workspace_session(workspace_id) as session:
        assert session.get(WorkspaceStructureNode, chapter.id) is not None
        assert session.get(WorkspaceStructureNode, section.id) is not None


def test_create_node_draft_id_is_reference_only(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    node = create_node(
        db,
        workspace_id,
        kind=KIND_CHAPTER,
        title="挂草稿",
        draft_id="no-such-draft",
    )
    assert node.draft_id == "no-such-draft"
    assert node.id in {item.id for item in list_structure(db, workspace_id)}


@pytest.mark.parametrize(
    "parent_kind,child_kind",
    [
        (KIND_CHAPTER, KIND_VOLUME),
        (KIND_SECTION, KIND_CHAPTER),
        (KIND_VOLUME, KIND_VOLUME),
        (KIND_CHAPTER, KIND_CHAPTER),
        (KIND_SECTION, KIND_SECTION),
    ],
)
def test_create_invalid_hierarchy(
    tmp_path: Path, monkeypatch, parent_kind: str, child_kind: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    parent = create_node(db, workspace_id, kind=parent_kind, title="父节点")
    with pytest.raises(NovelError) as exc_info:
        create_node(
            db,
            workspace_id,
            kind=child_kind,
            title="非法子节点",
            parent_id=parent.id,
        )
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert (
        "invalid parent kind" in exc_info.value.message
        or "cannot have a parent" in exc_info.value.message
    )


def test_create_rejects_blank_title_and_invalid_kind(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    with pytest.raises(NovelError) as exc_info:
        create_node(db, workspace_id, kind=KIND_CHAPTER, title="   ")
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    with pytest.raises(NovelError) as exc_info:
        create_node(db, workspace_id, kind="book", title="书")
    assert exc_info.value.code is ErrorCode.USAGE_ERROR


def test_create_node_rejects_negative_sort_order(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    with pytest.raises(NovelError) as exc_info:
        create_node(
            db, workspace_id, kind=KIND_CHAPTER, title="负序", sort_order=-5
        )
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "invalid sort order" in exc_info.value.message
    assert list_structure(db, workspace_id) == []


def test_create_parent_missing_or_other_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")
    db = _db()
    foreign = create_node(db, workspace_a, kind=KIND_VOLUME, title="甲卷")

    with pytest.raises(NovelError) as exc_info:
        create_node(
            db, workspace_a, kind=KIND_CHAPTER, title="孤儿", parent_id="missing"
        )
    assert exc_info.value.code is ErrorCode.NOT_FOUND

    with pytest.raises(NovelError) as exc_info:
        create_node(
            db,
            workspace_b,
            kind=KIND_CHAPTER,
            title="跨作品",
            parent_id=foreign.id,
        )
    assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_create_unknown_workspace(tmp_path: Path, monkeypatch) -> None:
    _create_workspace(tmp_path, monkeypatch)
    db = _db()
    with pytest.raises(NovelError) as exc_info:
        create_node(db, "missing", kind=KIND_CHAPTER, title="无主")
    assert exc_info.value.code is ErrorCode.NOT_FOUND
    assert "workspace not found" in exc_info.value.message


def test_list_structure_empty_and_workspace_isolation(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")
    db = _db()
    assert list_structure(db, workspace_a) == []
    assert count_structure(db, workspace_a) == {
        "volumes": 0,
        "chapters": 0,
        "sections": 0,
        "completed_chapters": 0,
        "total_nodes": 0,
    }

    create_node(db, workspace_a, kind=KIND_VOLUME, title="甲卷")
    assert len(list_structure(db, workspace_a)) == 1
    assert list_structure(db, workspace_b) == []
    assert count_structure(db, workspace_b)["total_nodes"] == 0


def test_list_structure_parent_first_deterministic(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    root_a = create_node(db, workspace_id, kind=KIND_VOLUME, title="甲", sort_order=2)
    root_b = create_node(db, workspace_id, kind=KIND_CHAPTER, title="乙", sort_order=1)
    child_b = create_node(
        db, workspace_id, kind=KIND_SECTION, title="乙节", parent_id=root_b.id
    )
    child_a = create_node(
        db, workspace_id, kind=KIND_CHAPTER, title="甲章", parent_id=root_a.id
    )

    assert [node.id for node in list_structure(db, workspace_id)] == [
        root_b.id,
        child_b.id,
        root_a.id,
        child_a.id,
    ]


def test_list_structure_tiebreak_by_id(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    first = create_node(db, workspace_id, kind=KIND_CHAPTER, title="甲", sort_order=9)
    second = create_node(db, workspace_id, kind=KIND_CHAPTER, title="乙", sort_order=9)
    fixed = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    with db.workspace_session(workspace_id) as session:
        session.query(WorkspaceStructureNode).filter(
            WorkspaceStructureNode.id.in_([first.id, second.id])
        ).update({"created_at": fixed}, synchronize_session=False)
        session.commit()

    expected = sorted([first.id, second.id])
    assert [node.id for node in list_structure(db, workspace_id)] == expected


def test_rename_node_updates_title_and_events(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    node = create_node(db, workspace_id, kind=KIND_CHAPTER, title="旧名")

    renamed = rename_node(db, workspace_id, node.id, "新名")

    assert renamed.title == "新名"
    listed = list_structure(db, workspace_id)
    assert [item.title for item in listed] == ["新名"]
    assert "structure_created" in _event_kinds(db, workspace_id)
    assert "structure_renamed" in _event_kinds(db, workspace_id)


def test_rename_node_missing_or_blank(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    with pytest.raises(NovelError) as exc_info:
        rename_node(db, workspace_id, "missing", "新名")
    assert exc_info.value.code is ErrorCode.NOT_FOUND

    node = create_node(db, workspace_id, kind=KIND_CHAPTER, title="保持")
    with pytest.raises(NovelError) as exc_info:
        rename_node(db, workspace_id, node.id, "   ")
    assert exc_info.value.code is ErrorCode.USAGE_ERROR


def test_move_node_to_root_and_reorder(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    root = create_node(db, workspace_id, kind=KIND_VOLUME, title="卷")
    first = create_node(
        db, workspace_id, kind=KIND_CHAPTER, title="甲", parent_id=root.id
    )
    second = create_node(
        db, workspace_id, kind=KIND_CHAPTER, title="乙", parent_id=root.id
    )
    assert first.sort_order == 1
    assert second.sort_order == 2

    moved = move_node(db, workspace_id, first.id, parent_id=None)
    assert moved.parent_id is None
    assert moved.sort_order == 2
    assert [node.title for node in list_structure(db, workspace_id)] == [
        root.title,
        second.title,
        first.title,
    ]

    back = move_node(
        db, workspace_id, first.id, parent_id=root.id, sort_order=1
    )
    assert back.parent_id == root.id
    assert back.sort_order == 1
    assert [node.title for node in list_structure(db, workspace_id)] == [
        root.title,
        first.title,
        second.title,
    ]


def test_move_node_to_same_parent_without_order_is_noop(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    volume = create_node(db, workspace_id, kind=KIND_VOLUME, title="卷")
    first = create_node(
        db, workspace_id, kind=KIND_CHAPTER, title="甲", parent_id=volume.id
    )
    second = create_node(
        db, workspace_id, kind=KIND_CHAPTER, title="乙", parent_id=volume.id
    )
    assert [node.title for node in list_structure(db, workspace_id)] == [
        volume.title,
        first.title,
        second.title,
    ]
    events_before = len(_event_kinds(db, workspace_id))

    moved = move_node(db, workspace_id, first.id, parent_id=volume.id)

    assert moved.parent_id == volume.id
    assert moved.sort_order == 1
    assert [node.title for node in list_structure(db, workspace_id)] == [
        volume.title,
        first.title,
        second.title,
    ]
    assert len(_event_kinds(db, workspace_id)) == events_before


def test_move_root_to_root_without_order_is_noop(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    root = create_node(db, workspace_id, kind=KIND_VOLUME, title="卷甲")
    create_node(db, workspace_id, kind=KIND_VOLUME, title="卷乙")
    events_before = len(_event_kinds(db, workspace_id))

    moved = move_node(db, workspace_id, root.id, parent_id=None)

    assert moved.parent_id is None
    assert moved.sort_order == 1
    assert [node.title for node in list_structure(db, workspace_id)] == [
        root.title,
        "卷乙",
    ]
    assert len(_event_kinds(db, workspace_id)) == events_before


def test_move_node_default_sort_appends_to_new_parent(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    root_a = create_node(db, workspace_id, kind=KIND_VOLUME, title="卷甲")
    root_b = create_node(db, workspace_id, kind=KIND_VOLUME, title="卷乙")
    chapter = create_node(
        db, workspace_id, kind=KIND_CHAPTER, title="章", parent_id=root_a.id
    )
    moved = move_node(db, workspace_id, chapter.id, parent_id=root_b.id)

    assert moved.parent_id == root_b.id
    assert moved.sort_order == 1
    assert [node.title for node in list_structure(db, workspace_id)] == [
        root_a.title,
        root_b.title,
        chapter.title,
    ]


def test_move_node_rejects_negative_sort_order(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    volume = create_node(db, workspace_id, kind=KIND_VOLUME, title="卷")
    chapter = create_node(
        db, workspace_id, kind=KIND_CHAPTER, title="章", parent_id=volume.id
    )

    with pytest.raises(NovelError) as exc_info:
        move_node(db, workspace_id, chapter.id, sort_order=-5)
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "invalid sort order" in exc_info.value.message

    with db.workspace_session(workspace_id) as session:
        stored = session.get(WorkspaceStructureNode, chapter.id)
        assert stored is not None
        assert stored.parent_id == volume.id
        assert stored.sort_order == 1


def test_move_node_cycle_self_and_descendant(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    volume = create_node(db, workspace_id, kind=KIND_VOLUME, title="卷")
    chapter = create_node(
        db, workspace_id, kind=KIND_CHAPTER, title="章", parent_id=volume.id
    )
    section = create_node(
        db, workspace_id, kind=KIND_SECTION, title="节", parent_id=chapter.id
    )

    with pytest.raises(NovelError) as exc_info:
        move_node(db, workspace_id, volume.id, parent_id=volume.id)
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "itself or its own subtree" in exc_info.value.message

    with pytest.raises(NovelError) as exc_info:
        move_node(db, workspace_id, volume.id, parent_id=chapter.id)
    assert exc_info.value.code is ErrorCode.USAGE_ERROR

    with pytest.raises(NovelError) as exc_info:
        move_node(db, workspace_id, volume.id, parent_id=section.id)
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert [node.id for node in list_structure(db, workspace_id)] == [
        volume.id,
        chapter.id,
        section.id,
    ]


def test_move_node_invalid_level_or_foreign_parent(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")
    db = _db()
    volume = create_node(db, workspace_a, kind=KIND_VOLUME, title="甲卷")
    chapter = create_node(
        db, workspace_a, kind=KIND_CHAPTER, title="甲章", parent_id=volume.id
    )
    root_chapter = create_node(db, workspace_a, kind=KIND_CHAPTER, title="根章")

    with pytest.raises(NovelError) as exc_info:
        move_node(db, workspace_a, volume.id, parent_id=root_chapter.id)
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "cannot have a parent" in exc_info.value.message

    foreign = create_node(db, workspace_b, kind=KIND_VOLUME, title="乙卷")
    with pytest.raises(NovelError) as exc_info:
        move_node(db, workspace_a, chapter.id, parent_id=foreign.id)
    assert exc_info.value.code is ErrorCode.NOT_FOUND

    with pytest.raises(NovelError) as exc_info:
        move_node(db, workspace_a, "missing", parent_id=None)
    assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_remove_node_cascades_and_keeps_draft_body(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    volume = create_node(db, workspace_id, kind=KIND_VOLUME, title="卷")
    chapter = create_node(
        db, workspace_id, kind=KIND_CHAPTER, title="章", parent_id=volume.id
    )
    section = create_node(
        db, workspace_id, kind=KIND_SECTION, title="节", parent_id=chapter.id
    )
    with db.workspace_session(workspace_id) as session:
        draft = Draft(
            workspace_id=workspace_id,
            title="草稿本体",
            status="draft",
            current_version=1,
        )
        session.add(draft)
        session.commit()
        draft_id = draft.id
    with db.workspace_session(workspace_id) as session:
        section = session.get(WorkspaceStructureNode, section.id)
        assert section is not None
        section.draft_id = draft_id
        session.commit()

    removed = remove_node(db, workspace_id, volume.id)

    assert removed == 3
    assert list_structure(db, workspace_id) == []
    with db.workspace_session(workspace_id) as session:
        assert session.query(WorkspaceStructureNode).count() == 0
        stored_draft = session.get(Draft, draft_id)
        assert stored_draft is not None
        assert stored_draft.title == "草稿本体"


def test_remove_node_missing_and_other_workspace_untouched(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")
    db = _db()
    foreign = create_node(db, workspace_b, kind=KIND_VOLUME, title="乙卷")

    with pytest.raises(NovelError) as exc_info:
        remove_node(db, workspace_a, "missing")
    assert exc_info.value.code is ErrorCode.NOT_FOUND

    removed = remove_node(db, workspace_b, foreign.id)
    assert removed == 1
    assert list_structure(db, workspace_a) == []


def test_set_node_status_flow_and_invalid(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    chapter = create_node(db, workspace_id, kind=KIND_CHAPTER, title="章")
    assert chapter.status == STATUS_WRITING

    completed = set_node_status(
        db, workspace_id, chapter.id, STATUS_COMPLETED
    )
    assert completed.status == STATUS_COMPLETED
    set_node_status(db, workspace_id, chapter.id, STATUS_SHELVED)
    set_node_status(db, workspace_id, chapter.id, STATUS_WRITING)
    with db.workspace_session(workspace_id) as session:
        stored = session.get(WorkspaceStructureNode, chapter.id)
        assert stored is not None
        assert stored.status == STATUS_WRITING

    with pytest.raises(NovelError) as exc_info:
        set_node_status(db, workspace_id, chapter.id, "done")
    assert exc_info.value.code is ErrorCode.USAGE_ERROR

    with pytest.raises(NovelError) as exc_info:
        set_node_status(db, workspace_id, "missing", STATUS_WRITING)
    assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_set_workspace_status_flow_and_invalid(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    workspace = set_workspace_status(
        db, workspace_id, STATUS_COMPLETED
    )
    assert workspace.status == STATUS_COMPLETED
    set_workspace_status(db, workspace_id, STATUS_SHELVED)
    set_workspace_status(db, workspace_id, STATUS_WRITING)
    with db.global_session() as session:
        stored = session.get(Workspace, workspace_id)
        assert stored is not None
        assert stored.status == STATUS_WRITING

    with pytest.raises(NovelError) as exc_info:
        set_workspace_status(db, workspace_id, "done")
    assert exc_info.value.code is ErrorCode.USAGE_ERROR

    with pytest.raises(NovelError) as exc_info:
        set_workspace_status(db, "missing", STATUS_WRITING)
    assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_count_structure_mixed_tree(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    volume = create_node(db, workspace_id, kind=KIND_VOLUME, title="卷甲")
    chapter_done = create_node(
        db, workspace_id, kind=KIND_CHAPTER, title="已完", parent_id=volume.id
    )
    set_node_status(db, workspace_id, chapter_done.id, STATUS_COMPLETED)
    create_node(
        db, workspace_id, kind=KIND_CHAPTER, title="未完", parent_id=volume.id
    )
    create_node(
        db,
        workspace_id,
        kind=KIND_SECTION,
        title="节",
        parent_id=chapter_done.id,
    )
    create_node(db, workspace_id, kind=KIND_VOLUME, title="卷乙")

    assert count_structure(db, workspace_id) == {
        "volumes": 2,
        "chapters": 2,
        "sections": 1,
        "completed_chapters": 1,
        "total_nodes": 5,
    }


def test_structure_events_leave_system_trace(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    node = create_node(db, workspace_id, kind=KIND_CHAPTER, title="事件章")
    parent = create_node(db, workspace_id, kind=KIND_VOLUME, title="事件卷")
    move_node(db, workspace_id, node.id, parent_id=parent.id)
    rename_node(db, workspace_id, node.id, "新事件章")
    move_node(db, workspace_id, node.id, parent_id=None)
    set_node_status(db, workspace_id, node.id, STATUS_COMPLETED)
    set_workspace_status(db, workspace_id, STATUS_SHELVED)
    removed = remove_node(db, workspace_id, node.id)

    assert removed == 1
    events = list_events(db, workspace_id)
    payloads = [json.loads(event.payload) for event in events]
    kinds = [payload["kind"] for payload in payloads]
    assert kinds == [
        "structure_removed",
        "workspace_status_changed",
        "structure_status_changed",
        "structure_moved",
        "structure_renamed",
        "structure_moved",
        "structure_created",
        "structure_created",
    ]
    created = next(
        payload
        for payload in payloads
        if payload["kind"] == "structure_created" and payload["node_id"] == node.id
    )
    assert created["node_id"] == node.id
    assert created["kind"] == "structure_created"
    assert created["title"] == "事件章"
    assert created["parent_id"] is None
    assert all(event.type == "system" for event in events)


def test_event_failure_only_warns_and_keeps_change(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    def boom(*args, **kwargs):
        raise RuntimeError("events table down")

    monkeypatch.setattr("novel_editorial.core.structure.record_event", boom)
    node = create_node(db, workspace_id, kind=KIND_CHAPTER, title="事件坏了")

    assert node.id in {item.id for item in list_structure(db, workspace_id)}
    captured = capsys.readouterr()
    assert "warning: structure_created event skipped" in captured.err
    assert "events table down" in captured.err


def test_workspace_status_backfilled_by_migration(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = settings.data_dir / "global.db"
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE workspaces DROP COLUMN status")
    connection.execute(
        "INSERT INTO workspaces (id, title, genre, description, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "迁移前的旧作品",
            "",
            "",
            "2026-08-01 00:00:00",
        ),
    )
    connection.execute("DELETE FROM alembic_version")
    connection.execute(
        "INSERT INTO alembic_version (version_num) VALUES ('8030d420636d')"
    )
    connection.commit()
    connection.close()

    upgraded = DB(settings)
    upgraded.init_schema()
    with upgraded.global_session() as session:
        workspaces = session.query(Workspace).all()
        assert {item.id for item in workspaces} == {
            workspace_id,
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
        assert all(item.status == STATUS_WRITING for item in workspaces)
