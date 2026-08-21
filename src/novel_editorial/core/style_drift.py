"""Style drift detection across chapters (N21 S1).

The service is deterministic and strictly read-only: it never records events,
never writes to the database (a missing style anchor is treated as having no
keywords rather than being created), and never triggers proactive behavior.
Chapters are collected from the structure tree when chapter nodes carry a
draft id, otherwise from all drafts ordered by ``created_at``, ``id``. Each
chapter is profiled with :func:`compute_style_profile` and scored against the
first analyzable chapter (the baseline), whose deviations are all zero.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.draft import get_draft, get_draft_version, list_drafts
from novel_editorial.core.structure import KIND_CHAPTER, list_structure
from novel_editorial.core.style import extract_style_keywords
from novel_editorial.core.style_learn import StyleProfile, compute_style_profile
from novel_editorial.store.db import DB
from novel_editorial.store.models import StyleAnchor

DRIFT_THRESHOLD = 50
UNTITLED_CHAPTER = "未命名章节"
_FORBIDDEN_SPLIT_RE = re.compile(r"[,，]")


@dataclass(frozen=True)
class DriftChapter:
    """One analyzed chapter with per-chapter style metrics and drift score."""

    index: int
    title: str
    draft_id: str
    avg_sentence_len: float
    short_sentence_ratio: float
    modifier_per_1000: float
    ai_words_per_1000: float
    style_hits: int | None
    style_total: int | None
    forbidden_hits: int
    drift_score: int
    drifted: bool


@dataclass(frozen=True)
class DriftReport:
    """Deterministic cross-chapter style drift report."""

    chapters: list[DriftChapter]
    baseline_title: str
    skipped: int
    threshold: int = DRIFT_THRESHOLD
    drifted: list[DriftChapter] = field(default_factory=list)
    verdict: str = ""


@dataclass(frozen=True)
class _CollectedChapter:
    """One ordered chapter with its draft body before profiling."""

    title: str
    draft_id: str
    content: str


def compute_style_drift(db: DB, workspace_id: str) -> DriftReport:
    """Compute a read-only style drift report for one workspace.

    Chapters with ``total_chars == 0`` are skipped and counted in
    ``skipped``. Verdicts are fixed: ``"no chapters"``, ``"need at least 2
    chapters"``, ``"drift detected in N chapters"`` (N in English digits) or
    ``"style stable"``. A missing workspace raises ``NovelError(NOT_FOUND)``.
    """
    get_workspace_or_raise(db, workspace_id)
    collected = _ordered_chapters(db, workspace_id)
    if not collected:
        return DriftReport(
            chapters=[],
            baseline_title="",
            skipped=0,
            drifted=[],
            verdict="no chapters",
        )

    description, forbidden_raw = _read_style_anchor(db, workspace_id)
    keywords = extract_style_keywords(description)
    forbidden_words = _split_forbidden_words(forbidden_raw)

    analyzed: list[tuple[_CollectedChapter, StyleProfile]] = []
    skipped = 0
    for chapter in collected:
        profile = compute_style_profile([chapter.content])
        if profile.total_chars == 0:
            skipped += 1
            continue
        analyzed.append((chapter, profile))

    chapters: list[DriftChapter] = []
    drifted: list[DriftChapter] = []
    baseline_title = ""
    if analyzed:
        baseline, baseline_profile = analyzed[0]
        baseline_title = baseline.title
        baseline_ai = _ai_words_per_1000(baseline_profile)
        baseline_style_hits = (
            sum(1 for keyword in keywords if keyword in baseline.content) if keywords else None
        )
        for index, (chapter, profile) in enumerate(analyzed, start=1):
            ai_per_1000 = _ai_words_per_1000(profile)
            baseline_len = baseline_profile.avg_sentence_len
            baseline_mod = baseline_profile.modifier_per_1000
            style_hits: int | None = None
            style_total = 0
            if keywords:
                style_hits = sum(1 for keyword in keywords if keyword in chapter.content)
                style_total = len(keywords)
            deviations = [
                min(1.0, abs(profile.avg_sentence_len - baseline_len) / max(baseline_len, 6.0)),
                abs(profile.short_sentence_ratio - baseline_profile.short_sentence_ratio),
                min(1.0, abs(profile.modifier_per_1000 - baseline_mod) / max(baseline_mod, 1.0)),
                min(1.0, abs(ai_per_1000 - baseline_ai) / max(baseline_ai, 0.5)),
            ]
            if keywords and style_hits is not None and baseline_style_hits is not None:
                deviations.append(abs(style_hits / style_total - baseline_style_hits / style_total))
            score = round(100 * sum(deviations) / len(deviations))
            is_drifted = index > 1 and score >= DRIFT_THRESHOLD
            drift_chapter = DriftChapter(
                index=index,
                title=chapter.title,
                draft_id=chapter.draft_id,
                avg_sentence_len=profile.avg_sentence_len,
                short_sentence_ratio=profile.short_sentence_ratio,
                modifier_per_1000=profile.modifier_per_1000,
                ai_words_per_1000=ai_per_1000,
                style_hits=style_hits,
                style_total=style_total,
                forbidden_hits=sum(chapter.content.count(word) for word in forbidden_words),
                drift_score=score,
                drifted=is_drifted,
            )
            chapters.append(drift_chapter)
            if is_drifted:
                drifted.append(drift_chapter)

    if len(analyzed) < 2:
        verdict = "need at least 2 chapters"
    elif drifted:
        verdict = f"drift detected in {len(drifted)} chapters"
    else:
        verdict = "style stable"

    return DriftReport(
        chapters=chapters,
        baseline_title=baseline_title,
        skipped=skipped,
        drifted=drifted,
        verdict=verdict,
    )


def _ordered_chapters(db: DB, workspace_id: str) -> list[_CollectedChapter]:
    """Collect chapters in reading order (structure first, then drafts)."""
    nodes = list_structure(db, workspace_id)
    attached: list[tuple[str, str]] = []
    for node in nodes:
        if node.kind != KIND_CHAPTER:
            continue
        draft_id = node.draft_id
        if not draft_id:
            continue
        attached.append((node.title, draft_id))

    if attached:
        chapters: list[_CollectedChapter] = []
        for title, draft_id in attached:
            draft = get_draft(db, workspace_id, draft_id)
            version = get_draft_version(db, workspace_id, draft.id, draft.current_version)
            chapters.append(
                _CollectedChapter(title=title, draft_id=draft.id, content=version.content)
            )
        return chapters

    drafts = sorted(list_drafts(db, workspace_id), key=lambda draft: (draft.created_at, draft.id))
    chapters = []
    for draft in drafts:
        version = get_draft_version(db, workspace_id, draft.id, draft.current_version)
        title = draft.title.strip() or UNTITLED_CHAPTER
        chapters.append(_CollectedChapter(title=title, draft_id=draft.id, content=version.content))
    return chapters


def _read_style_anchor(db: DB, workspace_id: str) -> tuple[str, str]:
    """Read description and forbidden words without creating a missing anchor."""
    with db.workspace_session(workspace_id) as session:
        anchor = (
            session.query(StyleAnchor)
            .filter_by(workspace_id=workspace_id)
            .first()
        )
        if anchor is None:
            return "", ""
        return anchor.description, anchor.forbidden_words


def _split_forbidden_words(text: str) -> list[str]:
    """Split forbidden words on ASCII/Chinese commas, dropping blanks and dupes."""
    words: list[str] = []
    seen: set[str] = set()
    for raw in _FORBIDDEN_SPLIT_RE.split(text):
        word = raw.strip()
        if not word or word in seen:
            continue
        seen.add(word)
        words.append(word)
    return words


def _ai_words_per_1000(profile: StyleProfile) -> float:
    if profile.total_chars == 0:
        return 0.0
    return len(profile.ai_word_hits) * 1000 / profile.total_chars
