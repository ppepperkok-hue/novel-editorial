from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "简档之书"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def test_agents_show_lists_full_profiles(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["agents", "show", workspace_id])
    assert result.exit_code == 0, result.output
    for name in ("总编", "责编", "写手", "审稿"):
        assert name in result.output
    assert "性格" in result.output
    assert "立场" in result.output
    for profile_fragment in ("沉稳果断", "敏锐挑剔", "手感型创作者", "冷静严谨"):
        assert profile_fragment in result.output
    for stance_fragment in (
        "叙事完整性与作品基调优先",
        "读者节奏优先",
        "忠于人物内心戏",
        "连贯性与一致性优先",
    ):
        assert stance_fragment in result.output
    for label in (
        "价值观",
        "审美",
        "情绪基线",
        "工作习惯",
        "弱点",
        "人际预设",
        "私心",
    ):
        assert label in result.output
    assert "作品完整性高于短期热度" in result.output
    assert "想写出让读者记住某个瞬间的句子" in result.output


def test_agents_show_missing_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["agents", "show", "nope"])
    assert result.exit_code == 1
    assert "workspace not found" in result.output


def test_agents_edit_updates_field(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        [
            "agents",
            "edit",
            workspace_id,
            "写手",
            "--field",
            "aesthetic",
            "--value",
            "偏爱冷峻的画面，拒绝华丽辞藻。",
        ],
    )
    assert result.exit_code == 0, result.output

    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        writer = session.query(Agent).filter_by(workspace_id=workspace_id, role="writer").first()
        assert writer is not None
        assert writer.aesthetic == "偏爱冷峻的画面，拒绝华丽辞藻。"

    shown = runner.invoke(app, ["agents", "show", workspace_id])
    assert shown.exit_code == 0
    assert "偏爱冷峻的画面" in shown.output


def test_agents_edit_by_id(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        writer = session.query(Agent).filter_by(workspace_id=workspace_id, role="writer").first()
        assert writer is not None
        writer_id = writer.id

    result = runner.invoke(
        app,
        [
            "agents",
            "edit",
            workspace_id,
            writer_id,
            "--field",
            "weaknesses",
            "--value",
            "容易把场景写得太满。",
        ],
    )
    assert result.exit_code == 0, result.output
    with db.workspace_session(workspace_id) as session:
        writer = session.query(Agent).filter_by(id=writer_id).first()
        assert writer is not None
        assert writer.weaknesses == "容易把场景写得太满。"


def test_agents_edit_invalid_field(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        [
            "agents",
            "edit",
            workspace_id,
            "写手",
            "--field",
            "hair_color",
            "--value",
            "红色",
        ],
    )
    assert result.exit_code == 2
    assert "unknown profile field" in result.output


def test_agents_edit_unknown_agent(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        [
            "agents",
            "edit",
            workspace_id,
            "nope",
            "--field",
            "values",
            "--value",
            "x",
        ],
    )
    assert result.exit_code == 1
    assert "agent not found" in result.output
