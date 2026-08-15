import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core import proactive
from novel_editorial.core.chat import build_agent_prompt, list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.store.db import DB, workspace_db_path
from novel_editorial.store.events import list_events
from novel_editorial.store.models import Agent, AgentRole, PlotThread, Workspace

runner = CliRunner()


def _create_workspace(
    tmp_path: Path,
    monkeypatch,
    *,
    title: str = "叙事之书",
    genre: str = "悬疑",
) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title, "--genre", genre])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _plant(
    workspace_id: str,
    *,
    kind: str = "foreshadow",
    content: str = "侦探口袋里的旧车票",
    chapter: str | None = "第二章",
) -> str:
    args = ["plot", "plant", workspace_id, "--kind", kind, "--content", content]
    if chapter is not None:
        args.extend(["--chapter", chapter])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return result.output.split()[1]


@pytest.mark.smoke
def test_plant_creates_planted_record(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        [
            "plot",
            "plant",
            workspace_id,
            "--kind",
            "foreshadow",
            "--content",
            "侦探口袋里的旧车票",
            "--chapter",
            "第二章",
        ],
    )
    assert result.exit_code == 0, result.output
    thread_id = result.output.split()[1]

    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        thread = session.get(PlotThread, thread_id)
        assert thread is not None
        assert thread.workspace_id == workspace_id
        assert thread.kind == "foreshadow"
        assert thread.content == "侦探口袋里的旧车票"
        assert thread.status == "planted"
        assert thread.chapter == "第二章"
        assert len(thread.id) == 32
        assert thread.created_at is not None


