"""CLI tests for N25 S2: works export / import end-to-end and exit codes."""

from __future__ import annotations

import gc
import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import record_message
from novel_editorial.core.config import load_settings
from novel_editorial.core.plot import plant_thread
from novel_editorial.core.setting import add_setting
from novel_editorial.core.structure import (
    STATUS_COMPLETED,
    create_node,
    set_workspace_status,
)
from novel_editorial.core.style import set_style_anchor
from novel_editorial.store.db import DB, list_workspace_ids
from novel_editorial.store.models import Draft, DraftVersion

runner = CliRunner()


def _create_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    title: str = "搬家之书",
) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(
        app,
        ["works", "create", title, "--genre", "网文", "--description", "端到端归档"],
    )
    assert result.exit_code == 0, result.output
    match = re.search(r"created workspace (\w+):", result.output)
    assert match is not None
    return match.group(1)


def _db() -> DB:
    return DB(load_settings())


def _seed_workspace(db: DB, workspace_id: str) -> None:
    """Fill drafts, messages, settings, structure, style, and events."""
    set_workspace_status(db, workspace_id, STATUS_COMPLETED)
    set_style_anchor(db, workspace_id, description="冷峻、克制", forbidden_words="宛如、仿佛")
    add_setting(db, workspace_id, kind="character", name="沈夜", content="雨夜归乡的侦探")
    volume = create_node(db, workspace_id, kind="volume", title="第一卷")
    create_node(db, workspace_id, kind="chapter", title="第一章", parent_id=volume.id)
    with db.workspace_session(workspace_id) as session:
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
        session.commit()
    plant_thread(db, workspace_id, kind="foreshadow", content="黑伞人始终背对站台")
    record_message(db, workspace_id, role="user", actor="作者", content="第一章先按这个写")
    record_message(
        db,
        workspace_id,
        role="agent",
        actor="总编",
        content="基调可以，先写正文",
    )


@pytest.mark.parametrize(
    ("args", "label"),
    [
        (["works", "export", "--help"], "works export"),
        (["works", "import", "--help"], "works import"),
    ],
    ids=["works export", "works import"],
)
def test_export_import_registered_and_documented(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str], label: str
) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, args)
    assert result.exit_code == 0, f"{label}: {result.output}"
    assert label in result.output


def test_export_import_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    _seed_workspace(db, workspace_id)
    target = tmp_path / "bundle.zip"

    exported = runner.invoke(app, ["works", "export", workspace_id, str(target)])
    assert exported.exit_code == 0, exported.output
    assert exported.output.strip() == f"exported: {target}"
    assert target.is_file()

    data_dir = tmp_path / "data"
    db.global_engine.dispose()
    for engine in list(db._workspace_engines.values()):
        engine.dispose()
    db._workspace_engines.clear()
    gc.collect()
    shutil.rmtree(data_dir)
    data_dir.mkdir()

    imported = runner.invoke(app, ["works", "import", str(target)])
    assert imported.exit_code == 0, imported.output
    match = re.search(r"imported workspace (\w+): (.+)", imported.output.strip())
    assert match is not None
    new_id, title = match.group(1), match.group(2)
    assert new_id != workspace_id
    assert title == "搬家之书"

    listed = runner.invoke(app, ["works", "list"])
    assert listed.exit_code == 0, listed.output
    assert new_id in listed.output
    assert "搬家之书" in listed.output

    shown = runner.invoke(app, ["works", "show", new_id])
    assert shown.exit_code == 0, shown.output
    assert "搬家之书" in shown.output
    assert "状态: 已完成" in shown.output
    assert "genre: 网文" in shown.output
    assert "结构：" in shown.output
    assert "[卷] 第一卷" in shown.output

    style = runner.invoke(app, ["style", "show", new_id])
    assert style.exit_code == 0, style.output
    assert "冷峻、克制" in style.output
    assert "宛如、仿佛" in style.output

    events = runner.invoke(app, ["events", "list", new_id])
    assert events.exit_code == 0, events.output
    assert "workspace_imported" in events.output
    assert workspace_id in events.output

    log = runner.invoke(app, ["log", new_id])
    assert log.exit_code == 0, log.output
    assert "雨夜的车站空无一人" in log.output
    assert "第一章先按这个写" in log.output
    assert "基调可以，先写正文" in log.output


def test_export_missing_workspace_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app, ["works", "export", "does-not-exist", str(tmp_path / "x.zip")]
    )
    assert result.exit_code == 1
    assert "workspace not found" in result.output


def test_export_target_exists_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    target = tmp_path / "exists.zip"
    target.write_bytes(b"old data")

    result = runner.invoke(app, ["works", "export", workspace_id, str(target)])

    assert result.exit_code == 2
    assert "target exists" in result.output
    assert target.read_bytes() == b"old data"


def test_import_missing_archive_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["works", "import", str(tmp_path / "no-such.zip")])
    assert result.exit_code == 1
    assert "archive not found" in result.output


def test_import_bad_archive_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"this is not a zip archive")

    result = runner.invoke(app, ["works", "import", str(bad)])

    assert result.exit_code == 2
    assert "invalid archive" in result.output
    assert list_workspace_ids(load_settings()) == [workspace_id]
