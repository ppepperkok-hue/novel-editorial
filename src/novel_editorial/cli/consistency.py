"""Consistency check command group."""

from __future__ import annotations

import typer

from novel_editorial.core.config import load_settings
from novel_editorial.core.consistency import check_consistency
from novel_editorial.core.draft import find_draft_anywhere, get_draft_version
from novel_editorial.store.db import DB

consistency_app = typer.Typer(help="Consistency checks")


@consistency_app.command("check")
def consistency_check(draft_id: str = typer.Argument(..., help="Draft id")) -> None:
    """Check the latest draft version against settings and open threads (read-only)."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    version = get_draft_version(db, draft.workspace_id, draft_id, draft.current_version)
    report = check_consistency(db, draft.workspace_id, version.content)
    typer.echo(
        f"settings checked: {report.settings_checked} / "
        f"threads checked: {report.threads_checked}"
    )
    for name, count in report.character_mentions.items():
        typer.echo(f"[人物] {name}：出现 {count} 次")
    if not report.issues:
        typer.echo("no consistency issues found")
        return
    for issue in report.issues:
        if issue.kind == "number_conflict":
            typer.echo(f"[冲突] {issue.setting_name}：{issue.detail}")
        elif issue.kind == "character_missing":
            typer.echo(f"[未提及] {issue.setting_name}：{issue.detail}")
        else:
            typer.echo(f"[未提及] 伏笔·{issue.setting_name}：{issue.detail}")
