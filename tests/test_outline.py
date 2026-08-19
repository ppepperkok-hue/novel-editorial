"""Tests for N13 J2: versioned outline service and CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.outline import (
    create_outline,
    get_outline,
    list_outline_versions,
    revise_outline,
)
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events

runner = CliRunner()


def _create_workspace(
    tmp_path: Path, monkeypatch, title: str = "大纲之书"
) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _db() -> DB:
    return DB(load_settings())


def _event_kinds(db: DB, workspace_id: str) -> list[str]:
    events = list_events(db, workspace_id)
    return [json.loads(event.payload)["kind"] for event in events]


def test_outline_create_and_get(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    outline = create_outline(db, workspace_id, content="第一章：雨夜", actor="作者")

    assert outline.version == 1
    assert outline.actor == "作者"
    assert outline.reason == "initial"
    current = get_outline(db, workspace_id)
    assert current is not None
    assert current.id == outline.id
    assert current.content == "第一章：雨夜"
    assert "outline_created" in _event_kinds(db, workspace_id)


def test_outline_revise_bumps_version_and_traces_events(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    create_outline(db, workspace_id, content="v1 内容", actor="作者")
    revised = revise_outline(
        db,
        workspace_id,
        content="v2 内容",
        reason="角色线调整",
        actor="责编",
    )

    assert revised.version == 2
    current = get_outline(db, workspace_id)
    assert current is not None
    assert current.content == "v2 内容"
    versions = list_outline_versions(db, workspace_id)
    assert [version.version for version in versions] == [2, 1]
    assert [version.actor for version in versions] == ["责编", "作者"]

    events = list_events(db, workspace_id)
    payloads = [json.loads(event.payload) for event in events]
    assert [payload["kind"] for payload in payloads] == [
        "outline_revised",
        "outline_created",
    ]
    assert all(event.type == "system" for event in events)
    revised_payload = payloads[0]
    assert revised_payload["outline_id"] == revised.id
    assert revised_payload["version"] == 2
    assert revised_payload["actor"] == "责编"
    assert revised_payload["reason"] == "角色线调整"


def test_outline_duplicate_create_is_usage_error(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    create_outline(db, workspace_id, content="初版", actor="作者")

    with pytest.raises(NovelError) as exc_info:
        create_outline(db, workspace_id, content="重复", actor="作者")
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "already exists" in exc_info.value.message


def test_outline_revise_without_outline_is_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        revise_outline(
            db, workspace_id, content="内容", reason="理由", actor="作者"
        )
    assert exc_info.value.code is ErrorCode.NOT_FOUND
    assert "outline not found" in exc_info.value.message


def test_outline_validation_and_unknown_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        create_outline(db, workspace_id, content="   ", actor="作者")
    assert exc_info.value.code is ErrorCode.USAGE_ERROR

    with pytest.raises(NovelError) as exc_info:
        create_outline(db, workspace_id, content="内容", actor="   ")
    assert exc_info.value.code is ErrorCode.USAGE_ERROR

    create_outline(db, workspace_id, content="初版", actor="作者")
    with pytest.raises(NovelError) as exc_info:
        revise_outline(
            db,
            workspace_id,
            content="新内容",
            reason="   ",
            actor="作者",
        )
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    with pytest.raises(NovelError) as exc_info:
        revise_outline(
            db,
            workspace_id,
            content="新内容",
            reason="理由",
            actor="",
        )
    assert exc_info.value.code is ErrorCode.USAGE_ERROR

    for accessor in (
        lambda: create_outline(db, "missing", content="内容", actor="作者"),
        lambda: get_outline(db, "missing"),
        lambda: list_outline_versions(db, "missing"),
    ):
        with pytest.raises(NovelError) as exc_info:
            accessor()
        assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_outline_get_and_list_empty(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    assert get_outline(db, workspace_id) is None
    assert list_outline_versions(db, workspace_id) == []


def test_outline_event_failure_only_warns(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    def boom(*args, **kwargs):
        raise RuntimeError("events table down")

    monkeypatch.setattr("novel_editorial.core.outline.record_event", boom)
    outline = create_outline(db, workspace_id, content="内容", actor="作者")

    current = get_outline(db, workspace_id)
    assert current is not None
    assert current.id == outline.id
    captured = capsys.readouterr()
    assert "warning: outline_created event skipped" in captured.err
    assert "events table down" in captured.err


def test_outline_cli_create_revise_show_history(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    created = runner.invoke(
        app,
        ["outline", "create", workspace_id, "--content", "楔子：雨夜车站", "--actor", "作者"],
    )
    assert created.exit_code == 0, created.output
    assert created.output.strip() == "outline v1 created"

    revised = runner.invoke(
        app,
        [
            "outline",
            "revise",
            workspace_id,
            "--content",
            "楔子：雨夜车站，钟停十一点",
            "--reason",
            "加悬念",
            "--actor",
            "责编",
        ],
    )
    assert revised.exit_code == 0, revised.output
    assert revised.output.strip() == "outline v2 saved"

    shown = runner.invoke(app, ["outline", "show", workspace_id])
    assert shown.exit_code == 0, shown.output
    assert shown.output.startswith("outline v2：")
    assert "雨夜车站，钟停十一点" in shown.output

    history = runner.invoke(app, ["outline", "history", workspace_id])
    assert history.exit_code == 0, history.output
    lines = history.output.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("v2 ")
    assert "责编" in lines[0]
    assert "加悬念" in lines[0]
    assert lines[1].startswith("v1 ")
    assert "作者" in lines[1]
    assert "initial" in lines[1]


def test_outline_cli_no_outline_and_missing_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    shown = runner.invoke(app, ["outline", "show", workspace_id])
    assert shown.exit_code == 0
    assert shown.output.strip() == "no outline"

    history = runner.invoke(app, ["outline", "history", workspace_id])
    assert history.exit_code == 0
    assert history.output.strip() == "no outline"

    revised = runner.invoke(
        app,
        ["outline", "revise", workspace_id, "--content", "内容", "--reason", "理由"],
    )
    assert revised.exit_code == 1
    assert "outline not found" in revised.output

    unknown = runner.invoke(app, ["outline", "show", "does-not-exist"])
    assert unknown.exit_code == 1
    assert "workspace not found" in unknown.output


def test_outline_cli_duplicate_create_is_usage_error(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    first = runner.invoke(
        app, ["outline", "create", workspace_id, "--content", "初版"]
    )
    assert first.exit_code == 0, first.output

    second = runner.invoke(
        app, ["outline", "create", workspace_id, "--content", "重复"]
    )
    assert second.exit_code == 2
    assert "already exists" in second.output


def test_outline_cli_history_truncates_long_reason_and_limit(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    runner.invoke(app, ["outline", "create", workspace_id, "--content", "初版"])
    runner.invoke(
        app,
        [
            "outline",
            "revise",
            workspace_id,
            "--content",
            "二版",
            "--reason",
            "长" * 50,
        ],
    )
    runner.invoke(
        app,
        [
            "outline",
            "revise",
            workspace_id,
            "--content",
            "三版",
            "--reason",
            "短理由",
        ],
    )

    history = runner.invoke(
        app, ["outline", "history", workspace_id, "--limit", "2"]
    )
    assert history.exit_code == 0, history.output
    lines = history.output.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("v3 ")
    assert "短理由" in lines[0]
    assert lines[1].startswith("v2 ")
    assert ("长" * 40) + "…" in lines[1]
    assert "v1" not in history.output
