"""Patience command group (N28-E S4): show each partner's patience pool."""

from __future__ import annotations

import typer

from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.config import load_settings
from novel_editorial.core.patience import STATE_KEYS, patience_pools
from novel_editorial.store.db import DB

patience_app = typer.Typer(help="Inspect partner patience pools")


@patience_app.command("show")
def patience_show(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """Show every partner's patience pool and the three state breakdowns."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    pools = patience_pools(db, workspace_id)
    for pool in pools:
        states = pool["states"]
        typer.echo(
            f"[{pool['agent_name']}] pool={pool['pool']} "
            f"patience={pool['effective_patience']} consumed={pool['consumption']} "
            f"rejected={states['rejected']} overridden={states['overridden']} "
            f"conflict={states['conflict']}"
        )
        for state in STATE_KEYS:
            for entry in pool["entries"][state]:
                typer.echo(
                    f"  {state}: {entry.target}: {entry.summary} "
                    f"(source={entry.source})"
                )
