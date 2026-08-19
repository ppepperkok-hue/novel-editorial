import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.store.db import DB, global_db_path
from novel_editorial.store.models import Agent

runner = CliRunner()


@pytest.mark.smoke
def test_works_create_and_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["works", "create", "测试之书", "--genre", "网文"])
    assert result.exit_code == 0, result.output
    assert "created workspace" in result.output

    settings = load_settings()
    assert global_db_path(settings).exists()

    result = runner.invoke(app, ["works", "list"])
    assert result.exit_code == 0
    assert "测试之书" in result.output


def test_workspace_band_seeded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["works", "create", "第二本", "--genre", "同人"])
    assert result.exit_code == 0, result.output

    settings = load_settings()
    db = DB(settings)
    works_dir = settings.data_dir / "works"
    assert works_dir.exists()
    workspace_dir = next(works_dir.iterdir())
    assert (workspace_dir / "data.db").exists()
    with db.workspace_session(workspace_dir.name) as session:
        agents = session.query(Agent).all()
        assert len(agents) == 4


def test_works_show(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    create = runner.invoke(app, ["works", "create", "展示之书", "--genre", "短篇"])
    assert create.exit_code == 0, create.output
    match = re.search(r"created workspace (\w+):", create.output)
    assert match is not None
    workspace_id = match.group(1)

    result = runner.invoke(app, ["works", "show", workspace_id])
    assert result.exit_code == 0, result.output
    assert "展示之书" in result.output
    assert "总编" in result.output
    assert "写手" in result.output


def test_works_show_missing_returns_business_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["works", "show", "does-not-exist"])
    assert result.exit_code == 1
    assert "workspace not found" in result.output


def _created_workspace_id(create_output: str) -> str:
    match = re.search(r"created workspace (\w+):", create_output)
    assert match is not None
    return match.group(1)


def test_works_status_flow_and_invalid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    create = runner.invoke(app, ["works", "create", "状态之书"])
    assert create.exit_code == 0, create.output
    workspace_id = _created_workspace_id(create.output)

    for status in ("completed", "shelved", "writing"):
        result = runner.invoke(app, ["works", "status", workspace_id, status])
        assert result.exit_code == 0, result.output
        assert result.output.strip() == f"status updated: {workspace_id} {status}"

    invalid = runner.invoke(app, ["works", "status", workspace_id, "done"])
    assert invalid.exit_code == 2
    assert "invalid status" in invalid.output


def test_works_show_zero_structure_output_only_adds_status_line(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    create = runner.invoke(
        app,
        ["works", "create", "零结构之书", "--genre", "短篇", "--description", "没有结构的简介"],
    )
    assert create.exit_code == 0, create.output
    workspace_id = _created_workspace_id(create.output)

    shown = runner.invoke(app, ["works", "show", workspace_id])
    assert shown.exit_code == 0, shown.output
    assert shown.output.splitlines() == [
        f"id: {workspace_id}",
        "title: 零结构之书",
        "状态: 创作中",
        "genre: 短篇",
        "description: 没有结构的简介",
        "band:",
        "  editor_in_chief: 总编",
        "  editor: 责编",
        "  writer: 写手",
        "  reviewer: 审稿",
    ]


def test_works_show_status_line_and_structure_tree(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    create = runner.invoke(
        app,
        ["works", "create", "结构展示之书", "--genre", "长篇", "--description", "一段简介"],
    )
    assert create.exit_code == 0, create.output
    workspace_id = _created_workspace_id(create.output)

    empty_show = runner.invoke(app, ["works", "show", workspace_id])
    assert empty_show.exit_code == 0, empty_show.output
    assert "状态: 创作中" in empty_show.output
    assert "结构：" not in empty_show.output

    add_volume = runner.invoke(
        app, ["structure", "add", workspace_id, "volume", "第一卷"]
    )
    assert add_volume.exit_code == 0, add_volume.output
    volume_id = add_volume.output.split()[1]
    add_chapter = runner.invoke(
        app,
        ["structure", "add", workspace_id, "chapter", "第一章", "--parent", volume_id],
    )
    assert add_chapter.exit_code == 0, add_chapter.output
    chapter_id = add_chapter.output.split()[1]

    status = runner.invoke(app, ["works", "status", workspace_id, "completed"])
    assert status.exit_code == 0, status.output
    assert status.output.strip() == f"status updated: {workspace_id} completed"

    shown = runner.invoke(app, ["works", "show", workspace_id])
    assert shown.exit_code == 0, shown.output
    lines = shown.output.splitlines()
    assert "title: 结构展示之书" in lines
    status_index = lines.index("状态: 已完成")
    description_index = lines.index("description: 一段简介")
    assert status_index < description_index
    assert lines[status_index + 1] == "genre: 长篇"
    assert lines[status_index + 2] == "description: 一段简介"

    structure_index = lines.index("结构：")
    assert lines[structure_index + 1] == f"[卷] 第一卷（{volume_id}）"
    assert lines[structure_index + 2] == f"  [章] 第一章（{chapter_id}）"
