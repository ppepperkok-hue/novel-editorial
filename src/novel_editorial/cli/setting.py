"""Setting command group."""

from __future__ import annotations

import typer

from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.impact import analyze_setting_impact, extract_keywords
from novel_editorial.core.setting import (
    KIND_LABELS,
    add_setting,
    check_settings,
    get_setting,
    list_setting_history,
    list_settings,
    revise_setting,
)
from novel_editorial.store.db import DB

setting_app = typer.Typer(help="Manage versioned world settings")


def _kind_from_label(label: str) -> str:
    """Map a Chinese kind label back to its canonical kind."""
    for kind, text in KIND_LABELS.items():
        if text == label:
            return kind
    expected = "、".join(KIND_LABELS.values())
    raise NovelError(
        ErrorCode.USAGE_ERROR, f"invalid kind: {label} (expected one of: {expected})"
    )


@setting_app.command("add")
def setting_add(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    kind: str = typer.Option(
        ..., "--kind", help="Setting kind: 人物/关系/时间线/世界观"
    ),
    name: str = typer.Option(..., "--name", help="Setting name"),
    content: str = typer.Option(..., "--content", help="Setting content"),
    source: str = typer.Option("作者", "--source", help="Source of the setting"),
) -> None:
    """Add a setting entry at version 1."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    entry = add_setting(
        db,
        workspace_id,
        kind=_kind_from_label(kind),
        name=name,
        content=content,
        source=source,
    )
    label = KIND_LABELS[entry.kind]
    typer.echo(f"added {entry.id} [{label}] {entry.name} v{entry.current_version}")


@setting_app.command("list")
def setting_list(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    kind: str | None = typer.Option(
        None, "--kind", help="Filter by kind label: 人物/关系/时间线/世界观"
    ),
) -> None:
    """List settings in a workspace, oldest first."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    kind_value = _kind_from_label(kind) if kind is not None else None
    entries = list_settings(db, workspace_id, kind=kind_value)
    if not entries:
        typer.echo("no settings yet")
        return
    for entry in entries:
        label = KIND_LABELS[entry.kind]
        typer.echo(
            f"{entry.id} [{label}] {entry.name} v{entry.current_version} {entry.content}"
        )


@setting_app.command("check")
def setting_check(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
) -> None:
    """Report stale settings and same-name conflict candidates."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    typer.echo(check_settings(db, workspace_id))


@setting_app.command("show")
def setting_show(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    setting_id: str = typer.Argument(..., help="Setting id"),
) -> None:
    """Show a setting with its latest version content."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    entry = get_setting(db, workspace_id, setting_id)
    label = KIND_LABELS[entry.kind]
    typer.echo(f"{entry.name} [{label}] v{entry.current_version}")
    typer.echo(f"source: {entry.source}")
    typer.echo("---")
    typer.echo(entry.content)


@setting_app.command("revise")
def setting_revise(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    setting_id: str = typer.Argument(..., help="Setting id"),
    content: str = typer.Option(..., "--content", help="New content"),
    reason: str = typer.Option(..., "--reason", help="Reason for the revision"),
    actor: str = typer.Option(
        "作者", "--actor", help="Actor making the revision"
    ),
) -> None:
    """Revise a setting: bump the version and record the change."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    entry = revise_setting(
        db,
        workspace_id,
        setting_id,
        content=content,
        reason=reason,
        actor=actor,
    )
    typer.echo(f"revised {entry.id} {entry.name} v{entry.current_version}")


@setting_app.command("history")
def setting_history(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    setting_id: str = typer.Argument(..., help="Setting id"),
) -> None:
    """Show every version of a setting, oldest first."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    versions = list_setting_history(db, workspace_id, setting_id)
    for version in versions:
        typer.echo(f"v{version.version} {version.actor} {version.reason} {version.content}")


@setting_app.command("impact")
def setting_impact(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    setting_id: str = typer.Argument(..., help="Setting id"),
    limit: int = typer.Option(
        20, "--limit", help="Max impact rows (default: 20)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", help="Print the keyword set used for matching"
    ),
) -> None:
    """Report which layers reference one setting (read-only)."""
    if limit < 1:
        raise NovelError(
            ErrorCode.USAGE_ERROR, f"limit must be at least 1, got {limit}"
        )
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    report = analyze_setting_impact(db, workspace_id, setting_id, limit=limit)
    if verbose:
        entry = get_setting(db, workspace_id, setting_id)
        keywords = extract_keywords(entry.name, entry.content)
        typer.echo(f"keywords: {'、'.join(keywords)}")
    if report.total == 0:
        typer.echo(
            f"no impact found for {report.setting_name} v{report.setting_version}"
        )
        return
    typer.echo(
        f"impact for {report.setting_name} v{report.setting_version}"
        f"（共 {report.total} 条）："
    )
    for item in report.impacts:
        typer.echo(f"[{item.layer}] {item.source}：{item.snippet}")
