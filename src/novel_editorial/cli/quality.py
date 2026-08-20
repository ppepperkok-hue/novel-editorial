"""Quality gate command group."""

from __future__ import annotations

import typer

from novel_editorial.core.calibration import scan_corpus
from novel_editorial.core.config import load_settings, set_quality_threshold
from novel_editorial.core.draft import find_draft_anywhere, get_draft_version
from novel_editorial.core.style import extract_style_keywords, get_style_anchor
from novel_editorial.quality.explain import (
    explain_quality,
    render_explanation,
    style_consistency_summary,
)
from novel_editorial.quality.gate import check_quality
from novel_editorial.store.db import DB

quality_app = typer.Typer(help="Quality gate")


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
