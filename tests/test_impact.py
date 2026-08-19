"""N18 L1: setting impact analysis core service tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.impact import (
    SettingImpactItem,
    SettingImpactReport,
    analyze_setting_impact,
    extract_keywords,
)
from novel_editorial.core.plot import plant_thread
from novel_editorial.core.setting import add_setting, revise_setting
from novel_editorial.store.db import DB
from novel_editorial.store.models import (
    Agent,
    AgentMemory,
    Draft,
    DraftVersion,
    Message,
    Review,
)

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch, title: str = "影响之书") -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _db() -> DB:
    return DB(load_settings())


def _writer_id(db: DB, workspace_id: str) -> str:
    with db.workspace_session(workspace_id) as session:
        writer = session.query(Agent).filter_by(workspace_id=workspace_id, role="writer").first()
        assert writer is not None
        return writer.id


def _add_message(
    db: DB,
    workspace_id: str,
    actor: str,
    content: str,
    *,
    created_at: datetime | None = None,
) -> Message:
    with db.workspace_session(workspace_id) as session:
        row = Message(
            workspace_id=workspace_id,
            role="author",
            actor=actor,
            content=content,
            created_at=created_at or datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        return row


def _add_draft_version(
    db: DB,
    workspace_id: str,
    *,
    title: str,
    version: int,
    content: str,
    created_at: datetime | None = None,
) -> tuple[Draft, DraftVersion]:
    with db.workspace_session(workspace_id) as session:
        draft = (
            session.query(Draft)
            .filter_by(workspace_id=workspace_id, title=title)
            .first()
        )
        if draft is None:
            draft = Draft(workspace_id=workspace_id, title=title, current_version=version)
            session.add(draft)
            session.flush()
        row = DraftVersion(
            draft_id=draft.id,
            version=version,
            content=content,
            created_at=created_at or datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        return draft, row


def _add_review(
    db: DB,
    workspace_id: str,
    draft_id: str,
    actor: str,
    content: str,
    *,
    created_at: datetime | None = None,
) -> Review:
    with db.workspace_session(workspace_id) as session:
        row = Review(
            workspace_id=workspace_id,
            draft_id=draft_id,
            role="reviewer",
            actor=actor,
            content=content,
            created_at=created_at or datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        return row


def _add_note(
    db: DB,
    workspace_id: str,
    agent_id: str,
    content: str,
    *,
    archived_at: datetime | None = None,
) -> AgentMemory:
    with db.workspace_session(workspace_id) as session:
        row = AgentMemory(
            workspace_id=workspace_id,
            agent_id=agent_id,
            content=content,
            archived_at=archived_at,
        )
        session.add(row)
        session.commit()
        return row


def test_extract_keywords_dedupes_and_filters_short_tokens() -> None:
    assert extract_keywords("林墨", "雨夜 雨夜 侦探 雨 沉默 沉默寡言") == [
        "林墨",
        "沉默寡言",
        "雨夜",
        "侦探",
        "沉默",
    ]


def test_extract_keywords_caps_fragments_at_five() -> None:
    assert extract_keywords("名", "甲乙 丙丁 戊己 庚辛 壬癸 子丑 寅卯") == [
        "名",
        "甲乙",
        "丙丁",
        "戊己",
        "庚辛",
        "壬癸",
    ]


def test_extract_keywords_never_uses_whole_content() -> None:
    keywords = extract_keywords("名", "第一段 第二段 第三段")
    assert "第一段 第二段 第三段" not in keywords
    assert keywords[1:] == ["第一段", "第二段", "第三段"]


def test_extract_keywords_falls_back_to_content_prefix() -> None:
    assert extract_keywords("名", "a b c") == ["名", "a b c"]
    long = " ".join(["a"] * 30)
    assert extract_keywords("名", long) == ["名", long[:20]]


def test_analyze_returns_empty_report_when_no_impact(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(db, workspace_id, kind="character", name="林墨", content="雨夜 侦探")

    report = analyze_setting_impact(db, workspace_id, entry.id)

    assert isinstance(report, SettingImpactReport)
    assert report.setting_kind == "character"
    assert report.setting_name == "林墨"
    assert report.setting_version == 1
    assert report.total == 0
    assert report.impacts == []


def test_analyze_unknown_setting_raises_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        analyze_setting_impact(db, workspace_id, "deadbeefdeadbeefdeadbeefdeadbeef")
    assert exc_info.value.code is ErrorCode.NOT_FOUND
    assert "setting not found" in exc_info.value.message


def test_analyze_matches_setting_name(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(db, workspace_id, kind="character", name="钟声", content="雨夜 旧城 回荡")
    _add_message(db, workspace_id, "写手", "钟声在雨夜响起")

    report = analyze_setting_impact(db, workspace_id, entry.id)

    assert report.total == 1
    hit = report.impacts[0]
    assert hit.layer == "对话"
    assert hit.source == "写手"
    assert hit.snippet == "钟声在雨夜响起"


def test_analyze_matches_content_fragment(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(
        db,
        workspace_id,
        kind="character",
        name="设定甲",
        content="沉默寡言 的 侦探",
    )
    _add_draft_version(
        db,
        workspace_id,
        title="第一章",
        version=1,
        content="沉默寡言的侦探在雨夜登场",
    )

    report = analyze_setting_impact(db, workspace_id, entry.id)

    assert report.total == 1
    hit = report.impacts[0]
    assert hit.layer == "版本"
    assert hit.source == "第一章 v1"
    assert hit.snippet == "沉默寡言的侦探在雨夜登场"


def test_analyze_hits_every_layer_with_citations(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(db, workspace_id, kind="character", name="钟声", content="雨夜 旧城 回荡")
    draft, _ = _add_draft_version(
        db,
        workspace_id,
        title="第一章",
        version=2,
        content="钟声在教堂响起",
    )
    _add_message(db, workspace_id, "写手", "钟声问题确认")
    _add_review(db, workspace_id, draft.id, "责编", "钟声段落再打磨")
    plant_thread(db, workspace_id, kind="foreshadow", content="钟声是关键")
    _add_note(db, workspace_id, _writer_id(db, workspace_id), "钟声备忘")
    add_setting(db, workspace_id, kind="world", name="世界观", content="钟声来自旧城")

    report = analyze_setting_impact(db, workspace_id, entry.id)

    assert report.total == 6
    assert [(hit.layer, hit.source) for hit in report.impacts] == [
        ("版本", "第一章 v2"),
        ("对话", "写手"),
        ("意见", "责编 的意见"),
        ("线索", "伏笔：伏笔"),
        ("笔记", "写手"),
        ("设定", "世界观（世界观）"),
    ]
    assert all(isinstance(hit, SettingImpactItem) for hit in report.impacts)


def test_analyze_orders_layers_fixed_and_time_desc_within_layer(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(db, workspace_id, kind="character", name="钟声", content="雨夜 旧城")
    now = datetime.now(UTC)
    _add_message(db, workspace_id, "写手", "钟声早", created_at=now - timedelta(hours=2))
    _add_message(db, workspace_id, "写手", "钟声晚", created_at=now - timedelta(hours=1))
    _add_draft_version(
        db,
        workspace_id,
        title="第一章",
        version=1,
        content="钟声版本",
        created_at=now - timedelta(minutes=30),
    )

    report = analyze_setting_impact(db, workspace_id, entry.id)

    assert [hit.layer for hit in report.impacts] == ["版本", "对话", "对话"]
    assert [hit.snippet for hit in report.impacts] == ["钟声版本", "钟声晚", "钟声早"]


def test_analyze_excludes_self_and_history_versions(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(
        db,
        workspace_id,
        kind="character",
        name="钟声",
        content="钟声 是 旧城 信物",
    )
    revise_setting(db, workspace_id, entry.id, content="钟声 新版", reason="调整", actor="作者")

    report = analyze_setting_impact(db, workspace_id, entry.id)

    assert report.total == 0
    assert report.impacts == []


def test_analyze_counts_other_entry_with_same_name(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(db, workspace_id, kind="character", name="钟声", content="雨夜 回荡")
    add_setting(db, workspace_id, kind="world", name="钟声", content="旧城习俗")

    report = analyze_setting_impact(db, workspace_id, entry.id)

    assert report.total == 1
    assert report.impacts[0].layer == "设定"
    assert report.impacts[0].source == "钟声（世界观）"


def test_analyze_skips_archived_notes(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(db, workspace_id, kind="character", name="钟声", content="雨夜 回荡")
    _add_note(
        db,
        workspace_id,
        _writer_id(db, workspace_id),
        "钟声归档",
        archived_at=datetime.now(UTC),
    )

    report = analyze_setting_impact(db, workspace_id, entry.id)

    assert report.total == 0


def test_analyze_includes_only_active_notes(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(db, workspace_id, kind="character", name="钟声", content="雨夜 回荡")
    writer_id = _writer_id(db, workspace_id)
    _add_note(db, workspace_id, writer_id, "钟声活跃")
    _add_note(
        db,
        workspace_id,
        writer_id,
        "钟声归档",
        archived_at=datetime.now(UTC),
    )

    report = analyze_setting_impact(db, workspace_id, entry.id)

    assert report.total == 1
    assert report.impacts[0].layer == "笔记"
    assert report.impacts[0].source == "写手"
    assert report.impacts[0].snippet == "钟声活跃"


def test_analyze_note_source_falls_back_to_agent_id(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(db, workspace_id, kind="character", name="钟声", content="雨夜 回荡")
    _add_note(db, workspace_id, "ghost_agent", "钟声备忘录")

    report = analyze_setting_impact(db, workspace_id, entry.id)

    assert report.impacts[0].source == "ghost_agent"


def test_analyze_limit_truncates_after_total(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(db, workspace_id, kind="character", name="钟声", content="雨夜 回荡")
    now = datetime.now(UTC)
    for index in range(3):
        _add_message(
            db,
            workspace_id,
            "写手",
            f"钟声消息{index}",
            created_at=now - timedelta(minutes=index),
        )

    report = analyze_setting_impact(db, workspace_id, entry.id, limit=2)

    assert report.total == 3
    assert len(report.impacts) == 2
    assert [hit.snippet for hit in report.impacts] == ["钟声消息0", "钟声消息1"]


def test_analyze_snippet_truncates_long_content(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(db, workspace_id, kind="character", name="钟声", content="雨夜 回荡")
    long_content = "钟声" + "甲" * 70
    _add_message(db, workspace_id, "写手", long_content)

    report = analyze_setting_impact(db, workspace_id, entry.id)

    assert report.impacts[0].snippet == long_content[:60] + "…"


def test_analyze_is_case_insensitive(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(db, workspace_id, kind="character", name="Hook", content="hidden 在 剧情")
    _add_message(db, workspace_id, "写手", "the hook is planted")

    report = analyze_setting_impact(db, workspace_id, entry.id)

    assert report.total == 1
    assert report.impacts[0].snippet == "the hook is planted"


def test_analyze_single_layer_failure_degrades(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(db, workspace_id, kind="character", name="钟声", content="雨夜 回荡")
    _add_draft_version(
        db,
        workspace_id,
        title="第一章",
        version=1,
        content="钟声版本",
    )
    _add_message(db, workspace_id, "写手", "钟声消息")

    def boom(*args, **kwargs):
        raise RuntimeError("message layer down")

    monkeypatch.setattr("novel_editorial.core.impact._query_messages", boom)
    report = analyze_setting_impact(db, workspace_id, entry.id)

    assert report.total == 1
    assert [hit.layer for hit in report.impacts] == ["版本"]
    captured = capsys.readouterr()
    assert "warning: impact layer skipped: 对话: message layer down" in captured.err


def test_analyze_is_isolated_between_workspaces(tmp_path: Path, monkeypatch) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")
    db = _db()
    entry_a = add_setting(db, workspace_a, kind="character", name="钟声", content="雨夜 回荡")
    entry_b = add_setting(db, workspace_b, kind="character", name="钟声", content="雨夜 回荡")
    _add_message(db, workspace_a, "写手", "钟声在甲书响起")

    report_a = analyze_setting_impact(db, workspace_a, entry_a.id)
    report_b = analyze_setting_impact(db, workspace_b, entry_b.id)

    assert report_a.total == 1
    assert report_b.total == 0