def test_plot_list_shows_threads_and_empty_hint(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    empty = runner.invoke(app, ["plot", "list", workspace_id])
    assert empty.exit_code == 0
    assert "no plot threads yet" in empty.output

    _plant(workspace_id, kind="hook", content="雨夜巷口的人影", chapter=None)
    listing = runner.invoke(app, ["plot", "list", workspace_id])
    assert listing.exit_code == 0, listing.output
    assert "[钩子]" in listing.output
    assert "planted" in listing.output
    assert "雨夜巷口的人影" in listing.output


@pytest.mark.smoke
def test_plot_recover_marks_recovered_and_is_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    thread_id = _plant(workspace_id)

    recovered = runner.invoke(app, ["plot", "recover", workspace_id, thread_id])
    assert recovered.exit_code == 0, recovered.output
    assert f"recovered {thread_id}" in recovered.output

    again = runner.invoke(app, ["plot", "recover", workspace_id, thread_id])
    assert again.exit_code == 0, again.output
    assert "already recovered" in again.output

    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        thread = session.get(PlotThread, thread_id)
        assert thread is not None
        assert thread.status == "recovered"


def test_plot_recover_wrong_workspace_leaves_thread_untouched(
    tmp_path: Path, monkeypatch
) -> None:
    first_id = _create_workspace(tmp_path, monkeypatch, title="甲书")
    second_id = _create_workspace(tmp_path, monkeypatch, title="乙书")
    thread_id = _plant(first_id, kind="foreshadow", content="只属于甲书的线索")

    wrong = runner.invoke(app, ["plot", "recover", second_id, thread_id])
    assert wrong.exit_code == 1, wrong.output
    assert "plot thread not found" in wrong.output

    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(first_id) as session:
        thread = session.get(PlotThread, thread_id)
        assert thread is not None
        assert thread.status == "planted"


def test_plot_plant_rejects_invalid_kind_and_empty_content(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    bad_kind = runner.invoke(
        app, ["plot", "plant", workspace_id, "--kind", "teaser", "--content", "x"]
    )
    assert bad_kind.exit_code == 2
    assert "invalid kind" in bad_kind.output

    empty = runner.invoke(
        app, ["plot", "plant", workspace_id, "--kind", "hook", "--content", "   "]
    )
    assert empty.exit_code == 2
    assert "must not be empty" in empty.output


def test_plot_plant_rejects_multiline_content(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    contents = (
        "第一行\n第二行",
        "第一行\r第二行",
        "第一行\u2028第二行",
        "第一行\n",
        "第一行\r",
        "第一行\r\n",
        "第一行\u2028",
    )
    for content in contents:
        result = runner.invoke(
            app, ["plot", "plant", workspace_id, "--kind", "foreshadow", "--content", content]
        )
        assert result.exit_code == 2, result.output
        assert "must not contain newlines" in result.output

    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        threads = session.query(PlotThread).filter_by(workspace_id=workspace_id).all()
    assert threads == []


@pytest.mark.smoke
def test_plot_plant_emits_reviewer_consistency(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        [
            "plot",
            "plant",
            workspace_id,
            "--kind",
            "foreshadow",
            "--content",
            "侦探口袋里的旧车票",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "审稿: 线索「侦探口袋里的旧车票」埋下了" in result.output

    db = DB(load_settings())
    consistency = [
        message
        for message in list_messages(db, workspace_id)
        if json.loads(message.payload)["kind"] == proactive.PROACTIVE_KIND_CONSISTENCY
    ]
    assert len(consistency) == 1
    assert consistency[0].actor == "审稿"
    assert consistency[0].content == (
        "线索「侦探口袋里的旧车票」埋下了。我记进时间线，回头逐章对照，别让它断在半路。"
    )
    assert json.loads(consistency[0].payload) == {
        "initiator": "agent",
        "kind": proactive.PROACTIVE_KIND_CONSISTENCY,
        "trigger": proactive.TRIGGER_PLOT_PLANTED,
    }

    events = list_events(db, workspace_id)
    assert [event.type for event in events] == ["agent.message"]
    assert json.loads(events[0].payload) == json.loads(consistency[0].payload)


def test_disabled_proactive_suppresses_plot_consistency(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("NOVEL_PROACTIVE_ENABLED", "false")
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        [
            "plot",
            "plant",
            workspace_id,
            "--kind",
            "hook",
            "--content",
            "雨夜巷口的人影",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "审稿:" not in result.output

    db = DB(load_settings())
    assert list_messages(db, workspace_id) == []


def test_plot_unknown_workspace_and_thread_not_found(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    missing_workspace = runner.invoke(app, ["plot", "list", "nope"])
    assert missing_workspace.exit_code == 1
    assert "workspace not found" in missing_workspace.output

    missing_thread = runner.invoke(
        app,
        ["plot", "recover", workspace_id, "deadbeefdeadbeefdeadbeefdeadbeef"],
    )
    assert missing_thread.exit_code == 1
    assert "plot thread not found" in missing_thread.output


def test_memory_pack_includes_open_threads_only(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _plant(workspace_id, kind="foreshadow", content="旧案的钥匙藏在钟楼", chapter="第三章")
    _plant(workspace_id, kind="goal", content="查出旧案真凶", chapter=None)
    recovered_id = _plant(workspace_id, kind="hook", content="雨夜的敲门声")
    assert runner.invoke(app, ["plot", "recover", workspace_id, recovered_id]).exit_code == 0

    pack = runner.invoke(app, ["memory", "pack", workspace_id])
    assert pack.exit_code == 0, pack.output
    assert "悬置线索：" in pack.output
    assert "[伏笔] 旧案的钥匙藏在钟楼（第三章）" in pack.output
    assert "[目标] 查出旧案真凶" in pack.output
    assert "雨夜的敲门声" not in pack.output


def test_memory_pack_omits_section_when_no_open_threads(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    pack = runner.invoke(app, ["memory", "pack", workspace_id])
    assert pack.exit_code == 0, pack.output
    assert "悬置线索" not in pack.output


def test_reviewer_prompt_includes_open_threads(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _plant(workspace_id, kind="foreshadow", content="第三章出现的红伞", chapter="第三章")
    recovered_id = _plant(workspace_id, kind="hook", content="开场的不明脚步声")
    assert runner.invoke(app, ["plot", "recover", workspace_id, recovered_id]).exit_code == 0

    settings = load_settings()
    db = DB(settings)
    with db.global_session() as session:
        workspace = session.get(Workspace, workspace_id)
    assert workspace is not None
    with db.workspace_session(workspace_id) as session:
        reviewer = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, role=AgentRole.REVIEWER)
            .first()
        )
    assert reviewer is not None

    prompt = build_agent_prompt(
        workspace,
        reviewer,
        [],
        latest_message="请审稿",
        db=db,
        workspace_id=workspace_id,
    )
    assert "悬置线索：" in prompt
    assert "[伏笔] 第三章出现的红伞（第三章）" in prompt
    assert "开场的不明脚步声" not in prompt


def test_threads_are_isolated_across_workspaces(tmp_path: Path, monkeypatch) -> None:
    first_id = _create_workspace(tmp_path, monkeypatch, title="甲书")
    second_id = _create_workspace(tmp_path, monkeypatch, title="乙书")
    _plant(first_id, kind="foreshadow", content="甲书的秘密", chapter="第一章")

    listing_b = runner.invoke(app, ["plot", "list", second_id])
    assert listing_b.exit_code == 0
    assert "甲书的秘密" not in listing_b.output
    assert "no plot threads yet" in listing_b.output

    pack_b = runner.invoke(app, ["memory", "pack", second_id])
    assert pack_b.exit_code == 0
    assert "甲书的秘密" not in pack_b.output

    listing_a = runner.invoke(app, ["plot", "list", first_id])
    assert listing_a.exit_code == 0
    assert "甲书的秘密" in listing_a.output


def test_plot_upgrades_pre_migration_workspace(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = workspace_db_path(settings, workspace_id)
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE IF EXISTS plot_threads")
    connection.execute("DROP TABLE IF EXISTS events")
    connection.execute("DELETE FROM alembic_version")
    connection.execute("INSERT INTO alembic_version (version_num) VALUES ('2c8ab7642c70')")
    connection.commit()
    connection.close()

    result = runner.invoke(
        app,
        [
            "plot",
            "plant",
            workspace_id,
            "--kind",
            "goal",
            "--content",
            "升级旧库后仍能埋设",
        ],
    )
    assert result.exit_code == 0, result.output
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        threads = session.query(PlotThread).filter_by(workspace_id=workspace_id).all()
    assert len(threads) == 1
    assert threads[0].content == "升级旧库后仍能埋设"
