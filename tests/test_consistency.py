"""Consistency-check service tests (N19 C1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.consistency import check_consistency
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.plot import list_threads, plant_thread, recover_thread
from novel_editorial.core.setting import add_setting, list_settings
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import Draft, DraftVersion, PlotThread

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch, *, title: str = "一致性之书") -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _db() -> DB:
    return DB(load_settings())


def _write_draft(db: DB, workspace_id: str, content: str) -> str:
    """Insert a draft with a single version directly (no LLM involved)."""
    with db.workspace_session(workspace_id) as session:
        draft = Draft(workspace_id=workspace_id, title="第一章", current_version=1)
        session.add(draft)
        session.flush()
        session.add(DraftVersion(draft_id=draft.id, version=1, content=content))
        session.commit()
        return draft.id


def _number_conflicts(report) -> list:
    return [issue for issue in report.issues if issue.kind == "number_conflict"]


def test_character_appearance_counts_and_missing_is_reported(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="character", name="沈夜", content="雨夜归乡的侦探")
    add_setting(db, workspace_id, kind="character", name="林墨", content="沉默的旧识")

    report = check_consistency(
        db,
        workspace_id,
        "沈夜走下月台。沈夜推开候车室的门，沈夜看见了那把伞。",
    )

    assert report.character_mentions == {"沈夜": 3}
    assert report.settings_checked == 2
    assert [issue.kind for issue in report.issues] == ["character_missing"]
    issue = report.issues[0]
    assert issue.setting_name == "林墨"
    assert issue.severity == "info"
    assert issue.detail == "设定人物未在正文出现"
    assert issue.sentence is None


def test_number_conflict_reports_on_same_unit_different_value(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(
        db,
        workspace_id,
        kind="timeline",
        name="旧车站",
        content="末班车每晚十一点进站",
    )

    report = check_consistency(
        db,
        workspace_id,
        "雨夜里他回到旧车站，站台上没有人。旧车站的钟停在十二点。",
    )

    conflicts = _number_conflicts(report)
    assert len(conflicts) == 1
    issue = conflicts[0]
    assert issue.severity == "conflict"
    assert issue.setting_name == "旧车站"
    assert issue.sentence == 2
    assert issue.detail == "正文「十二点」不在设定值中（设定含：十一点）（句 2）"


def test_number_conflict_same_value_is_not_reported(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="timeline", name="旧车站", content="钟停在十一点")

    report = check_consistency(db, workspace_id, "旧车站的钟停在十一点，指针一动不动。")

    assert _number_conflicts(report) == []


def test_number_conflict_different_unit_is_not_reported(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="timeline", name="旧车站", content="钟停在十一点")

    report = check_consistency(db, workspace_id, "旧车站的钟停在十一时。")

    assert _number_conflicts(report) == []


def test_number_conflict_without_topic_word_is_not_reported(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="timeline", name="旧车站", content="钟停在十一点")

    report = check_consistency(db, workspace_id, "远处传来十二点的钟声。")

    assert _number_conflicts(report) == []


def test_number_conflict_normalizes_chinese_and_arabic_digits(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="world", name="钟楼", content="指针停在十一点")

    same_value = check_consistency(db, workspace_id, "钟楼的指针停在11 点。")
    assert _number_conflicts(same_value) == []

    conflicts = _number_conflicts(check_consistency(db, workspace_id, "钟楼的指针停在12 点。"))
    assert len(conflicts) == 1
    assert conflicts[0].detail == "正文「12点」不在设定值中（设定含：十一点）（句 1）"


def test_number_conflict_uses_content_prefix_as_topic_word(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(
        db,
        workspace_id,
        kind="timeline",
        name="旧站档案",
        content="旧车站：钟停在十一点",
    )

    report = check_consistency(db, workspace_id, "旧车站的钟指向十二点。")

    conflicts = _number_conflicts(report)
    assert len(conflicts) == 1
    assert conflicts[0].setting_name == "旧站档案"
    assert conflicts[0].detail == "正文「十二点」不在设定值中（设定含：十一点）（句 1）"


def test_number_conflict_covers_character_kind(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="character", name="沈夜", content="二十岁的古董修复师")

    report = check_consistency(db, workspace_id, "沈夜今年二十五岁。")

    conflicts = _number_conflicts(report)
    assert len(conflicts) == 1
    assert conflicts[0].detail == "正文「二十五岁」不在设定值中（设定含：二十岁）（句 1）"


def test_number_conflict_value_present_in_multi_value_setting_is_not_reported(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(
        db, workspace_id, kind="timeline", name="旧车站", content="钟在十一点闭站，十二点发车"
    )

    report = check_consistency(db, workspace_id, "旧车站的末班车十二点发车。")

    assert _number_conflicts(report) == []


def test_number_conflict_reports_value_absent_from_multi_value_setting(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(
        db, workspace_id, kind="timeline", name="旧车站", content="钟在十一点闭站，十二点发车"
    )

    report = check_consistency(
        db,
        workspace_id,
        "雨夜里他回到旧车站，站台上没有人。旧车站的末班车十三点发车。",
    )

    conflicts = _number_conflicts(report)
    assert len(conflicts) == 1
    issue = conflicts[0]
    assert issue.severity == "conflict"
    assert issue.setting_name == "旧车站"
    assert issue.sentence == 2
    assert issue.detail == "正文「十三点」不在设定值中（设定含：十一点、十二点）（句 2）"


def test_number_conflict_supports_chinese_two(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="timeline", name="车站", content="两点到站")

    report = check_consistency(db, workspace_id, "车站三点到站。")

    conflicts = _number_conflicts(report)
    assert len(conflicts) == 1
    assert conflicts[0].detail == "正文「三点」不在设定值中（设定含：两点）（句 1）"


def test_number_conflict_chinese_two_matches_arabic_two(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="timeline", name="车站", content="两点到站")

    report = check_consistency(db, workspace_id, "车站2点到站。")

    assert _number_conflicts(report) == []


def test_number_conflict_deduplicates_same_value_different_writings(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="timeline", name="车站", content="末班车每晚十一点进站")

    report = check_consistency(db, workspace_id, "车站十二点发车，12点收车。")

    conflicts = _number_conflicts(report)
    assert len(conflicts) == 1
    issue = conflicts[0]
    assert issue.severity == "conflict"
    assert issue.setting_name == "车站"
    assert issue.sentence == 1
    assert issue.detail == "正文「十二点」不在设定值中（设定含：十一点）（句 1）"


def test_thread_hit_suppresses_issue_and_miss_reports(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    plant_thread(
        db,
        workspace_id,
        kind="foreshadow",
        content="黑伞人始终背对站台，伞面缝着旧车站的站徽。",
    )
    plant_thread(db, workspace_id, kind="hook", content="雨夜巷口的三声钟响")

    report = check_consistency(db, workspace_id, "候车室里只有一个人，撑黑伞，背对着他。")

    assert report.threads_checked == 2
    thread_issues = [issue for issue in report.issues if issue.kind == "thread_missing"]
    assert len(thread_issues) == 1
    issue = thread_issues[0]
    assert issue.setting_name == "雨夜巷口的三声钟响"
    assert issue.severity == "info"
    assert issue.detail == "伏笔关键词未出现"
    assert issue.sentence is None


def test_thread_missing_name_is_truncated(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    long_content = "一条特别长的伏笔内容反复提到旧车站地下的密室和消失的站台，正文里一个字都没有"
    plant_thread(db, workspace_id, kind="foreshadow", content=long_content)

    report = check_consistency(db, workspace_id, "这一章只有普通场景描写。")

    thread_issues = [issue for issue in report.issues if issue.kind == "thread_missing"]
    assert len(thread_issues) == 1
    assert thread_issues[0].setting_name.endswith("…")
    assert len(thread_issues[0].setting_name) <= 20
    assert thread_issues[0].setting_name.startswith("一条特别长")


def test_thread_single_char_keyword_hit_suppresses_issue(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    plant_thread(db, workspace_id, kind="foreshadow", content="伞")

    report = check_consistency(db, workspace_id, "候车室角落立着一把伞。")

    assert report.threads_checked == 1
    assert [issue for issue in report.issues if issue.kind == "thread_missing"] == []


def test_thread_single_char_keyword_miss_reports(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    plant_thread(db, workspace_id, kind="foreshadow", content="伞")

    report = check_consistency(db, workspace_id, "候车室角落空无一物。")

    assert report.threads_checked == 1
    thread_issues = [issue for issue in report.issues if issue.kind == "thread_missing"]
    assert len(thread_issues) == 1
    assert thread_issues[0].setting_name == "伞"
    assert thread_issues[0].detail == "伏笔关键词未出现"


def test_recovered_thread_is_not_checked_but_pending_is(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    recovered_id = plant_thread(db, workspace_id, kind="hook", content="雨夜的敲门声")
    recover_thread(db, workspace_id, recovered_id.id)
    pending_id = plant_thread(db, workspace_id, kind="foreshadow", content="钟楼下的旧车票")
    with db.workspace_session(workspace_id) as session:
        thread = session.get(PlotThread, pending_id.id)
        assert thread is not None
        thread.status = "pending"
        session.commit()

    report = check_consistency(db, workspace_id, "正文里什么关键词都没有。")

    assert report.threads_checked == 1
    thread_issues = [issue for issue in report.issues if issue.kind == "thread_missing"]
    assert len(thread_issues) == 1
    assert thread_issues[0].setting_name == "钟楼下的旧车票"


def test_empty_settings_and_threads_yield_clean_report(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    report = check_consistency(db, workspace_id, "雨夜的车站一片寂静。")

    assert report.issues == []
    assert report.settings_checked == 0
    assert report.threads_checked == 0
    assert report.character_mentions == {}


def test_relation_settings_are_not_checked(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(
        db,
        workspace_id,
        kind="relation",
        name="沈夜与林墨",
        content="二十年的旧识",
    )

    report = check_consistency(db, workspace_id, "沈夜与林墨重逢。")

    assert report.settings_checked == 0
    assert report.issues == []
    assert report.character_mentions == {}


@pytest.mark.parametrize("text", ["", "   ", "\n\t", " \u3000 "])
def test_blank_text_is_usage_error(tmp_path: Path, monkeypatch, text: str) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        check_consistency(db, workspace_id, text)

    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "正文为空" in exc_info.value.message
    assert "无法核查" in exc_info.value.message


def test_report_is_deterministic(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="character", name="沈夜", content="雨夜归乡的侦探")
    add_setting(db, workspace_id, kind="timeline", name="旧车站", content="钟停在十一点")
    plant_thread(db, workspace_id, kind="foreshadow", content="黑伞人的旧皮箱")
    plant_thread(db, workspace_id, kind="hook", content="雨夜的敲门声")
    text = "沈夜走进旧车站，钟却指向十二点。黑伞人站在月台尽头。"

    first = check_consistency(db, workspace_id, text)
    second = check_consistency(db, workspace_id, text)

    assert first == second


def test_conflicts_sort_first_then_kind_order(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="character", name="林墨", content="警觉的站台员")
    add_setting(db, workspace_id, kind="character", name="江晚", content="沉默的法医")
    add_setting(db, workspace_id, kind="timeline", name="旧车站", content="钟停在十一点")
    plant_thread(db, workspace_id, kind="foreshadow", content="雨夜巷口的钟声")

    report = check_consistency(db, workspace_id, "林墨走进旧车站，钟指向十二点。")

    assert [issue.kind for issue in report.issues] == [
        "number_conflict",
        "character_missing",
        "thread_missing",
    ]


def test_check_is_read_only(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="character", name="沈夜", content="雨夜归乡的侦探")
    add_setting(db, workspace_id, kind="timeline", name="旧车站", content="钟停在十一点")
    plant_thread(db, workspace_id, kind="foreshadow", content="黑伞人")
    settings_before = list_settings(db, workspace_id)
    threads_before = list_threads(db, workspace_id)
    events_before = list_events(db, workspace_id)

    check_consistency(db, workspace_id, "沈夜走进旧车站，钟指向十二点。")

    assert [entry.id for entry in list_settings(db, workspace_id)] == [
        entry.id for entry in settings_before
    ]
    assert [thread.id for thread in list_threads(db, workspace_id)] == [
        thread.id for thread in threads_before
    ]
    assert len(list_events(db, workspace_id)) == len(events_before)


def test_cli_check_reports_conflicts_mentions_and_missing(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="character", name="沈夜", content="雨夜归乡的侦探")
    add_setting(db, workspace_id, kind="timeline", name="旧车站", content="钟停在十一点")
    plant_thread(db, workspace_id, kind="foreshadow", content="黑伞人")
    draft_id = _write_draft(
        db,
        workspace_id,
        "沈夜回到旧车站，站台上的钟指向十二点。候车室空无一人。",
    )

    result = runner.invoke(app, ["consistency", "check", draft_id])

    assert result.exit_code == 0, result.output
    assert "settings checked: 2 / threads checked: 1" in result.output
    assert "[人物] 沈夜：出现 1 次" in result.output
    assert (
        "[冲突] 旧车站：正文「十二点」不在设定值中（设定含：十一点）（句 1）"
        in result.output
    )
    assert "[未提及] 伏笔·黑伞人：伏笔关键词未出现" in result.output
    assert "[未提及] 沈夜" not in result.output


def test_cli_check_clean_text_prints_no_issues(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="character", name="沈夜", content="雨夜归乡的侦探")
    add_setting(db, workspace_id, kind="timeline", name="旧车站", content="钟停在十一点")
    plant_thread(db, workspace_id, kind="foreshadow", content="黑伞人")
    draft_id = _write_draft(
        db,
        workspace_id,
        "沈夜回到旧车站，站台上的钟指向十一点。黑伞人立在月台尽头。",
    )

    result = runner.invoke(app, ["consistency", "check", draft_id])

    assert result.exit_code == 0, result.output
    assert "settings checked: 2 / threads checked: 1" in result.output
    assert "[人物] 沈夜：出现 1 次" in result.output
    assert "no consistency issues found" in result.output


def test_cli_check_missing_draft_exits_not_found(tmp_path: Path, monkeypatch) -> None:
    _create_workspace(tmp_path, monkeypatch)

    result = runner.invoke(app, ["consistency", "check", "no-such-draft"])

    assert result.exit_code == 1
    assert "draft not found" in result.output


def test_cli_check_blank_content_exits_usage_error(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    draft_id = _write_draft(db, workspace_id, "   ")

    result = runner.invoke(app, ["consistency", "check", draft_id])

    assert result.exit_code == 2
    assert "正文为空" in result.output
