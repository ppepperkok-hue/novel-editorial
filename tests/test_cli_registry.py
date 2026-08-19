"""CLI command registry: every group and subcommand must stay callable after the split."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app

runner = CliRunner()

TOP_LEVEL_COMMANDS = ("init", "health", "version", "demo", "log", "inspect")

SUBCOMMANDS = {
    "works": ("create", "list", "show"),
    "agents": ("add", "list", "show", "edit"),
    "behavior": ("timeline", "show"),
    "talk": ("send", "list", "delegate", "discuss"),
    "style": ("set", "show"),
    "memory": (
        "pack",
        "view",
        "search",
        "note",
        "notes",
        "delete",
        "decay",
        "remember",
        "reindex",
        "archive",
        "restore",
    ),
    "draft": ("generate", "revise", "list", "show", "diff"),
    "review": ("add", "list"),
    "decision": ("list", "pending", "accept", "reject", "note"),
    "quality": ("check", "explain"),
    "plot": ("plant", "list", "recover"),
    "setting": ("add", "list", "show", "revise", "history", "check", "impact"),
    "structure": ("add", "list", "rename", "move", "remove", "status"),
    "outline": ("create", "revise", "show", "history"),
    "events": ("list", "watch"),
}

HELP_CASES: list[tuple[list[str], str]] = [
    *[([command], command) for command in TOP_LEVEL_COMMANDS],
    *[
        ([group, command], f"{group} {command}")
        for group, commands in SUBCOMMANDS.items()
        for command in commands
    ],
]


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))


@pytest.mark.parametrize(
    ("args", "label"),
    HELP_CASES,
    ids=[label for _, label in HELP_CASES],
)
def test_every_command_registered_and_documented(args: list[str], label: str) -> None:
    result = runner.invoke(app, [*args, "--help"])
    assert result.exit_code == 0, f"{label}: {result.output}"


@pytest.mark.smoke
def test_representative_commands_run() -> None:
    create = runner.invoke(app, ["works", "create", "注册测试", "--genre", "网文"])
    assert create.exit_code == 0, create.output
    workspace_match = re.search(r"created workspace (\w+):", create.output)
    assert workspace_match is not None
    workspace_id = workspace_match.group(1)

    generate = runner.invoke(app, ["draft", "generate", workspace_id])
    assert generate.exit_code == 0, generate.output
    draft_match = re.search(r"draft (\w+)", generate.output)
    assert draft_match is not None
    draft_id = draft_match.group(1)

    cases: list[tuple[list[str], str]] = [
        (["health"], "health"),
        (["version"], "version"),
        (["works", "show", workspace_id], "works show"),
        (["agents", "show", workspace_id], "agents show"),
        (["talk", "list", workspace_id], "talk list"),
        (
            [
                "talk",
                "discuss",
                workspace_id,
                "--topic",
                "主角动机要不要改",
                "--with",
                "写手,审稿",
                "--outcome",
                "先不改，加一场揭示戏",
            ],
            "talk discuss",
        ),
        (
            [
                "talk",
                "delegate",
                workspace_id,
                "审稿",
                "--as",
                "写手",
                "--task",
                "帮我校一遍逻辑",
            ],
            "talk delegate",
        ),
        (["style", "show", workspace_id], "style show"),
        (["memory", "notes", workspace_id], "memory notes"),
        (["draft", "list", workspace_id], "draft list"),
        (["behavior", "timeline", workspace_id], "behavior timeline"),
        (["behavior", "show", workspace_id], "behavior show"),
        (["review", "list", draft_id], "review list"),
        (["decision", "pending", workspace_id], "decision pending"),
        (["quality", "check", draft_id], "quality check"),
        (["plot", "list", workspace_id], "plot list"),
        (["events", "list", workspace_id], "events list"),
    ]
    for args, label in cases:
        result = runner.invoke(app, args)
        assert result.exit_code == 0, f"{label}: {result.output}"

    behavior_show = runner.invoke(app, ["behavior", "show", workspace_id])
    assert behavior_show.exit_code == 0, behavior_show.output
    assert "委托被接受" in behavior_show.output
    assert "可协作" in behavior_show.output
    behavior_timeline = runner.invoke(app, ["behavior", "timeline", workspace_id])
    assert behavior_timeline.exit_code == 0, behavior_timeline.output
    assert "[relationship]" in behavior_timeline.output
    assert "[impression]" in behavior_timeline.output
