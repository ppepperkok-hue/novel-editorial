"""Behavior CLI: timeline/show visibility, agents show summaries, and the e2e flow."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.behavior import record_behavior_entry
from novel_editorial.core.chat import get_agent
from novel_editorial.core.config import load_settings
from novel_editorial.store.db import DB
from novel_editorial.store.models import AgentRole

runner = CliRunner()


class _AdvancingDateTime(datetime):
    """A frozen clock that ticks forward one second per now() call."""

    ticks = 0

    @classmethod
    def now(cls, tz=None) -> datetime:
        cls.ticks += 1
        return datetime(2026, 1, 2, 3, 4, 0, tzinfo=UTC) + timedelta(seconds=cls.ticks)


def _freeze_advancing_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("novel_editorial.store.models.datetime", _AdvancingDateTime)


def _create_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "可见之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    match = re.search(r"created workspace (\w+):", result.output)
    assert match is not None
    return match.group(1)


def _agent_id(workspace_id: str, role: str) -> str:
    return get_agent(DB(load_settings()), workspace_id, role).id


def _talk(workspace_id: str, content: str) -> None:
    result = runner.invoke(app, ["talk", "send", workspace_id, content])
    assert result.exit_code == 0, result.output


def _without_time(line: str) -> str:
    return line.split(" ", 1)[1]


def test_timeline_empty_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["behavior", "timeline", workspace_id])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "no behavior traces yet"


def test_timeline_replays_refusal_then_override_oldest_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _talk(workspace_id, "@写手 这段按违背人设写")
    _talk(workspace_id, "@写手 以老板身份我拍板，就按违背人设写")

    result = runner.invoke(app, ["behavior", "timeline", workspace_id])
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        when = line.split(" ", 1)[0]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", when)
    assert [_without_time(line) for line in lines] == [
        (
            "[viewpoint] 写手 -> writer_portrayal: 拒绝了违背立场的指令"
            " | 无 -> 坚持该立场 | source=refusal:writer_portrayal"
        ),
        (
            "[viewpoint] 写手 -> writer_portrayal: 作者推翻后调整"
            " | 坚持该立场 -> 按作者决定执行 | source=override:writer_portrayal"
        ),
        "[relationship] 写手 -> 作者: 作者拍板优先 | source=override:writer_portrayal",
    ]


def test_timeline_agent_kind_and_limit_filters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _freeze_advancing_clock(monkeypatch)
    db = DB(load_settings())
    writer_id = _agent_id(workspace_id, AgentRole.WRITER)
    editor_id = _agent_id(workspace_id, AgentRole.EDITOR)
    record_behavior_entry(
        db, workspace_id, agent_id=writer_id, kind="viewpoint", target="rule_a", summary="v0"
    )
    record_behavior_entry(
        db, workspace_id, agent_id=writer_id, kind="impression", target="责编", summary="i0"
    )
    record_behavior_entry(
        db, workspace_id, agent_id=editor_id, kind="impression", target="写手", summary="e0"
    )
    record_behavior_entry(
        db, workspace_id, agent_id=writer_id, kind="viewpoint", target="rule_a", summary="v1"
    )

    by_agent = runner.invoke(app, ["behavior", "timeline", workspace_id, "--agent", "写手"])
    assert by_agent.exit_code == 0, by_agent.output
    assert [_without_time(line) for line in by_agent.output.strip().splitlines()] == [
        "[viewpoint] 写手 -> rule_a: v0",
        "[impression] 写手 -> 责编: i0",
        "[viewpoint] 写手 -> rule_a: v1",
    ]

    by_editor = runner.invoke(app, ["behavior", "timeline", workspace_id, "--agent", "责编"])
    assert by_editor.exit_code == 0, by_editor.output
    assert [_without_time(line) for line in by_editor.output.strip().splitlines()] == [
        "[impression] 责编 -> 写手: e0",
    ]

    by_kind = runner.invoke(app, ["behavior", "timeline", workspace_id, "--kind", "viewpoint"])
    assert by_kind.exit_code == 0, by_kind.output
    assert [_without_time(line) for line in by_kind.output.strip().splitlines()] == [
        "[viewpoint] 写手 -> rule_a: v0",
        "[viewpoint] 写手 -> rule_a: v1",
    ]

    limited = runner.invoke(app, ["behavior", "timeline", workspace_id, "--limit", "2"])
    assert limited.exit_code == 0, limited.output
    assert [_without_time(line) for line in limited.output.strip().splitlines()] == [
        "[viewpoint] 写手 -> rule_a: v0",
        "[impression] 写手 -> 责编: i0",
    ]

    crossed = runner.invoke(
        app,
        [
            "behavior",
            "timeline",
            workspace_id,
            "--kind",
            "impression",
            "--kind",
            "viewpoint",
        ],
    )
    assert crossed.exit_code == 0, crossed.output
    assert [_without_time(line) for line in crossed.output.strip().splitlines()] == [
        "[viewpoint] 写手 -> rule_a: v0",
        "[impression] 写手 -> 责编: i0",
        "[impression] 责编 -> 写手: e0",
        "[viewpoint] 写手 -> rule_a: v1",
    ]


def test_timeline_multi_kind_replays_insertion_order_with_frozen_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    fixed_time = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None) -> datetime:
            return fixed_time

    monkeypatch.setattr("novel_editorial.store.models.datetime", FrozenDateTime)
    db = DB(load_settings())
    writer_id = _agent_id(workspace_id, AgentRole.WRITER)
    record_behavior_entry(
        db, workspace_id, agent_id=writer_id, kind="viewpoint", target="rule_a", summary="v0"
    )
    record_behavior_entry(
        db, workspace_id, agent_id=writer_id, kind="impression", target="责编", summary="i0"
    )
    record_behavior_entry(
        db, workspace_id, agent_id=writer_id, kind="relationship", target="作者", summary="r0"
    )

    result = runner.invoke(
        app,
        [
            "behavior",
            "timeline",
            workspace_id,
            "--agent",
            "写手",
            "--kind",
            "relationship",
            "--kind",
            "impression",
            "--kind",
            "viewpoint",
        ],
    )
    assert result.exit_code == 0, result.output
    assert [_without_time(line) for line in result.output.strip().splitlines()] == [
        "[viewpoint] 写手 -> rule_a: v0",
        "[impression] 写手 -> 责编: i0",
        "[relationship] 写手 -> 作者: r0",
    ]


def test_timeline_unknown_agent_is_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["behavior", "timeline", workspace_id, "--agent", "主编大人"])
    assert result.exit_code == 2
    assert "unknown agent: 主编大人" in result.output


def test_timeline_unknown_kind_is_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["behavior", "timeline", workspace_id, "--kind", "mood"])
    assert result.exit_code == 2
    assert "unknown behavior kind: mood" in result.output


def test_show_groups_by_agent_created_at_and_sorts_by_kind_then_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer_id = _agent_id(workspace_id, AgentRole.WRITER)
    editor_id = _agent_id(workspace_id, AgentRole.EDITOR)
    record_behavior_entry(
        db, workspace_id, agent_id=writer_id, kind="viewpoint", target="rule_a", summary="观点"
    )
    record_behavior_entry(
        db, workspace_id, agent_id=writer_id, kind="impression", target="责编", summary="盯节奏"
    )
    record_behavior_entry(
        db, workspace_id, agent_id=writer_id, kind="impression", target="总编", summary="结构稳"
    )
    record_behavior_entry(
        db,
        workspace_id,
        agent_id=writer_id,
        kind="relationship",
        target="作者",
        summary="稿子被认可",
    )
    record_behavior_entry(
        db, workspace_id, agent_id=editor_id, kind="impression", target="写手", summary="盯逻辑"
    )

    result = runner.invoke(app, ["behavior", "show", workspace_id])
    assert result.exit_code == 0, result.output
    assert result.output.strip().splitlines() == [
        "[责编]",
        "  impression -> 写手: 盯逻辑",
        "[写手]",
        "  impression -> 总编: 结构稳",
        "  impression -> 责编: 盯节奏",
        "  relationship -> 作者: 稿子被认可",
        "  viewpoint -> rule_a: 观点",
    ]


def test_show_keeps_latest_entry_per_group_and_renders_change_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer_id = _agent_id(workspace_id, AgentRole.WRITER)
    record_behavior_entry(
        db,
        workspace_id,
        agent_id=writer_id,
        kind="viewpoint",
        target="rule_a",
        summary="第一次拒绝",
        after_value="坚持该立场",
    )
    record_behavior_entry(
        db,
        workspace_id,
        agent_id=writer_id,
        kind="viewpoint",
        target="rule_a",
        summary="作者推翻后调整",
        before_value="坚持该立场",
        after_value="按作者决定执行",
    )

    shown = runner.invoke(app, ["behavior", "show", workspace_id])
    assert shown.exit_code == 0, shown.output
    assert shown.output.strip().splitlines() == [
        "[写手]",
        "  viewpoint -> rule_a: 作者推翻后调整（坚持该立场 -> 按作者决定执行）",
    ]

    timeline = runner.invoke(app, ["behavior", "timeline", workspace_id])
    assert timeline.exit_code == 0, timeline.output
    assert [_without_time(line) for line in timeline.output.strip().splitlines()] == [
        "[viewpoint] 写手 -> rule_a: 第一次拒绝 | 无 -> 坚持该立场",
        "[viewpoint] 写手 -> rule_a: 作者推翻后调整 | 坚持该立场 -> 按作者决定执行",
    ]


def test_show_empty_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["behavior", "show", workspace_id])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "no behavior traces yet"


def test_agents_show_appends_impression_and_relationship_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer_id = _agent_id(workspace_id, AgentRole.WRITER)
    record_behavior_entry(
        db,
        workspace_id,
        agent_id=writer_id,
        kind="relationship",
        target="作者",
        summary="稿子被认可",
    )
    record_behavior_entry(
        db, workspace_id, agent_id=writer_id, kind="impression", target="责编", summary="盯节奏"
    )
    record_behavior_entry(
        db, workspace_id, agent_id=writer_id, kind="viewpoint", target="rule_a", summary="观点"
    )

    result = runner.invoke(app, ["agents", "show", workspace_id])
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    assert lines.count("  印象与关系:") == 1
    private_idx = lines.index("  私心: 想写出让读者记住某个瞬间的句子。")
    assert lines[private_idx + 1 : private_idx + 4] == [
        "  印象与关系:",
        "    impression -> 责编: 盯节奏",
        "    relationship -> 作者: 稿子被认可",
    ]
    for label in ("性格", "立场", "价值观", "审美", "情绪基线", "工作习惯", "弱点", "人际预设"):
        assert label in result.output


def test_agents_show_without_entries_keeps_profiles_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["agents", "show", workspace_id])
    assert result.exit_code == 0, result.output
    assert "印象与关系" not in result.output
    for label in (
        "性格",
        "立场",
        "价值观",
        "审美",
        "情绪基线",
        "工作习惯",
        "弱点",
        "人际预设",
        "私心",
    ):
        assert label in result.output


def test_end_to_end_refusal_then_override_visible_in_timeline_and_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _talk(workspace_id, "@写手 这段按违背人设写")
    _talk(workspace_id, "@写手 以老板身份我拍板，就按违背人设写")

    timeline = runner.invoke(app, ["behavior", "timeline", workspace_id])
    assert timeline.exit_code == 0, timeline.output
    timeline_lines = timeline.output.strip().splitlines()
    assert len(timeline_lines) == 3
    assert "[viewpoint]" in timeline_lines[0]
    assert "[viewpoint]" in timeline_lines[1]
    assert "[relationship]" in timeline_lines[2]
    assert "坚持该立场 -> 按作者决定执行" in timeline_lines[1]

    shown = runner.invoke(app, ["behavior", "show", workspace_id])
    assert shown.exit_code == 0, shown.output
    assert shown.output.strip().splitlines() == [
        "[写手]",
        "  relationship -> 作者: 作者拍板优先",
        "  viewpoint -> writer_portrayal: 作者推翻后调整（坚持该立场 -> 按作者决定执行）",
    ]
