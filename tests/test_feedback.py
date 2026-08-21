import json
from pathlib import Path
from types import SimpleNamespace

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
SCORE_10_TEXTS = [
    "她不禁莞尔。她不禁莞尔。",
    "他仿佛笑了。他仿佛笑了。",
    "她悄然离开。她悄然离开。",
    "月光宛如纱。月光宛如纱。",
    "她瞬间回头。她瞬间回头。",
    "他深邃凝望。他深邃凝望。",
]
SCORE_14_TEXT = "她不禁莞尔。她不禁莞尔。她不禁莞尔。"
SCORE_9_TEXT = "她不禁莞尔，静静站着。"


def _write_feedback(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _invoke(tmp_path: Path, monkeypatch, *args: str):
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    return runner.invoke(app, list(args))


def _write_cli_feedback(tmp_path: Path) -> Path:
    """Write a 12-line JSONL that reproduces the documented CLI example shape:

    threshold 8 agrees 10/12, the best agreement is 11/12 shared by t=6,
    t=7 and t=9, and the tie-break picks the higher suggested threshold 9.
    """
    lines = [
        {"label": "bad", "text": REPEATED_ENDINGS_TEXT},
        *({"label": "bad", "text": text} for text in SCORE_10_TEXTS),
        {"label": "bad", "text": SCORE_14_TEXT},
        {"label": "good", "text": CLEAN_TEXT},
        {"label": "good", "text": MODIFIER_TEXT},
        {"label": "good", "text": AI_SINGLE_TEXT},
        {"label": "good", "text": SCORE_9_TEXT},
    ]
    path = tmp_path / "feedback.jsonl"
    path.write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines),
        encoding="utf-8",
    )
    return path


def _patch_scores(monkeypatch, scores: dict[str, float]) -> None:
    """Replace check_quality with a deterministic per-text score map."""
    monkeypatch.setattr(
        "novel_editorial.core.feedback.check_quality",
        lambda text, **kwargs: SimpleNamespace(score=scores[text]),
    )


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
    assert report.suggested_threshold == 7
    assert report.suggested_agreement == pytest.approx(1.0)


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
    assert report.suggested_threshold == 7
    assert report.suggested_agreement == pytest.approx(1.0)


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
    assert report.suggested_threshold == 5
    assert report.suggested_agreement == pytest.approx(0.5)


def test_analyze_feedback_nearest_rank_p90_below_max() -> None:
    samples = [
        FeedbackSample(label="bad", text=AI_SINGLE_TEXT, line=line)
        for line in range(1, 11)
    ]
    samples.append(FeedbackSample(label="bad", text=AI_TEXT, line=11))

    report = analyze_feedback(samples, threshold=8)

    assert report.bad_count == 11
    assert report.bad_stats == (6.0, 6.0, 6.0, 22.0)
    assert report.suggested_threshold == 21
    assert report.suggested_agreement == pytest.approx(1 / 11)


def test_analyze_feedback_flat_agreement_breaks_tie_to_higher_threshold() -> None:
    samples = [
        FeedbackSample(label="bad", text=CLEAN_TEXT, line=line)
        for line in range(1, 4)
    ]

    report = analyze_feedback(samples, threshold=8)

    assert report.bad_stats == (0.0, 0.0, 0.0, 0.0)
    assert report.suggested_threshold == 8
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
    assert report.suggested_threshold == 21
    assert report.suggested_agreement == pytest.approx(1.0)


def test_analyze_feedback_decimal_scores_use_integer_grid(monkeypatch) -> None:
    """P2: fractional sample scores are never truncated into int(best).

    bad=9.5 / good=9.2 at threshold 8 spans the integer grid {8, 9, 10}; every
    candidate agrees on 1/2, so the tie-break picks the highest (10). The old
    implementation instead picked fractional candidate 9.2 and reported
    int(best) = 9 with a recomputed agreement that did not match the best.
    """
    bad = FeedbackSample(label="bad", text="bad text", line=1)
    good = FeedbackSample(label="good", text="good text", line=2)
    _patch_scores(monkeypatch, {"bad text": 9.5, "good text": 9.2})

    report = analyze_feedback([bad, good], threshold=8)

    assert report.suggested_threshold == 10
    assert report.suggested_agreement == pytest.approx(0.5)
    recomputed = (
        sum(
            1
            for sample, score in ((bad, 9.5), (good, 9.2))
            if (sample.label == "bad") == (score > report.suggested_threshold)
        )
        / 2
    )
    assert report.suggested_agreement == pytest.approx(recomputed)


def test_analyze_feedback_decimal_scores_can_reach_full_agreement(
    monkeypatch,
) -> None:
    """P2: decimal scores can land on a mid-grid integer with full agreement.

    bad=9.5 / good=8.8 at threshold 8: the integer grid {8, 9, 10} maximizes
    agreement at t=9 (bad 9.5 > 9, good 8.8 <= 9), so the suggestion is 9 with
    agreement 1.0 — no fractional candidate and no truncated report.
    """
    bad = FeedbackSample(label="bad", text="bad text", line=1)
    good = FeedbackSample(label="good", text="good text", line=2)
    _patch_scores(monkeypatch, {"bad text": 9.5, "good text": 8.8})

    report = analyze_feedback([bad, good], threshold=8)

    assert report.suggested_threshold == 9
    assert report.suggested_agreement == pytest.approx(1.0)


