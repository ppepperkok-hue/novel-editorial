"""Style drift detection service tests (N21 S1)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.structure import KIND_CHAPTER, KIND_VOLUME, create_node
from novel_editorial.core.style import set_style_anchor
from novel_editorial.core.style_drift import compute_style_drift
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import Draft, DraftVersion, StyleAnchor

runner = CliRunner()

# Baseline: 45 sentences of length 6, one modifier (静静) and one AI word (宛如).
BASELINE_TEXT = "静静宛如的吧。" * 45
# Chapter A: 10 short sentences (length 2) + 9 keyword longs + 1 plain long;
# avg 9, short ratio 0.5, same modifier/AI density ratio as baseline, 9/20 style hits.
CHAPTER_A_TEXT = (
    "啊吧。" * 10
    + "".join(
        f"静静宛如{kw}一二三四五六七八九十。"
        for kw in ("甲一", "甲二", "甲三", "甲四", "甲五", "甲六", "甲七", "甲八", "甲九")
    )
    + "静静宛如一二三四五六七八九十ab。"
)
# Chapter B: same as A but 10/20 style hits (all 甲* keywords present).
CHAPTER_B_TEXT = (
    "啊吧。" * 10
    + "".join(
        f"静静宛如{kw}一二三四五六七八九十。"
        for kw in ("甲一", "甲二", "甲三", "甲四", "甲五", "甲六", "甲七", "甲八", "甲九", "甲十")
    )
)
TWENTY_KEYWORDS = "，".join(
    ("甲一", "甲二", "甲三", "甲四", "甲五", "甲六", "甲七", "甲八", "甲九", "甲十")
    + ("乙一", "乙二", "乙三", "乙四", "乙五", "乙六", "乙七", "乙八", "乙九", "乙十")
)


def _create_workspace(
    tmp_path: Path, monkeypatch, *, title: str = "风格漂移之书"
) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


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


def test_structure_order_is_parent_first_and_unattached_drafts_ignored(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    first = _write_draft(
        db, workspace_id, title="草稿一", content="雨夜归乡。", draft_id="d1"
    )
    second = _write_draft(
        db, workspace_id, title="草稿二", content="线索浮现。", draft_id="d2"
    )
    third = _write_draft(
        db, workspace_id, title="草稿三", content="转折发生。", draft_id="d3"
    )
    _write_draft(
        db, workspace_id, title="游离草稿", content="不该出现。", draft_id="d4"
    )
    volume = create_node(db, workspace_id, kind=KIND_VOLUME, title="第一卷")
    create_node(
        db,
        workspace_id,
        kind=KIND_CHAPTER,
        title="第一章 雨夜",
        parent_id=volume.id,
        draft_id=first,
        sort_order=0,
    )
    create_node(
        db,
        workspace_id,
        kind=KIND_CHAPTER,
        title="第三章 转折",
        parent_id=volume.id,
        draft_id=third,
        sort_order=2,
    )
    create_node(
        db,
        workspace_id,
        kind=KIND_CHAPTER,
        title="第二章 线索",
        parent_id=volume.id,
        draft_id=second,
        sort_order=1,
    )

    report = compute_style_drift(db, workspace_id)

    assert [chapter.title for chapter in report.chapters] == [
        "第一章 雨夜",
        "第二章 线索",
        "第三章 转折",
    ]
    assert [chapter.draft_id for chapter in report.chapters] == [first, second, third]
    assert [chapter.index for chapter in report.chapters] == [1, 2, 3]
    assert report.baseline_title == "第一章 雨夜"
    assert all(chapter.title != "游离草稿" for chapter in report.chapters)


def test_dangling_structure_draft_is_skipped(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    first = _write_draft(
        db, workspace_id, title="第一章 雨夜", content="雨夜归乡。", draft_id="d1"
    )
    second = _write_draft(
        db, workspace_id, title="第二章 线索", content="线索浮现。", draft_id="d2"
    )
    volume = create_node(db, workspace_id, kind=KIND_VOLUME, title="第一卷")
    create_node(
        db,
        workspace_id,
        kind=KIND_CHAPTER,
        title="悬空章",
        parent_id=volume.id,
        draft_id="ghost-draft",
        sort_order=0,
    )
    create_node(
        db,
        workspace_id,
        kind=KIND_CHAPTER,
        title="第一章 雨夜",
        parent_id=volume.id,
        draft_id=first,
        sort_order=1,
    )
    create_node(
        db,
        workspace_id,
        kind=KIND_CHAPTER,
        title="第二章 线索",
        parent_id=volume.id,
        draft_id=second,
        sort_order=2,
    )

    report = compute_style_drift(db, workspace_id)

    assert [chapter.title for chapter in report.chapters] == [
        "第一章 雨夜",
        "第二章 线索",
    ]
    assert report.skipped == 1
    assert report.baseline_title == "第一章 雨夜"
    assert report.drifted == []
    assert report.verdict == "style stable"


def test_fallback_orders_drafts_by_created_at_then_id(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
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

    report = compute_style_drift(db, workspace_id)

    assert [chapter.title for chapter in report.chapters] == [
        "未命名章节",
        "第二稿",
        "第三稿",
    ]
    assert [chapter.draft_id for chapter in report.chapters] == ["a", "b", "c"]


def test_dimensions_and_boundary_49_is_not_drifted(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    set_style_anchor(
        db,
        workspace_id,
        description=TWENTY_KEYWORDS,
        forbidden_words="璀璨, 宛如，璀璨",
    )
    _write_draft(
        db, workspace_id, title="第一章", content=BASELINE_TEXT, draft_id="d1"
    )
    _write_draft(
        db, workspace_id, title="第二章", content=CHAPTER_A_TEXT, draft_id="d2"
    )

    report = compute_style_drift(db, workspace_id)

    first, second = report.chapters
    assert first.avg_sentence_len == pytest.approx(6.0)
    assert first.short_sentence_ratio == pytest.approx(1.0)
    assert first.modifier_per_1000 == pytest.approx(1000 / 270)
    assert first.ai_words_per_1000 == pytest.approx(1000 / 270)
    assert first.style_hits == 0
    assert first.style_total == 20
    assert first.forbidden_hits == 45
    assert first.drift_score == 0
    assert first.drifted is False

    assert second.avg_sentence_len == pytest.approx(9.0)
    assert second.short_sentence_ratio == pytest.approx(0.5)
    assert second.modifier_per_1000 == pytest.approx(1000 / 180)
    assert second.ai_words_per_1000 == pytest.approx(1000 / 180)
    assert second.style_hits == 9
    assert second.style_total == 20
    assert second.forbidden_hits == 10
    assert second.drift_score == 49
    assert second.drifted is False

    assert report.baseline_title == "第一章"
    assert report.skipped == 0
    assert report.threshold == 50
    assert report.drifted == []
    assert report.verdict == "style stable"


def test_boundary_50_is_drifted(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    set_style_anchor(db, workspace_id, description=TWENTY_KEYWORDS, forbidden_words="")
    _write_draft(
        db, workspace_id, title="第一章", content=BASELINE_TEXT, draft_id="d1"
    )
    _write_draft(
        db, workspace_id, title="第二章", content=CHAPTER_B_TEXT, draft_id="d2"
    )

    report = compute_style_drift(db, workspace_id)

    second = report.chapters[1]
    assert second.style_hits == 10
    assert second.style_total == 20
    assert second.drift_score == 50
    assert second.drifted is True
    assert report.drifted == [second]
    assert report.verdict == "drift detected in 1 chapter"


def test_no_style_keywords_excludes_dimension_and_renormalizes(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    _write_draft(
        db, workspace_id, title="第一章", content=BASELINE_TEXT, draft_id="d1"
    )
    _write_draft(
        db, workspace_id, title="第二章", content=CHAPTER_A_TEXT, draft_id="d2"
    )

    report = compute_style_drift(db, workspace_id)

    assert all(chapter.style_hits is None for chapter in report.chapters)
    assert all(chapter.style_total == 0 for chapter in report.chapters)
    # Four dimensions average 0.5 -> 50; the fifth style dimension would make it 49.
    assert report.chapters[1].drift_score == 50
    assert report.chapters[1].drifted is True
    assert report.verdict == "drift detected in 1 chapter"
    with db.workspace_session(workspace_id) as session:
        assert session.query(StyleAnchor).filter_by(workspace_id=workspace_id).first() is None


def test_forbidden_words_split_dedupe_and_count(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    set_style_anchor(db, workspace_id, description="", forbidden_words="璀璨， 宛如,璀璨")
    text = "璀璨星光洒落。宛如薄纱，璀璨依旧。"
    _write_draft(db, workspace_id, title="第一章", content=text, draft_id="d1")
    _write_draft(db, workspace_id, title="第二章", content=text, draft_id="d2")

    report = compute_style_drift(db, workspace_id)

    assert [chapter.forbidden_hits for chapter in report.chapters] == [3, 3]
    assert report.chapters[0].drift_score == 0
    assert report.chapters[1].drift_score == 0
    assert report.verdict == "style stable"


def test_empty_content_chapter_is_skipped(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    _write_draft(db, workspace_id, title="空章", content="   \n\t", draft_id="d1")
    _write_draft(db, workspace_id, title="正常章", content="雨夜归乡。", draft_id="d2")

    report = compute_style_drift(db, workspace_id)

    assert [chapter.title for chapter in report.chapters] == ["正常章"]
    assert report.skipped == 1
    assert report.baseline_title == "正常章"
    assert report.drifted == []
    assert report.verdict == "need at least 2 chapters"


def test_no_drafts_yields_no_chapters(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    report = compute_style_drift(db, workspace_id)

    assert report.chapters == []
    assert report.baseline_title == ""
    assert report.skipped == 0
    assert report.drifted == []
    assert report.verdict == "no chapters"


def test_single_chapter_yields_need_at_least_two(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    _write_draft(db, workspace_id, title="第一章", content="雨夜归乡。", draft_id="d1")

    report = compute_style_drift(db, workspace_id)

    assert len(report.chapters) == 1
    assert report.baseline_title == "第一章"
    assert report.drifted == []
    assert report.verdict == "need at least 2 chapters"


def test_all_empty_chapters_yield_need_at_least_two(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    _write_draft(db, workspace_id, title="空章一", content="……", draft_id="d1")
    _write_draft(db, workspace_id, title="空章二", content="   ", draft_id="d2")

    report = compute_style_drift(db, workspace_id)

    assert report.chapters == []
    assert report.skipped == 2
    assert report.baseline_title == ""
    assert report.drifted == []
    assert report.verdict == "need at least 2 chapters"


def test_report_is_deterministic(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    set_style_anchor(
        db, workspace_id, description="短句，克制，冷峻", forbidden_words="璀璨,宛如"
    )
    _write_draft(
        db, workspace_id, title="第一章", content=BASELINE_TEXT, draft_id="d1"
    )
    _write_draft(
        db, workspace_id, title="第二章", content=CHAPTER_A_TEXT, draft_id="d2"
    )
    _write_draft(db, workspace_id, title="空章", content=" ", draft_id="d3")

    first = compute_style_drift(db, workspace_id)
    second = compute_style_drift(db, workspace_id)

    assert first == second


def test_compute_is_read_only(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    set_style_anchor(
        db, workspace_id, description=TWENTY_KEYWORDS, forbidden_words="璀璨,宛如"
    )
    _write_draft(
        db, workspace_id, title="第一章", content=BASELINE_TEXT, draft_id="d1"
    )
    _write_draft(
        db, workspace_id, title="第二章", content=CHAPTER_B_TEXT, draft_id="d2"
    )
    events_before = list_events(db, workspace_id)

    compute_style_drift(db, workspace_id)

    assert len(list_events(db, workspace_id)) == len(events_before)


def test_missing_workspace_is_not_found(tmp_path: Path, monkeypatch) -> None:
    _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        compute_style_drift(db, "no-such-workspace")

    assert exc_info.value.code is ErrorCode.NOT_FOUND
