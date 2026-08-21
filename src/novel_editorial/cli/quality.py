"""Quality gate command group."""

from __future__ import annotations

import typer

from novel_editorial.core.calibration import scan_corpus
from novel_editorial.core.config import load_settings, set_quality_threshold
from novel_editorial.core.draft import find_draft_anywhere, get_draft_version
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.feedback import analyze_feedback, load_feedback_samples
from novel_editorial.core.style import extract_style_keywords, get_style_anchor
from novel_editorial.quality.explain import (
    explain_quality,
    render_explanation,
    style_consistency_summary,
)
from novel_editorial.quality.gate import check_quality
from novel_editorial.quality.gems import (
    SIGNAL_DIALOGUE,
    SIGNAL_NUMBER_DETAIL,
    SIGNAL_SENSORY,
    GoodSentence,
    find_good_sentences,
)
from novel_editorial.store.db import DB

quality_app = typer.Typer(help="Quality gate")

_SIGNAL_LABELS = {
    SIGNAL_DIALOGUE: "对话引语",
    SIGNAL_NUMBER_DETAIL: "数字细节",
    SIGNAL_SENSORY: "感官细节",
}
_SIGNAL_ORDER = (SIGNAL_DIALOGUE, SIGNAL_NUMBER_DETAIL, SIGNAL_SENSORY)


def _render_score(value: float) -> str:
    """Render a score without a trailing .0 while keeping fractional values."""
    return f"{value:g}"


def _render_stats(stats: tuple[float, ...]) -> str:
    """Render min / median / p90 / max, or n/a when the group is empty."""
    if not stats:
        return "n/a"
    return (
        f"min {_render_score(stats[0])} median {_render_score(stats[1])} "
        f"p90 {_render_score(stats[2])} max {_render_score(stats[3])}"
    )


def _render_agreement(agreement: float, total: int) -> str:
    """Render an agreement fraction as percent plus an exact fraction."""
    numerator = round(agreement * total)
    return f"{agreement * 100:.1f}% ({numerator}/{total})"


def render_good_sentences(gems: list[GoodSentence]) -> str | None:
    """Render the good-sentences block, or None when there are no gems."""
    if not gems:
        return None
    indexes = "、".join(str(gem.index) for gem in gems)
    labels = [
        _SIGNAL_LABELS[signal]
        for signal in _SIGNAL_ORDER
        if any(signal in gem.signals for gem in gems)
    ]
    lines = [f"good sentences: 句 {indexes}（{'、'.join(labels)}，建议保留）"]
    lines.extend(f"  {gem.index}: {gem.snippet}" for gem in gems)
    return "\n".join(lines)


@quality_app.command("check")
def quality_check(draft_id: str = typer.Argument(..., help="Draft id")) -> None:
    """Run the AI-flavor quality gate on the latest version of a draft."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    version = get_draft_version(db, draft.workspace_id, draft_id, draft.current_version)
    anchor = get_style_anchor(db, draft.workspace_id)
    style_keywords = extract_style_keywords(anchor.description)
    report = check_quality(
        version.content,
        threshold=settings.quality_threshold,
        style_keywords=style_keywords,
    )
    typer.echo(f"passed: {report.passed}")
    typer.echo(f"score: {report.score} (threshold {settings.quality_threshold})")
    typer.echo(f"ai word hits: {report.details['ai_word_hits']}")
    typer.echo(f"modifier hits: {report.details['modifier_hits']}")
    typer.echo(f"sentence repetition: {report.details['sentence_repetition']}")
    if style_keywords:
        consistency = report.details["style_consistency"]
        typer.echo(
            f"style hits: {len(report.details['style_hits'])}/{len(style_keywords)} "
            f"(consistency {consistency:.2f})"
        )
    else:
        typer.echo("style hits: n/a (no style keywords)")


@quality_app.command("explain")
def quality_explain(draft_id: str = typer.Argument(..., help="Draft id")) -> None:
    """Locate AI-flavor sentences in the latest draft version with rewrite suggestions."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    version = get_draft_version(db, draft.workspace_id, draft_id, draft.current_version)
    anchor = get_style_anchor(db, draft.workspace_id)
    style_keywords = extract_style_keywords(anchor.description)
    issues = explain_quality(version.content)
    if issues:
        typer.echo(f"{draft.title} (v{version.version})")
    typer.echo(render_explanation(issues))
    summary = style_consistency_summary(version.content, style_keywords)
    if summary is not None:
        typer.echo(summary)
    good_block = render_good_sentences(find_good_sentences(version.content))
    if good_block is not None:
        typer.echo(good_block)


@quality_app.command("calibrate")
def quality_calibrate(
    corpus_path: str = typer.Argument(
        ..., help="Corpus directory or a single .txt/.md file"
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Write the suggested threshold into config.toml"
    ),
) -> None:
    """Scan a corpus and suggest an AI-flavor quality threshold."""
    settings = load_settings()
    report = scan_corpus(corpus_path)
    typer.echo(f"samples: {len(report.samples)}")
    for sample in report.samples:
        typer.echo(
            f"{sample.path}: 字数 {sample.char_count} · AI 词 {sample.ai_word_hits} · "
            f"修饰词 {sample.modifier_hits} · 句式重复 {sample.sentence_repetition} · "
            f"score {sample.score}"
        )
    typer.echo(
        f"distribution: min {report.min} median {report.median} p90 {report.p90} "
        f"p95 {report.p95} max {report.max}"
    )
    typer.echo(f"suggested threshold: {report.suggested_threshold}")
    if report.skipped > 0:
        typer.echo(f"skipped: {report.skipped}")
    for error in report.errors:
        typer.echo(f"warning: {error}", err=True)
    if apply:
        typer.echo(f"apply: quality_threshold = {report.suggested_threshold}")
        set_quality_threshold(settings.config_path, report.suggested_threshold)
        typer.echo(f"config updated: {settings.config_path}")


@quality_app.command("feedback")
def quality_feedback(
    feedback_path: str = typer.Argument(
        ..., help="Path to annotated feedback JSONL (one {label, text} per line)"
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Write the suggested threshold into config.toml"
    ),
) -> None:
    """Align the quality gate with annotated trial-reader feedback."""
    settings = load_settings()
    samples = load_feedback_samples(feedback_path)
    report = analyze_feedback(samples, settings.quality_threshold)
    total = len(report.samples)
    typer.echo(f"samples: {total}")
    typer.echo(f"bad: {report.bad_count} / good: {report.good_count}")
    typer.echo(f"bad scores: {_render_stats(report.bad_stats)}")
    typer.echo(f"good scores: {_render_stats(report.good_stats)}")
    typer.echo(
        f"agreement at threshold {report.threshold_used}: "
        f"{_render_agreement(report.agreement, total)}"
    )
    if report.suggested_threshold is None:
        typer.echo("suggested threshold: n/a (no bad samples)")
    else:
        typer.echo(f"suggested threshold: {report.suggested_threshold}")
        if report.suggested_agreement is not None:
            typer.echo(
                "agreement at suggested: "
                f"{_render_agreement(report.suggested_agreement, total)}"
            )
    if apply:
        if report.suggested_threshold is None:
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                "cannot apply a suggested threshold without bad samples",
                context={"path": feedback_path},
            )
        typer.echo(f"apply: quality_threshold = {report.suggested_threshold}")
        set_quality_threshold(settings.config_path, report.suggested_threshold)
        typer.echo(f"config updated: {settings.config_path}")