def test_analyze_feedback_tie_breaks_to_higher_suggested_threshold() -> None:
    samples = [
        FeedbackSample(label="bad", text=AI_TEXT, line=1),
        FeedbackSample(label="good", text=CLEAN_TEXT, line=2),
        FeedbackSample(label="good", text=MODIFIER_TEXT, line=3),
        FeedbackSample(label="good", text=AI_SINGLE_TEXT, line=4),
    ]

    report = analyze_feedback(samples, threshold=8)

    # Every integer t in 6..21 reaches 4/4 agreement; the highest (most
    # conservative) threshold wins even though the maximum sample score is 22.
    assert report.suggested_threshold == 21
    assert report.suggested_agreement == pytest.approx(1.0)


def test_analyze_feedback_suggestion_blocks_most_bad_samples() -> None:
    samples = [
        FeedbackSample(label="bad", text=AI_TWO_TEXT, line=1),
        FeedbackSample(label="bad", text=AI_TEXT, line=2),
        FeedbackSample(label="good", text=CLEAN_TEXT, line=3),
        FeedbackSample(label="good", text=MODIFIER_TEXT, line=4),
        FeedbackSample(label="good", text=AI_SINGLE_TEXT, line=5),
    ]

    report = analyze_feedback(samples, threshold=8)

    assert report.suggested_threshold == 11
    blocked_bad = sum(
        check_quality(sample.text).score > report.suggested_threshold
        for sample in samples
        if sample.label == "bad"
    )
    passed_good = sum(
        check_quality(sample.text).score <= report.suggested_threshold
        for sample in samples
        if sample.label == "good"
    )
    assert blocked_bad == 2  # 多数 bad 被拦住
    assert passed_good == 3  # good 全部放行


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


def test_quality_feedback_registered_and_documented() -> None:
    result = runner.invoke(app, ["quality", "feedback", "--help"])

    assert result.exit_code == 0, result.output
    assert "feedback" in result.output
    assert "--apply" in result.output


def test_quality_feedback_reports_fields_and_suggestion(
    tmp_path: Path, monkeypatch
) -> None:
    assert check_quality(REPEATED_ENDINGS_TEXT).score == 8.0
    assert check_quality(SCORE_10_TEXTS[0]).score == 10.0
    assert check_quality(SCORE_14_TEXT).score == 14.0
    assert check_quality(SCORE_9_TEXT).score == 9.0
    path = _write_cli_feedback(tmp_path)

    result = _invoke(tmp_path, monkeypatch, "quality", "feedback", str(path))

    assert result.exit_code == 0, result.output
    assert "samples: 12" in result.output
    assert "bad: 8 / good: 4" in result.output
    assert "bad scores: min 8 median 10 p90 14 max 14" in result.output
    assert "good scores: min 0 median 4.5 p90 9 max 9" in result.output
    assert "agreement at threshold 8: 83.3% (10/12)" in result.output
    assert "suggested threshold: 9" in result.output
    assert "agreement at suggested: 91.7% (11/12)" in result.output


def test_quality_feedback_apply_writes_config(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    path = _write_cli_feedback(tmp_path)

    result = _invoke(
        tmp_path, monkeypatch, "quality", "feedback", str(path), "--apply"
    )

    assert result.exit_code == 0, result.output
    assert "apply: quality_threshold = 9" in result.output
    assert f"config updated: {config_path}" in result.output
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 9


def test_quality_feedback_apply_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    path = _write_cli_feedback(tmp_path)

    first = _invoke(
        tmp_path, monkeypatch, "quality", "feedback", str(path), "--apply"
    )
    assert first.exit_code == 0, first.output
    content_after_first = config_path.read_text(encoding="utf-8")

    second = _invoke(
        tmp_path, monkeypatch, "quality", "feedback", str(path), "--apply"
    )

    assert second.exit_code == 0, second.output
    assert config_path.read_text(encoding="utf-8") == content_after_first


def test_quality_feedback_without_apply_never_writes_config(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "config.toml"
    path = _write_cli_feedback(tmp_path)

    result = _invoke(tmp_path, monkeypatch, "quality", "feedback", str(path))

    assert result.exit_code == 0, result.output
    assert not config_path.exists()


def test_quality_feedback_no_bad_samples_reports_na(
    tmp_path: Path, monkeypatch
) -> None:
    path = _write_feedback(
        tmp_path,
        "good-only.jsonl",
        f'{{"label": "good", "text": "{CLEAN_TEXT}"}}\n'
        f'{{"label": "good", "text": "{MODIFIER_TEXT}"}}\n',
    )

    result = _invoke(tmp_path, monkeypatch, "quality", "feedback", str(path))

    assert result.exit_code == 0, result.output
    assert "bad: 0 / good: 2" in result.output
    assert "bad scores: n/a" in result.output
    assert "suggested threshold: n/a (no bad samples)" in result.output
    assert "agreement at suggested" not in result.output


def test_quality_feedback_apply_without_bad_exits_2(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "config.toml"
    path = _write_feedback(
        tmp_path,
        "good-only.jsonl",
        f'{{"label": "good", "text": "{CLEAN_TEXT}"}}\n',
    )

    result = _invoke(
        tmp_path, monkeypatch, "quality", "feedback", str(path), "--apply"
    )

    assert result.exit_code == 2
    assert "no bad samples" in result.output
    assert not config_path.exists()


def test_quality_feedback_missing_path_exits_1(tmp_path: Path, monkeypatch) -> None:
    result = _invoke(
        tmp_path, monkeypatch, "quality", "feedback", str(tmp_path / "nope.jsonl")
    )

    assert result.exit_code == 1
    assert "not found" in result.output


def test_quality_feedback_bad_jsonl_exits_2(tmp_path: Path, monkeypatch) -> None:
    path = _write_feedback(tmp_path, "bad.jsonl", '{"label": "good", "text": 42}\n')

    result = _invoke(tmp_path, monkeypatch, "quality", "feedback", str(path))

    assert result.exit_code == 2
    assert "line 1" in result.output
