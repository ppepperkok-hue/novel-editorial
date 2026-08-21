"""CLI end-to-end tests for ``style drift`` (N21 S2)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.structure import KIND_CHAPTER, KIND_VOLUME, create_node
from novel_editorial.core.style import set_style_anchor
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import Draft, DraftVersion, StyleAnchor

runner = CliRunner()

# Chapter 1 baseline: 20 short sentences of length 10, no modifiers/AI words.
BASELINE_TEXT = "一二三四五六七八九十。" * 20
# Chapter 2: 16 shorts + 4 longs (avg 12, short 80%), one style keyword, two
# forbidden words, no modifiers/AI words -> drift 15.
CHAPTER_2_TEXT = (
    "一二三四五六七八九十。" * 16
    + "窒息丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉。"
    + "甲乙丙丁戊己庚辛壬癸微光寅卯辰巳午未申酉。"
    + "克制丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉。"
    + "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉。"
)
# Chapter 3: 20 long sentences (avg 26, short 0%), two modifiers, two AI
# words, two forbidden words -> drift 80.
CHAPTER_3_TEXT = (
    "一二三四五六七八九十甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳。" * 16
    + "窒息窒息五六七八九十甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳。"
    + "一二三四五六七八九十甲乙丙丁戊己庚辛壬癸微光寅卯辰巳。"
    + "静静缓缓五六七八九十甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳。"
    + "宛如不禁五六七八九十甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳。"
)
DESCRIPTION = "冷峻，克制，简洁"
FORBIDDEN_WORDS = "窒息,微光"

FULL_REPORT_LINES = [
    "chapters: 3",
    "baseline: 第一章 雨夜",
    "1 第一章 雨夜: len 10.0 / short 100.0% / mod 0.0 / ai 0.0 / style 0/3 → drift 0",
    "2 第二章 线索: len 12.0 / short 80.0% / mod 0.0 / ai 0.0 / style 1/3 → drift 15",
    "3 第三章 转折: len 26.0 / short 0.0% / mod 3.8 / ai 3.8 / style 0/3 → drift 80",
    "drift trend: 0 / 15 / 80",
    "drifted chapters: 第三章 转折（80）",
    "forbidden hits: 第二章 线索: 2（窒息、微光）",
    "forbidden hits: 第三章 转折: 3（窒息、微光）",
    "verdict: drift detected in 1 chapter",
]


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))


def _create_workspace(tmp_path: Path, *, title: str = "风格漂移之书") -> str:
    result = runner.invoke(app, ["works", "create", title, "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    match = re.search(r"created workspace (\w+):", result.output)
    assert match is not None, result.output
    return match.group(1)


def _db() -> DB:
    return DB(load_settings())


def _write_draft(
    db: DB,
    workspace_id: str,
    *,
    title: str,
    content: str,
    draft_id: str | None = None,
    created_at: datetime | None = None,
) -> str:
    """Insert a draft with one version directly (no LLM involved)."""
    with db.workspace_session(workspace_id) as session:
        draft = Draft(workspace_id=workspace_id, title=title, current_version=1)
        if draft_id is not None:
            draft.id = draft_id
        if created_at is not None:
            draft.created_at = created_at
        session.add(draft)
        session.flush()
        session.add(DraftVersion(draft_id=draft.id, version=1, content=content))
        session.commit()
        return draft.id


def _attach_chapters(
    db: DB,
    workspace_id: str,
    *,
    titles: list[str],
    draft_ids: list[str],
    sort_orders: list[int],
) -> None:
    volume = create_node(db, workspace_id, kind=KIND_VOLUME, title="第一卷")
    for title, draft_id, sort_order in zip(titles, draft_ids, sort_orders, strict=True):
        create_node(
            db,
            workspace_id,
            kind=KIND_CHAPTER,
            title=title,
            parent_id=volume.id,
            draft_id=draft_id,
            sort_order=sort_order,
        )


def test_style_drift_cli_full_report_with_structure(tmp_path: Path) -> None:
    workspace_id = _create_workspace(tmp_path)
    db = _db()
    set_style_anchor(
        db,
        workspace_id,
        description=DESCRIPTION,
        forbidden_words=FORBIDDEN_WORDS,
    )
    first = _write_draft(
        db, workspace_id, title="第一章 雨夜", content=BASELINE_TEXT, draft_id="d1"
    )
    second = _write_draft(
        db, workspace_id, title="第二章 线索", content=CHAPTER_2_TEXT, draft_id="d2"
    )
    third = _write_draft(
        db, workspace_id, title="第三章 转折", content=CHAPTER_3_TEXT, draft_id="d3"
    )
    _attach_chapters(
        db,
        workspace_id,
        titles=["第一章 雨夜", "第二章 线索", "第三章 转折"],
        draft_ids=[first, second, third],
        sort_orders=[0, 1, 2],
    )

    result = runner.invoke(app, ["style", "drift", workspace_id])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == FULL_REPORT_LINES


def test_style_drift_cli_orders_by_created_at_without_structure(
    tmp_path: Path,
) -> None:
    workspace_id = _create_workspace(tmp_path)
    db = _db()
    early = datetime(2026, 1, 1, tzinfo=UTC)
    late = datetime(2026, 1, 2, tzinfo=UTC)
    _write_draft(
        db, workspace_id, title="第三稿", content="夜。", draft_id="c", created_at=late
    )
    _write_draft(
        db, workspace_id, title="  ", content="朝。", draft_id="a", created_at=early
    )
    _write_draft(
        db, workspace_id, title="第二稿", content="午。", draft_id="b", created_at=early
    )

    result = runner.invoke(app, ["style", "drift", workspace_id])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[2].startswith("1 未命名章节:")
    assert lines[3].startswith("2 第二稿:")
    assert lines[4].startswith("3 第三稿:")


def test_style_drift_cli_omits_style_segment_without_keywords(
    tmp_path: Path,
) -> None:
    workspace_id = _create_workspace(tmp_path)
    db = _db()
    _write_draft(
        db, workspace_id, title="第一章", content=BASELINE_TEXT, draft_id="d1"
    )
    _write_draft(
        db, workspace_id, title="第二章", content=CHAPTER_2_TEXT, draft_id="d2"
    )

    result = runner.invoke(app, ["style", "drift", workspace_id])

    assert result.exit_code == 0, result.output
    assert "/ style" not in result.output
    assert "verdict: style stable" in result.output


def test_style_drift_cli_no_chapters_empty_state(tmp_path: Path) -> None:
    workspace_id = _create_workspace(tmp_path)

    result = runner.invoke(app, ["style", "drift", workspace_id])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == ["no chapters"]


def test_style_drift_cli_single_chapter_is_n_a(tmp_path: Path) -> None:
    workspace_id = _create_workspace(tmp_path)
    db = _db()
    _write_draft(
        db, workspace_id, title="第一章", content=BASELINE_TEXT, draft_id="d1"
    )

    result = runner.invoke(app, ["style", "drift", workspace_id])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "chapters: 1",
        "drift: n/a (need at least 2 chapters)",
    ]


def test_style_drift_cli_all_blank_chapters_are_n_a(tmp_path: Path) -> None:
    workspace_id = _create_workspace(tmp_path)
    db = _db()
    _write_draft(db, workspace_id, title="空章一", content="   ", draft_id="d1")
    _write_draft(db, workspace_id, title="空章二", content="……", draft_id="d2")

    result = runner.invoke(app, ["style", "drift", workspace_id])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "chapters: 0",
        "drift: n/a (need at least 2 chapters)",
    ]


def test_style_drift_cli_dangling_structure_chapter_is_skipped(
    tmp_path: Path,
) -> None:
    workspace_id = _create_workspace(tmp_path)
    db = _db()
    first = _write_draft(
        db, workspace_id, title="第一章 雨夜", content="雨夜归乡。", draft_id="d1"
    )
    second = _write_draft(
        db, workspace_id, title="第二章 线索", content="线索浮现。", draft_id="d2"
    )
    _attach_chapters(
        db,
        workspace_id,
        titles=["悬空章", "第一章 雨夜", "第二章 线索"],
        draft_ids=["ghost-draft", first, second],
        sort_orders=[0, 1, 2],
    )

    result = runner.invoke(app, ["style", "drift", workspace_id])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert "skipped chapters: 1" in lines
    first_row = next(line for line in lines if line.startswith("1 第一章 雨夜:"))
    assert lines.index("skipped chapters: 1") < lines.index(first_row)
    assert "悬空章" not in result.output
    assert "verdict: style stable" in result.output


def test_style_drift_cli_missing_workspace_exits_not_found(tmp_path: Path) -> None:
    _create_workspace(tmp_path)

    result = runner.invoke(app, ["style", "drift", "no-such-workspace"])

    assert result.exit_code == 1
    assert "workspace not found" in result.output


def test_style_drift_cli_is_deterministic(tmp_path: Path) -> None:
    workspace_id = _create_workspace(tmp_path)
    db = _db()
    set_style_anchor(
        db,
        workspace_id,
        description=DESCRIPTION,
        forbidden_words=FORBIDDEN_WORDS,
    )
    _write_draft(
        db, workspace_id, title="第一章 雨夜", content=BASELINE_TEXT, draft_id="d1"
    )
    _write_draft(
        db, workspace_id, title="第二章 线索", content=CHAPTER_2_TEXT, draft_id="d2"
    )
    _write_draft(
        db, workspace_id, title="第三章 转折", content=CHAPTER_3_TEXT, draft_id="d3"
    )

    first = runner.invoke(app, ["style", "drift", workspace_id])
    second = runner.invoke(app, ["style", "drift", workspace_id])

    assert first.exit_code == 0, first.output
    assert second.output == first.output


def test_style_drift_cli_is_read_only(tmp_path: Path) -> None:
    workspace_id = _create_workspace(tmp_path)
    db = _db()
    _write_draft(
        db, workspace_id, title="第一章", content=BASELINE_TEXT, draft_id="d1"
    )
    _write_draft(
        db, workspace_id, title="第二章", content=CHAPTER_2_TEXT, draft_id="d2"
    )
    events_before = list_events(db, workspace_id)

    result = runner.invoke(app, ["style", "drift", workspace_id])

    assert result.exit_code == 0, result.output
    assert len(list_events(db, workspace_id)) == len(events_before)
    with db.workspace_session(workspace_id) as session:
        assert session.query(StyleAnchor).filter_by(workspace_id=workspace_id).first() is None
