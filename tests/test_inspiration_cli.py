"""Tests for N15 S2: inspiration CLI command group end-to-end."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app

runner = CliRunner()

SUBCOMMANDS = ("add", "list", "show", "remove")


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))


def _create_workspace(title: str = "灵感CLI书") -> str:
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    workspace_match = re.search(r"created workspace (\w+):", result.output)
    assert workspace_match is not None
    return workspace_match.group(1)


@pytest.mark.parametrize(
    ("args", "label"),
    [
        (["inspiration"], "inspiration"),
        *[
            (["inspiration", command], f"inspiration {command}")
            for command in SUBCOMMANDS
        ],
    ],
    ids=["inspiration", *[f"inspiration {command}" for command in SUBCOMMANDS]],
)
def test_inspiration_group_registered_and_documented(
    args: list[str], label: str
) -> None:
    result = runner.invoke(app, [*args, "--help"])
    assert result.exit_code == 0, f"{label}: {result.output}"


def test_inspiration_end_to_end(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace()

    first = runner.invoke(
        app,
        ["inspiration", "add", workspace_id, "--content", "码头雾气与旧钟", "--kind", "意象"],
    )
    assert first.exit_code == 0, first.output
    first_id = first.output.split()[1]
    assert first.output.strip() == f"added {first_id} [意象] 码头雾气与旧钟"

    second = runner.invoke(
        app,
        [
            "inspiration",
            "add",
            workspace_id,
            "--content",
            "茶馆争吵",
            "--kind",
            "场景",
            "--source",
            "from the DAWN notebook",
        ],
    )
    assert second.exit_code == 0, second.output
    second_id = second.output.split()[1]
    assert second.output.strip() == f"added {second_id} [场景] 茶馆争吵"

    third = runner.invoke(
        app,
        ["inspiration", "add", workspace_id, "--content", "雨夜巷口的猫", "--kind", "意象"],
    )
    assert third.exit_code == 0, third.output
    third_id = third.output.split()[1]
    assert third.output.strip() == f"added {third_id} [意象] 雨夜巷口的猫"

    listed = runner.invoke(app, ["inspiration", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert listed.output.splitlines() == [
        f"{third_id} [意象] 雨夜巷口的猫",
        f"{second_id} [场景] 茶馆争吵",
        f"{first_id} [意象] 码头雾气与旧钟",
    ]

    kind_filtered = runner.invoke(
        app, ["inspiration", "list", workspace_id, "--kind", "意象"]
    )
    assert kind_filtered.exit_code == 0, kind_filtered.output
    assert kind_filtered.output.splitlines() == [
        f"{third_id} [意象] 雨夜巷口的猫",
        f"{first_id} [意象] 码头雾气与旧钟",
    ]

    keyword_filtered = runner.invoke(
        app, ["inspiration", "list", workspace_id, "--keyword", "DAWN"]
    )
    assert keyword_filtered.exit_code == 0, keyword_filtered.output
    assert keyword_filtered.output.splitlines() == [
        f"{second_id} [场景] 茶馆争吵"
    ]

    keyword_empty = runner.invoke(
        app, ["inspiration", "list", workspace_id, "--keyword", "不存在的词"]
    )
    assert keyword_empty.exit_code == 0, keyword_empty.output
    assert keyword_empty.output.strip() == "no inspirations"

    shown = runner.invoke(app, ["inspiration", "show", workspace_id, first_id])
    assert shown.exit_code == 0, shown.output
    assert shown.output.splitlines() == [
        "kind: 意象",
        "content: 码头雾气与旧钟",
        "source: (empty)",
    ]

    shown_with_source = runner.invoke(
        app, ["inspiration", "show", workspace_id, second_id]
    )
    assert shown_with_source.exit_code == 0, shown_with_source.output
    assert shown_with_source.output.splitlines() == [
        "kind: 场景",
        "content: 茶馆争吵",
        "source: from the DAWN notebook",
    ]

    removed = runner.invoke(
        app, ["inspiration", "remove", workspace_id, third_id]
    )
    assert removed.exit_code == 0, removed.output
    assert removed.output.strip() == f"removed {third_id} [意象]"

    after_remove = runner.invoke(app, ["inspiration", "list", workspace_id])
    assert after_remove.exit_code == 0, after_remove.output
    assert third_id not in after_remove.output
    assert after_remove.output.splitlines() == [
        f"{second_id} [场景] 茶馆争吵",
        f"{first_id} [意象] 码头雾气与旧钟",
    ]

    events = runner.invoke(app, ["events", "list", workspace_id])
    assert events.exit_code == 0, events.output
    assert events.output.count('"kind": "inspiration_created"') == 3
    assert events.output.count('"kind": "inspiration_removed"') == 1
    assert '"inspiration_id":' in events.output


def test_inspiration_exit_codes(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace()

    missing_workspace = runner.invoke(
        app, ["inspiration", "add", "f" * 32, "--content", "无主灵感"]
    )
    assert missing_workspace.exit_code == 1
    assert "workspace not found" in missing_workspace.output

    missing_inspiration = runner.invoke(
        app, ["inspiration", "show", workspace_id, "a" * 32]
    )
    assert missing_inspiration.exit_code == 1
    assert "inspiration not found" in missing_inspiration.output

    missing_remove = runner.invoke(
        app, ["inspiration", "remove", workspace_id, "b" * 32]
    )
    assert missing_remove.exit_code == 1
    assert "inspiration not found" in missing_remove.output

    empty_content = runner.invoke(
        app, ["inspiration", "add", workspace_id, "--content", ""]
    )
    assert empty_content.exit_code == 2
    assert "must not be empty" in empty_content.output


def test_inspiration_add_dash_content(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace()
    content = "- 破折号开头"

    added = runner.invoke(
        app, ["inspiration", "add", workspace_id, "--content", content]
    )
    assert added.exit_code == 0, added.output
    added_id = added.output.split()[1]
    assert added.output.strip() == f"added {added_id} [灵感] {content}"

    listed = runner.invoke(app, ["inspiration", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert listed.output.splitlines() == [f"{added_id} [灵感] {content}"]
