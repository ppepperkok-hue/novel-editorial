"""Tests for N13 J2: structure CLI command group end-to-end."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.llm.client import MockLLMClient

runner = CliRunner()


def _create_workspace(
    tmp_path: Path, monkeypatch, title: str = "结构CLI书"
) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _node_id(result_output: str) -> str:
    return result_output.split()[1]


def test_structure_add_list_rename_move_remove_status(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    add_volume = runner.invoke(
        app, ["structure", "add", workspace_id, "volume", "第一卷"]
    )
    assert add_volume.exit_code == 0, add_volume.output
    volume_id = _node_id(add_volume.output)
    assert add_volume.output.strip() == f"created {volume_id} volume 第一卷"

    add_chapter = runner.invoke(
        app,
        ["structure", "add", workspace_id, "章", "第一章", "--parent", volume_id],
    )
    assert add_chapter.exit_code == 0, add_chapter.output
    chapter_id = _node_id(add_chapter.output)
    assert add_chapter.output.strip() == f"created {chapter_id} chapter 第一章"

    add_section = runner.invoke(
        app,
        ["structure", "add", workspace_id, "section", "第一节", "--parent", chapter_id],
    )
    assert add_section.exit_code == 0, add_section.output
    section_id = _node_id(add_section.output)

    listed = runner.invoke(app, ["structure", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    lines = listed.output.splitlines()
    assert lines == [
        f"[卷] 第一卷（{volume_id}）",
        f"  [章] 第一章（{chapter_id}）",
        f"    [篇目] 第一节（{section_id}）",
    ]

    renamed = runner.invoke(
        app, ["structure", "rename", workspace_id, chapter_id, "新第一章"]
    )
    assert renamed.exit_code == 0, renamed.output
    assert renamed.output.strip() == f"renamed {chapter_id}"

    moved = runner.invoke(
        app, ["structure", "move", workspace_id, chapter_id, "--root"]
    )
    assert moved.exit_code == 0, moved.output
    assert moved.output.strip() == f"moved {chapter_id}"
    listed = runner.invoke(app, ["structure", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert listed.output.splitlines() == [
        f"[卷] 第一卷（{volume_id}）",
        f"[章] 新第一章（{chapter_id}）",
        f"  [篇目] 第一节（{section_id}）",
    ]

    moved_back = runner.invoke(
        app,
        [
            "structure",
            "move",
            workspace_id,
            chapter_id,
            "--parent",
            volume_id,
            "--order",
            "1",
        ],
    )
    assert moved_back.exit_code == 0, moved_back.output
    assert moved_back.output.strip() == f"moved {chapter_id}"

    status = runner.invoke(
        app, ["structure", "status", workspace_id, chapter_id, "completed"]
    )
    assert status.exit_code == 0, status.output
    assert status.output.strip() == f"status updated: {chapter_id} completed"
    listed = runner.invoke(app, ["structure", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert f"  [章] 新第一章（{chapter_id}） [已完成]" in listed.output

    removed = runner.invoke(app, ["structure", "remove", workspace_id, volume_id])
    assert removed.exit_code == 0, removed.output
    assert removed.output.strip() == "removed 3 node(s)"
    empty = runner.invoke(app, ["structure", "list", workspace_id])
    assert empty.exit_code == 0, empty.output
    assert empty.output.strip() == "no structure"


def test_structure_list_shows_attached_draft_title(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )
    generated = runner.invoke(
        app, ["draft", "generate", workspace_id, "--title", "第一章草稿"]
    )
    assert generated.exit_code == 0, generated.output
    draft_id = _node_id(generated.output)

    added = runner.invoke(
        app,
        ["structure", "add", workspace_id, "chapter", "第一章", "--draft", draft_id],
    )
    assert added.exit_code == 0, added.output
    node_id = _node_id(added.output)

    listed = runner.invoke(app, ["structure", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert f"[章] 第一章（{node_id}） 第一章草稿" in listed.output


def test_structure_add_invalid_kind_and_missing_parent(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    invalid = runner.invoke(app, ["structure", "add", workspace_id, "book", "书"])
    assert invalid.exit_code == 2
    assert "invalid kind" in invalid.output

    missing = runner.invoke(
        app,
        ["structure", "add", workspace_id, "chapter", "孤儿", "--parent", "missing"],
    )
    assert missing.exit_code == 1
    assert "structure node not found" in missing.output

    unknown = runner.invoke(app, ["structure", "list", "does-not-exist"])
    assert unknown.exit_code == 1
    assert "workspace not found" in unknown.output


def test_structure_add_invalid_hierarchy(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    add_chapter = runner.invoke(
        app, ["structure", "add", workspace_id, "chapter", "章"]
    )
    chapter_id = _node_id(add_chapter.output)

    invalid = runner.invoke(
        app,
        ["structure", "add", workspace_id, "volume", "卷", "--parent", chapter_id],
    )
    assert invalid.exit_code == 2
    assert "cannot have a parent" in invalid.output


def test_structure_add_cross_workspace_parent_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")
    add_volume = runner.invoke(
        app, ["structure", "add", workspace_a, "volume", "甲卷"]
    )
    volume_id = _node_id(add_volume.output)

    cross = runner.invoke(
        app,
        ["structure", "add", workspace_b, "chapter", "跨书", "--parent", volume_id],
    )
    assert cross.exit_code == 1
    assert "structure node not found" in cross.output


def test_structure_move_cycle_and_flag_conflict_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    volume_id = _node_id(
        runner.invoke(app, ["structure", "add", workspace_id, "volume", "卷"]).output
    )
    chapter_id = _node_id(
        runner.invoke(
            app,
            ["structure", "add", workspace_id, "chapter", "章", "--parent", volume_id],
        ).output
    )
    section_id = _node_id(
        runner.invoke(
            app,
            ["structure", "add", workspace_id, "section", "节", "--parent", chapter_id],
        ).output
    )

    cycle = runner.invoke(
        app, ["structure", "move", workspace_id, volume_id, "--parent", section_id]
    )
    assert cycle.exit_code == 2
    assert "itself or its own subtree" in cycle.output

    conflict = runner.invoke(
        app,
        [
            "structure",
            "move",
            workspace_id,
            volume_id,
            "--parent",
            section_id,
            "--root",
        ],
    )
    assert conflict.exit_code == 2
    assert "mutually exclusive" in conflict.output


def test_structure_status_three_states_and_invalid(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    node_id = _node_id(
        runner.invoke(
            app, ["structure", "add", workspace_id, "chapter", "章"]
        ).output
    )
    for status in ("writing", "completed", "shelved", "创作中"):
        result = runner.invoke(
            app, ["structure", "status", workspace_id, node_id, status]
        )
        assert result.exit_code == 0, result.output
        canonical = "writing" if status == "创作中" else status
        assert result.output.strip() == f"status updated: {node_id} {canonical}"

    invalid = runner.invoke(
        app, ["structure", "status", workspace_id, node_id, "done"]
    )
    assert invalid.exit_code == 2
    assert "invalid status" in invalid.output


def test_end_to_end_structure_outline_status_visible_in_works_show(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )
    generated = runner.invoke(
        app, ["draft", "generate", workspace_id, "--title", "第一章"]
    )
    assert generated.exit_code == 0, generated.output
    draft_id = _node_id(generated.output)

    volume_id = _node_id(
        runner.invoke(
            app, ["structure", "add", workspace_id, "volume", "第一卷"]
        ).output
    )
    chapter_id = _node_id(
        runner.invoke(
            app,
            [
                "structure",
                "add",
                workspace_id,
                "chapter",
                "第一章",
                "--parent",
                volume_id,
                "--draft",
                draft_id,
            ],
        ).output
    )

    created = runner.invoke(
        app,
        ["outline", "create", workspace_id, "--content", "楔子：雨夜车站", "--actor", "作者"],
    )
    assert created.exit_code == 0, created.output
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
        ],
    )
    assert revised.exit_code == 0, revised.output

    status = runner.invoke(app, ["works", "status", workspace_id, "completed"])
    assert status.exit_code == 0, status.output

    shown = runner.invoke(app, ["works", "show", workspace_id])
    assert shown.exit_code == 0, shown.output
    assert "状态: 已完成" in shown.output
    assert f"[卷] 第一卷（{volume_id}）" in shown.output
    assert f"  [章] 第一章（{chapter_id}） 第一章" in shown.output

    packed = runner.invoke(app, ["memory", "pack", workspace_id])
    assert packed.exit_code == 0, packed.output
    assert "章纲：楔子：雨夜车站，钟停十一点" in packed.output
