"""Style command group."""

from __future__ import annotations

import typer

from novel_editorial.core import proactive
from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.config import load_settings
from novel_editorial.core.style import get_style_anchor, set_style_anchor
from novel_editorial.core.style_drift import (
    compute_style_drift,
    read_forbidden_words,
)
from novel_editorial.core.style_learn import (
    build_suggested_description,
    collect_corpus_texts,
    compute_style_profile,
)
from novel_editorial.store.db import DB

style_app = typer.Typer(help="Manage style anchors")


def _record_proactive(db: DB, workspace_id: str, trigger: str, context: dict) -> None:
    """Evaluate and echo proactive messages; a failure never rolls business back."""
    try:
        messages = proactive.record_proactive_messages(db, workspace_id, trigger, context)
    except Exception as exc:
        typer.echo(f"warning: proactive messages skipped: {exc}", err=True)
        return
    for message in messages:
        typer.echo(f"{message.actor}: {message.content}")


@style_app.command("set")
def style_set(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    description: str = typer.Option("", "--description", help="Style description"),
    forbidden: str = typer.Option("", "--forbidden", help="Forbidden words, comma separated"),
) -> None:
    """Set the workspace style anchor."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    anchor = set_style_anchor(db, workspace_id, description=description, forbidden_words=forbidden)
    typer.echo(f"style anchor updated: {workspace_id}")
    _record_proactive(
        db,
        workspace_id,
        proactive.TRIGGER_STYLE_SET,
        {"description": anchor.description, "forbidden_words": anchor.forbidden_words},
    )


@style_app.command("show")
def style_show(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """Show the workspace style anchor."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    anchor = get_style_anchor(db, workspace_id)
    typer.echo(f"description: {anchor.description or '(empty)'}")
    typer.echo(f"forbidden: {anchor.forbidden_words or '(empty)'}")


@style_app.command("learn")
def style_learn(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    corpus_path: str = typer.Argument(..., help="Corpus file or directory"),
    apply: bool = typer.Option(
        False, "--apply", help="Write the suggested description to the style anchor"
    ),
) -> None:
    """Learn a style description from reference texts (read-only unless --apply)."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    texts = collect_corpus_texts(corpus_path)
    profile = compute_style_profile(texts)
    description = build_suggested_description(profile)
    typer.echo(f"samples: {profile.samples}")
    typer.echo(f"avg sentence length: {profile.avg_sentence_len:.1f} 字")
    typer.echo(f"short sentence ratio: {profile.short_sentence_ratio * 100:.1f}%")
    typer.echo(f"modifier per 1000 chars: {profile.modifier_per_1000:.1f}")
    if profile.ai_word_hits:
        typer.echo(f"ai words in corpus: {'、'.join(profile.ai_word_hits)}")
    typer.echo(f"suggested description: {description}")
    if apply:
        typer.echo(f"apply: description = {description}")
        anchor = get_style_anchor(db, workspace_id)
        set_style_anchor(
            db,
            workspace_id,
            description=description,
            forbidden_words=anchor.forbidden_words,
        )
        typer.echo(f"style anchor updated: {workspace_id}")


@style_app.command("drift")
def style_drift(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """Show cross-chapter style drift for one workspace (read-only)."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    report = compute_style_drift(db, workspace_id)

    if not report.chapters and report.skipped == 0:
        typer.echo("no chapters")
        return
    if len(report.chapters) < 2:
        typer.echo(f"chapters: {len(report.chapters)}")
        typer.echo("drift: n/a (need at least 2 chapters)")
        return

    forbidden_words = read_forbidden_words(db, workspace_id)
    typer.echo(f"chapters: {len(report.chapters)}")
    if report.baseline_title:
        typer.echo(f"baseline: {report.baseline_title}")
    if report.skipped > 0:
        typer.echo(f"skipped chapters: {report.skipped}")
    for chapter in report.chapters:
        parts = [
            f"len {chapter.avg_sentence_len:.1f}",
            f"short {chapter.short_sentence_ratio * 100:.1f}%",
            f"mod {chapter.modifier_per_1000:.1f}",
            f"ai {chapter.ai_words_per_1000:.1f}",
        ]
        if chapter.style_hits is not None:
            parts.append(f"style {chapter.style_hits}/{chapter.style_total}")
        typer.echo(
            f"{chapter.index} {chapter.title}: {' / '.join(parts)} → drift {chapter.drift_score}"
        )
    trend = " / ".join(str(chapter.drift_score) for chapter in report.chapters)
    typer.echo(f"drift trend: {trend}")
    if report.drifted:
        drifted = "、".join(
            f"{chapter.title}（{chapter.drift_score}）" for chapter in report.drifted
        )
        typer.echo(f"drifted chapters: {drifted}")
    for chapter in report.chapters:
        if chapter.forbidden_hits <= 0:
            continue
        words = "、".join(forbidden_words)
        typer.echo(f"forbidden hits: {chapter.title}: {chapter.forbidden_hits}（{words}）")
    typer.echo(f"verdict: {report.verdict}")
