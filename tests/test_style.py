import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core import proactive
from novel_editorial.core.chat import list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "风格之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


@pytest.mark.smoke
def test_style_set_emits_reviewer_consistency(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        [
            "style",
            "set",
            workspace_id,
            "--description",
            "平实克制短句",
            "--forbidden",
            "璀璨,宛如",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "style anchor updated" in result.output
    assert "审稿: 风格锚点定了：「平实克制短句」" in result.output
    assert "会不会打架" in result.output

    db = DB(load_settings())
    consistency = [
        message
        for message in list_messages(db, workspace_id)
        if json.loads(message.payload)["kind"] == proactive.PROACTIVE_KIND_CONSISTENCY
    ]
    assert len(consistency) == 1
    assert consistency[0].actor == "审稿"
    assert consistency[0].content == (
        "风格锚点定了：「平实克制短句」。"
        "我盯着设定看了一遍，开头那句跟「平实克制短句」会不会打架？"
    )
    assert json.loads(consistency[0].payload) == {
        "initiator": "agent",
        "kind": proactive.PROACTIVE_KIND_CONSISTENCY,
        "trigger": proactive.TRIGGER_STYLE_SET,
    }

    events = list_events(db, workspace_id)
    assert [event.type for event in events] == ["agent.message"]
    assert json.loads(events[0].payload) == json.loads(consistency[0].payload)


def test_style_set_reviewer_budget_stops_after_max(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_PROACTIVE_MAX_PER_AGENT", "1")
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    first = runner.invoke(
        app, ["style", "set", workspace_id, "--description", "第一版风格"]
    )
    assert first.exit_code == 0, first.output
    assert "审稿: 风格锚点定了" in first.output

    second = runner.invoke(
        app, ["style", "set", workspace_id, "--description", "第二版风格"]
    )
    assert second.exit_code == 0, second.output
    assert "审稿:" not in second.output

    db = DB(load_settings())
    assert proactive.count_proactive_messages(db, workspace_id, "审稿") == 1


def test_disabled_proactive_suppresses_style_consistency(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("NOVEL_PROACTIVE_ENABLED", "false")
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app, ["style", "set", workspace_id, "--description", "平实克制短句"]
    )
    assert result.exit_code == 0, result.output
    assert "审稿:" not in result.output

    db = DB(load_settings())
    assert list_messages(db, workspace_id) == []
