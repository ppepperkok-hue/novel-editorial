"""Quality gate command group."""

from __future__ import annotations

import typer

from novel_editorial.core.config import load_settings
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
    if issues:
        summary = style_consistency_summary(version.content, style_keywords)
        if summary is not None:
            typer.echo(summary)
