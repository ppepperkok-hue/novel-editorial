"""Tests for N10 O1: cross-workspace aggregation service."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.overview import build_overview
from novel_editorial.store.db import DB
from novel_editorial.store.models import Draft, Event, Workspace, WorkspaceStructureNode

runner = CliRunner()


def _db(tmp_path: Path, monkeypatch) -> DB:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    return DB(load_settings())


def _create_workspace(tmp_path: Path, monkeypatch, title: str) -> str:
    _db(tmp_path, monkeypatch)
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _add_draft(db: DB, workspace_id: str, *, status: str = "draft") -> None:
    with db.workspace_session(workspace_id) as session:
        session.add(
            Draft(workspace_id=workspace_id, title="草稿", status=status)
        )
        session.commit()


def _add_event(
    db: DB, workspace_id: str, when: datetime, *, event_type: str = "system"
) -> None:
    with db.workspace_session(workspace_id) as session:
        session.add(
            Event(
                workspace_id=workspace_id,
                type=event_type,
                time=when,
                actor="system",
            )
        )
        session.commit()


def _add_structure(
    db: DB, workspace_id: str, *, chapters: int, completed: int
) -> None:
    with db.workspace_session(workspace_id) as session:
        for index in range(chapters):
            session.add(
                WorkspaceStructureNode(
                    workspace_id=workspace_id,
                    kind="chapter",
                    title=f"第{index + 1}章",
                    sort_order=index + 1,
                    status="completed" if index < completed else "writing",
                )
            )
        session.commit()


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def test_build_overview_multi_workspace_summary_and_sort(
    tmp_path: Path, monkeypatch
) -> None:
    db = _db(tmp_path, monkeypatch)
    first = _create_workspace(tmp_path, monkeypatch, "甲书")
    second = _create_workspace(tmp_path, monkeypatch, "乙书")

    with db.global_session() as session:
        workspace = session.get(Workspace, first)
        assert workspace is not None
        workspace.status = "completed"
        session.commit()
    _add_structure(db, first, chapters=5, completed=2)
    _add_draft(db, first, status="draft")
    _add_draft(db, first, status="draft")
    _add_draft(db, first, status="accepted")
    first_event = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    second_event = datetime(2026, 8, 19, 8, 0, tzinfo=UTC)
    _add_event(db, first, first_event)
    _add_event(db, second, second_event)

    with db.global_session() as session:
        workspace = session.get(Workspace, first)
        assert workspace is not None
        created_first = _utc(workspace.created_at)

    report = build_overview(db)

    assert report.total == 2
    assert report.skipped == 0
    assert [item.workspace_id for item in report.overviews] == [first, second]
    first_overview = report.overviews[0]
    assert first_overview.title == "甲书"
    assert first_overview.genre == ""
    assert first_overview.status == "completed"
    assert first_overview.pending_count == 2
    assert first_overview.structure == "2/5 章"
    assert first_overview.last_activity == first_event
    assert first_overview.created_at == created_first
    second_overview = report.overviews[1]
    assert second_overview.title == "乙书"
    assert second_overview.status == "writing"
    assert second_overview.pending_count == 0
    assert second_overview.structure == "-"
    assert second_overview.last_activity == second_event


def test_build_overview_empty(tmp_path: Path, monkeypatch) -> None:
    db = _db(tmp_path, monkeypatch)
    db.init_schema()

    report = build_overview(db)

    assert report.overviews == []
    assert report.total == 0
    assert report.skipped == 0


def test_build_overview_structure_dash_when_no_nodes(
    tmp_path: Path, monkeypatch
) -> None:
    db = _db(tmp_path, monkeypatch)
    workspace_id = _create_workspace(tmp_path, monkeypatch, "无结构书")

    empty_report = build_overview(db)
    assert empty_report.overviews[0].structure == "-"

    _add_structure(db, workspace_id, chapters=5, completed=2)
    report = build_overview(db)
    assert report.overviews[0].structure == "2/5 章"


def test_pending_count_only_counts_draft_status(
    tmp_path: Path, monkeypatch
) -> None:
    db = _db(tmp_path, monkeypatch)
    workspace_id = _create_workspace(tmp_path, monkeypatch, "状态书")
    _add_draft(db, workspace_id, status="draft")
    _add_draft(db, workspace_id, status="draft")
    _add_draft(db, workspace_id, status="accepted")
    _add_draft(db, workspace_id, status="quality_failed")

    report = build_overview(db)

    assert report.overviews[0].pending_count == 2


def test_last_activity_uses_latest_event_or_created_at(
    tmp_path: Path, monkeypatch
) -> None:
    db = _db(tmp_path, monkeypatch)
    with_event = _create_workspace(tmp_path, monkeypatch, "有事件书")
    without_event = _create_workspace(tmp_path, monkeypatch, "无事件书")
    _add_event(db, with_event, datetime(2026, 8, 18, 9, 0, tzinfo=UTC))
    _add_event(db, with_event, datetime(2026, 8, 20, 15, 30, tzinfo=UTC))
    with db.global_session() as session:
        created = session.get(Workspace, without_event)
        assert created is not None
        created_time = _utc(created.created_at)

    report = build_overview(db)
    by_id = {item.workspace_id: item for item in report.overviews}

    assert by_id[with_event].last_activity == datetime(
        2026, 8, 20, 15, 30, tzinfo=UTC
    )
    assert by_id[without_event].last_activity == created_time


def test_sort_tiebreak_by_workspace_id(tmp_path: Path, monkeypatch) -> None:
    db = _db(tmp_path, monkeypatch)
    db.init_schema()
    fixed = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    ids = ["a" * 32, "b" * 32, "c" * 32]
    for workspace_id in ids:
        db.create_workspace_db(workspace_id)
        with db.global_session() as session:
            session.add(
                Workspace(id=workspace_id, title="平局书", created_at=fixed)
            )
            session.commit()
        _add_event(db, workspace_id, fixed)

    report = build_overview(db)

    assert [item.workspace_id for item in report.overviews] == sorted(ids)


def test_single_workspace_failure_skips_with_warning(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    db = _db(tmp_path, monkeypatch)
    good = _create_workspace(tmp_path, monkeypatch, "好书")
    bad = _create_workspace(tmp_path, monkeypatch, "坏书")
    _add_draft(db, good, status="draft")

    real_session = DB.workspace_session

    def flaky_session(self: DB, workspace_id: str):
        if workspace_id == bad:
            raise RuntimeError("simulated failure")
        return real_session(self, workspace_id)

    monkeypatch.setattr(DB, "workspace_session", flaky_session)
    report = build_overview(db)
    captured = capsys.readouterr()

    assert [item.workspace_id for item in report.overviews] == [good]
    assert report.total == 1
    assert report.skipped == 1
    assert f"warning: overview skipped: {bad}: simulated failure" in captured.err


def test_cross_workspace_pending_counts_do_not_leak(
    tmp_path: Path, monkeypatch
) -> None:
    db = _db(tmp_path, monkeypatch)
    first = _create_workspace(tmp_path, monkeypatch, "甲书")
    second = _create_workspace(tmp_path, monkeypatch, "乙书")
    _add_draft(db, first, status="draft")
    _add_draft(db, first, status="draft")
    _add_draft(db, second, status="accepted")
    _add_draft(db, second, status="quality_failed")

    report = build_overview(db)
    by_id = {item.workspace_id: item for item in report.overviews}

    assert by_id[first].pending_count == 2
    assert by_id[second].pending_count == 0
