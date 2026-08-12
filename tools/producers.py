"""Producer registry: decouple the workday from any specific production chain.

A producer turns a workday plan into a produce result. The workday only knows
producer names from the plan; it never imports a domain chain directly.

Registry:
    novel  -> the net-novel daily chain (current production line)
    none   -> no production (org/meeting days)

New domains register their own producer here (or in their own module) and the
workday picks it up by name with zero changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def produce_novel(
    conn,
    *,
    target=None,
    trigger="manual",
    dry_run=False,
    db_path=None,
    workday_run_id=None,
    lock_held=False,
    skip_diaries=False,
    **kwargs,
):
    """Net-novel daily production chain (the existing editorial_daily line)."""
    from tools import editorial_daily  # local import keeps module load domain-free

    return editorial_daily.daily(
        conn,
        chapters=target,
        trigger=trigger,
        dry_run=dry_run,
        db_path=db_path,
        workday_run_id=workday_run_id,
        lock_held=lock_held,
        skip_diaries=skip_diaries,
    )


def produce_none(conn, *, target=None, **kwargs):
    """No production: org/meeting days return a skipped result."""
    return {"status": "skipped", "published": 0}


def produce_article(conn, *, target=None, **kwargs):
    """Generic article chain: plan -> write -> polish -> review -> save to disk."""
    from tools import produce_article as _article

    return _article.produce_article(conn, target=target, **kwargs)


PRODUCERS = {
    "novel": produce_novel,
    "article": produce_article,
    "none": produce_none,
}


def run_producer(name, conn, **kwargs):
    """Dispatch to a registered producer by name; unknown names raise."""
    fn = PRODUCERS.get(name)
    if fn is None:
        raise ValueError(f"unknown producer: {name!r}")
    return fn(conn, **kwargs)
