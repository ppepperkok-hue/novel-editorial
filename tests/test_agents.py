from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.agents import (
    create_agent,
    get_default_writer,
    list_agents,
    resolve_agent,
)
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB, DEFAULT_BAND
from novel_editorial.store.models import Agent, AgentRole

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "简档之书"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


@pytest.mark.smoke
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


@pytest.mark.smoke
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


def test_create_agent_writer_multi_instances_allowed(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    first = create_agent(db, workspace_id, name="写手乙", role=AgentRole.WRITER)
    second = create_agent(db, workspace_id, name="写手丙", role=AgentRole.WRITER)
    assert first.id != second.id
    with db.workspace_session(workspace_id) as session:
        writers = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, role=AgentRole.WRITER)
            .all()
        )
    assert len(writers) == 3


def test_create_agent_rejects_duplicate_name_case_insensitive(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    create_agent(db, workspace_id, name="Writer-Beta", role=AgentRole.WRITER)
    with pytest.raises(NovelError) as exc:
        create_agent(db, workspace_id, name="writer-beta", role=AgentRole.WRITER)
    assert exc.value.code == ErrorCode.USAGE_ERROR
    assert "already exists" in exc.value.message


def test_create_agent_rejects_duplicate_non_writer_role(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    with pytest.raises(NovelError) as exc:
        create_agent(db, workspace_id, name="责编乙", role=AgentRole.EDITOR)
    assert exc.value.code == ErrorCode.USAGE_ERROR
    assert "already has a" in exc.value.message


def test_create_agent_rejects_invalid_role_and_empty_name(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    with pytest.raises(NovelError) as exc:
        create_agent(db, workspace_id, name="打杂", role="intern")
    assert exc.value.code == ErrorCode.USAGE_ERROR
    assert "unknown agent role" in exc.value.message
    with pytest.raises(NovelError) as exc2:
        create_agent(db, workspace_id, name="   ", role=AgentRole.WRITER)
    assert exc2.value.code == ErrorCode.USAGE_ERROR
    assert "must not be empty" in exc2.value.message


def test_create_agent_uses_default_profile_and_personality(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    created = create_agent(
        db,
        workspace_id,
        name="写手乙",
        role=AgentRole.WRITER,
        personality="我行我素",
    )
    defaults = next(member for member in DEFAULT_BAND if member["role"] == AgentRole.WRITER)
    assert created.name == "写手乙"
    assert created.personality == "我行我素"
    for field in (
        "stance",
        "values",
        "aesthetic",
        "emotion_baseline",
        "mood",
        "work_habits",
        "weaknesses",
        "relationship_presets",
        "private_motive",
    ):
        assert getattr(created, field) == defaults[field]

    defaulted = create_agent(db, workspace_id, name="写手丙", role=AgentRole.WRITER)
    assert defaulted.personality == defaults["personality"]


def test_get_default_writer_returns_earliest_writer(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    seed_writer = get_default_writer(db, workspace_id)
    assert seed_writer.name == "写手"
    create_agent(db, workspace_id, name="写手乙", role=AgentRole.WRITER)
    create_agent(db, workspace_id, name="写手丙", role=AgentRole.WRITER)
    assert get_default_writer(db, workspace_id).id == seed_writer.id


def test_get_default_writer_not_found_without_writer(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    with db.workspace_session(workspace_id) as session:
        writers = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, role=AgentRole.WRITER)
            .all()
        )
        for writer in writers:
            session.delete(writer)
        session.commit()
    with pytest.raises(NovelError) as exc:
        get_default_writer(db, workspace_id)
    assert exc.value.code == ErrorCode.NOT_FOUND


def test_resolve_agent_by_name_after_adding_writer(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    second = create_agent(db, workspace_id, name="写手乙", role=AgentRole.WRITER)
    assert resolve_agent(db, workspace_id, "写手乙").id == second.id


def test_resolve_agent_name_is_case_insensitive(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    created = create_agent(
        db, workspace_id, name="Writer-Beta", role=AgentRole.WRITER
    )
    assert resolve_agent(db, workspace_id, "writer-beta").id == created.id
    assert resolve_agent(db, workspace_id, "WRITER-BETA").id == created.id


def test_create_agent_rejects_duplicate_non_ascii_casefold(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    create_agent(db, workspace_id, name="Émilie", role=AgentRole.WRITER)
    with pytest.raises(NovelError) as exc:
        create_agent(db, workspace_id, name="émilie", role=AgentRole.WRITER)
    assert exc.value.code == ErrorCode.USAGE_ERROR
    assert "already exists" in exc.value.message


def test_resolve_agent_name_matches_non_ascii_casefold(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    created = create_agent(
        db, workspace_id, name="Émilie", role=AgentRole.WRITER
    )
    assert resolve_agent(db, workspace_id, "émilie").id == created.id


def test_resolve_agent_name_wins_over_role_alias(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    seed_writer = get_default_writer(db, workspace_id)
    assert seed_writer.name == "写手"
    assert resolve_agent(db, workspace_id, "写手").id == seed_writer.id
    chief = resolve_agent(db, workspace_id, "主编")
    assert chief.role == AgentRole.EDITOR_IN_CHIEF


def test_list_agents_orders_by_created_at_and_is_stable(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    create_agent(db, workspace_id, name="写手乙", role=AgentRole.WRITER)
    create_agent(db, workspace_id, name="写手丙", role=AgentRole.WRITER)
    names = [agent.name for agent in list_agents(db, workspace_id)]
    assert set(names) == {"总编", "责编", "写手", "审稿", "写手乙", "写手丙"}
    assert names[-2:] == ["写手乙", "写手丙"]
    assert [agent.name for agent in list_agents(db, workspace_id)] == names


def test_agents_add_and_list_writer(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    created = runner.invoke(
        app,
        [
            "agents",
            "add",
            workspace_id,
            "写手",
            "写手乙",
            "--personality",
            "我行我素",
        ],
    )
    assert created.exit_code == 0, created.output
    assert created.output.startswith("created agent ")
    agent_id = created.output.split()[2].rstrip(":")
    assert ": 写手乙 (writer)" in created.output

    listing = runner.invoke(app, ["agents", "list", workspace_id])
    assert listing.exit_code == 0, listing.output
    assert f"[writer] 写手乙（{agent_id}）" in listing.output
    assert listing.output.splitlines()[-1] == f"[writer] 写手乙（{agent_id}）"

    db = DB(load_settings())
    with db.workspace_session(workspace_id) as session:
        agent = session.query(Agent).filter_by(id=agent_id).first()
    assert agent is not None
    assert agent.role == "writer"
    assert agent.personality == "我行我素"


def test_agents_add_accepts_english_role_label_and_rejects_duplicate_name(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    added = runner.invoke(app, ["agents", "add", workspace_id, "writer", "写手乙"])
    assert added.exit_code == 0, added.output
    assert "(writer)" in added.output

    duplicate = runner.invoke(
        app, ["agents", "add", workspace_id, "writer", "写手乙"]
    )
    assert duplicate.exit_code == 2
    assert "already exists" in duplicate.output


def test_agents_add_rejects_duplicate_non_writer_role_and_invalid_role(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    editor = runner.invoke(app, ["agents", "add", workspace_id, "责编", "责编乙"])
    assert editor.exit_code == 2
    assert "already has a" in editor.output

    bad_role = runner.invoke(app, ["agents", "add", workspace_id, "打杂", "路人"])
    assert bad_role.exit_code == 2
    assert "unknown agent role" in bad_role.output
