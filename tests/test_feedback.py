from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.feedback import (
    FeedbackReport,
    FeedbackSample,
    analyze_feedback,
    load_feedback_samples,
)
from novel_editorial.quality.gate import check_quality
from novel_editorial.store.db import DB, list_workspace_ids
from novel_editorial.store.models import Event

runner = CliRunner()

CLEAN_TEXT = "他推开门，走进院子，把伞靠在墙边。"
MODIFIER_TEXT = "他静静地看着窗外。"
AI_SINGLE_TEXT = "她不禁莞尔。"
REPEATED_ENDINGS_TEXT = "他走进院子。她走进院子。大家走进院子。"
AI_TWO_TEXT = "她不禁莞尔，仿佛在笑。"
AI_TEXT = "他静静地站着，缓缓转身，月光宛如薄纱，悄然洒落。她走进院子。他走进院子。"


def _write_feedback(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_load_feedback_samples_parses_good_and_bad(tmp_path: Path) -> None:
    path = _write_feedback(
        tmp_path,
        "feedback.jsonl",
        f'{{"label": "good", "text": "{CLEAN_TEXT}"}}\n'
        f'{{"label": "bad", "text": "{AI_TEXT}"}}\n',
    )

    samples = load_feedback_samples(path)

    assert samples == [
        FeedbackSample(label="good", text=CLEAN_TEXT, line=1),
        FeedbackSample(label="bad", text=AI_TEXT, line=2),
    ]


def test_load_feedback_samples_handles_multiline_text_and_blank_lines(
    tmp_path: Path,
) -> None:
    path = _write_feedback(
        tmp_path,
        "feedback.jsonl",
        '{"label": "good", "text": "第一句。\\n第二句。"}\n'
        "\n"
        "   \n"
        '  {"label": "bad", "text": "她不禁莞尔。\\n他走进院子。"}  \n',
    )

    samples = load_feedback_samples(path)

    assert samples[0].text == "第一句。\n第二句。"
    assert samples[0].line == 1
    assert samples[1].text == "她不禁莞尔。\n他走进院子。"
    assert samples[1].line == 4
    assert [sample.label for sample in samples] == ["good", "bad"]


def test_load_feedback_samples_bad_json_reports_line_number(tmp_path: Path) -> None:
    path = _write_feedback(
        tmp_path,
        "feedback.jsonl",
        f'{{"label": "good", "text": "{CLEAN_TEXT}"}}\n{{not json}}\n',
    )

    with pytest.raises(NovelError) as exc_info:
        load_feedback_samples(path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR
    assert "line 2" in exc_info.value.message
    assert exc_info.value.context["line"] == 2


def test_load_feedback_samples_bad_label_reports_line_number(tmp_path: Path) -> None:
    path = _write_feedback(
        tmp_path,
        "feedback.jsonl",
        f'{{"label": "okay", "text": "{CLEAN_TEXT}"}}\n',
    )

    with pytest.raises(NovelError) as exc_info:
        load_feedback_samples(path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR
    assert "line 1" in exc_info.value.message


def test_load_feedback_samples_missing_label_reports_line_number(tmp_path: Path) -> None:
    path = _write_feedback(
        tmp_path,
        "feedback.jsonl",
        f'{{"text": "{CLEAN_TEXT}"}}\n',
    )

    with pytest.raises(NovelError) as exc_info:
        load_feedback_samples(path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR
    assert "line 1" in exc_info.value.message


def test_load_feedback_samples_non_object_reports_line_number(tmp_path: Path) -> None:
    path = _write_feedback(tmp_path, "feedback.jsonl", "[1, 2, 3]\n")

    with pytest.raises(NovelError) as exc_info:
        load_feedback_samples(path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR
    assert "line 1" in exc_info.value.message


def test_load_feedback_samples_blank_text_reports_line_number(tmp_path: Path) -> None:
    path = _write_feedback(
        tmp_path,
        "feedback.jsonl",
        '{"label": "good", "text": "   "}\n',
    )

    with pytest.raises(NovelError) as exc_info:
        load_feedback_samples(path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR
    assert "line 1" in exc_info.value.message


def test_load_feedback_samples_non_string_text_reports_line_number(
    tmp_path: Path,
) -> None:
    path = _write_feedback(
        tmp_path,
        "feedback.jsonl",
        '{"label": "good", "text": 42}\n',
    )

    with pytest.raises(NovelError) as exc_info:
        load_feedback_samples(path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR
    assert "line 1" in exc_info.value.message


def test_load_feedback_samples_missing_path_raises_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"

    with pytest.raises(NovelError) as exc_info:
        load_feedback_samples(missing)
    assert exc_info.value.code == ErrorCode.NOT_FOUND
    assert exc_info.value.context["path"] == str(missing)


def test_load_feedback_samples_empty_file_raises_usage_error(tmp_path: Path) -> None:
    path = _write_feedback(tmp_path, "feedback.jsonl", "")

    with pytest.raises(NovelError) as exc_info:
        load_feedback_samples(path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR
    assert "no valid samples" in exc_info.value.message


def test_load_feedback_samples_only_blank_lines_raises_usage_error(
    tmp_path: Path,
) -> None:
    path = _write_feedback(tmp_path, "feedback.jsonl", "\n  \n\n")

    with pytest.raises(NovelError) as exc_info:
        load_feedback_samples(path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR


def test_analyze_feedback_reports_stats_agreement_and_suggestion() -> None:
    samples = [
        FeedbackSample(label="bad", text=AI_TEXT, line=1),
        FeedbackSample(label="bad", text=AI_TWO_TEXT, line=2),
        FeedbackSample(label="bad", text=REPEATED_ENDINGS_TEXT, line=3),
        FeedbackSample(label="good", text=CLEAN_TEXT, line=4),
        FeedbackSample(label="good", text=MODIFIER_TEXT, line=5),
        FeedbackSample(label="good", text=AI_SINGLE_TEXT, line=6),
    ]

    report = analyze_feedback(samples, threshold=8)

    assert report.samples == samples
    assert report.bad_count == 3
    assert report.good_count == 3
    assert report.bad_stats == (8.0, 12.0, 22.0, 22.0)
    assert report.good_stats == (0.0, 3.0, 6.0, 6.0)
    assert report.threshold_used == 8
    assert report.agreement == pytest.approx(5 / 6)
    assert report.suggested_threshold == 22
    assert report.suggested_agreement == pytest.approx(3 / 6)


def test_analyze_feedback_uses_gate_boundary_score_above_threshold_is_bad() -> None:
    samples = [
        FeedbackSample(label="bad", text=REPEATED_ENDINGS_TEXT, line=1),
        FeedbackSample(label="bad", text=AI_TWO_TEXT, line=2),
        FeedbackSample(label="good", text=CLEAN_TEXT, line=3),
    ]

    report = analyze_feedback(samples, threshold=8)

    assert report.threshold_used == 8
    assert report.agreement == pytest.approx(2 / 3)
    assert report.bad_stats == (8.0, 10.0, 12.0, 12.0)
    assert report.suggested_threshold == 12


def test_analyze_feedback_no_bad_samples_yields_none_suggestion() -> None:
    samples = [
        FeedbackSample(label="good", text=CLEAN_TEXT, line=1),
        FeedbackSample(label="good", text=MODIFIER_TEXT, line=2),
        FeedbackSample(label="good", text=AI_SINGLE_TEXT, line=3),
    ]

    report = analyze_feedback(samples, threshold=8)

    assert report.bad_count == 0
    assert report.good_count == 3
    assert report.bad_stats == ()
    assert report.good_stats == (0.0, 3.0, 6.0, 6.0)
    assert report.agreement == pytest.approx(1.0)
    assert report.suggested_threshold is None
    assert report.suggested_agreement is None


def test_analyze_feedback_no_good_samples_yields_empty_good_stats() -> None:
    samples = [
        FeedbackSample(label="bad", text=CLEAN_TEXT, line=1),
        FeedbackSample(label="bad", text=AI_SINGLE_TEXT, line=2),
    ]

    report = analyze_feedback(samples, threshold=8)

    assert report.bad_count == 2
    assert report.good_count == 0
    assert report.bad_stats == (0.0, 3.0, 6.0, 6.0)
    assert report.good_stats == ()
    assert report.agreement == pytest.approx(0.0)
    assert report.suggested_threshold == 6


def test_analyze_feedback_nearest_rank_p90_below_max() -> None:
    samples = [
        FeedbackSample(label="bad", text=AI_SINGLE_TEXT, line=line)
        for line in range(1, 11)
    ]
    samples.append(FeedbackSample(label="bad", text=AI_TEXT, line=11))

    report = analyze_feedback(samples, threshold=8)

    assert report.bad_count == 11
    assert report.bad_stats == (6.0, 6.0, 6.0, 22.0)
    assert report.suggested_threshold == 6


def test_analyze_feedback_suggested_threshold_floors_at_one() -> None:
    samples = [
        FeedbackSample(label="bad", text=CLEAN_TEXT, line=line)
        for line in range(1, 4)
    ]

    report = analyze_feedback(samples, threshold=8)

    assert report.bad_stats == (0.0, 0.0, 0.0, 0.0)
    assert report.suggested_threshold == 1
    assert report.suggested_agreement == pytest.approx(0.0)


def test_analyze_feedback_empty_samples_yields_empty_report() -> None:
    report = analyze_feedback([], threshold=8)

    assert report == FeedbackReport(
        samples=[],
        bad_count=0,
        good_count=0,
        bad_stats=(),
        good_stats=(),
        threshold_used=8,
        agreement=0.0,
        suggested_threshold=None,
        suggested_agreement=None,
    )


def test_analyze_feedback_scores_match_check_quality(tmp_path: Path) -> None:
    path = _write_feedback(
        tmp_path,
        "feedback.jsonl",
        f'{{"label": "bad", "text": "{AI_TEXT}"}}\n'
        f'{{"label": "good", "text": "{CLEAN_TEXT}"}}\n',
    )
    samples = load_feedback_samples(path)

    report = analyze_feedback(samples, threshold=8)

    assert check_quality(AI_TEXT).score == 22.0
    assert check_quality(CLEAN_TEXT).score == 0.0
    assert report.bad_count == 1
    assert report.good_count == 1
    assert report.suggested_threshold == 22


def test_load_and_analyze_are_deterministic(tmp_path: Path) -> None:
    path = _write_feedback(
        tmp_path,
        "feedback.jsonl",
        f'{{"label": "bad", "text": "{AI_TEXT}"}}\n'
        f'{{"label": "good", "text": "{CLEAN_TEXT}"}}\n'
        f'{{"label": "bad", "text": "{AI_SINGLE_TEXT}"}}\n',
    )
    samples = load_feedback_samples(path)

    first_load = load_feedback_samples(path)
    second_load = load_feedback_samples(path)
    first_report = analyze_feedback(samples, threshold=8)
    second_report = analyze_feedback(samples, threshold=8)

    assert first_load == second_load
    assert first_report == second_report
    assert first_report.bad_stats == second_report.bad_stats
    assert first_report.agreement == second_report.agreement
    assert first_report.suggested_threshold == second_report.suggested_threshold


def test_load_and_analyze_are_read_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    created = runner.invoke(app, ["works", "create", "反馈之书", "--genre", "都市"])
    assert created.exit_code == 0, created.output
    workspace_id = created.output.split()[2].rstrip(":")

    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        events_before = session.query(Event).count()

    path = _write_feedback(
        tmp_path,
        "feedback.jsonl",
        f'{{"label": "bad", "text": "{AI_TEXT}"}}\n'
        f'{{"label": "good", "text": "{CLEAN_TEXT}"}}\n',
    )
    samples = load_feedback_samples(path)
    analyze_feedback(samples, threshold=8)

    with db.workspace_session(workspace_id) as session:
        events_after = session.query(Event).count()
    assert events_after == events_before
    assert list_workspace_ids(settings) == [workspace_id]
