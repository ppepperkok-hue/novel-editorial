"""Corpus calibration service: sample scanning and score distribution."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.quality.gate import check_quality

CORPUS_EXTENSIONS = {".txt", ".md"}


def is_valid_corpus_file(path: Path) -> bool:
    """Return True when path is a non-hidden regular file with a corpus extension."""
    return (
        path.is_file()
        and path.suffix.lower() in CORPUS_EXTENSIONS
        and not path.name.startswith(".")
    )


def read_sample(path: Path) -> str:
    """Read a corpus file as UTF-8 text, stripping a UTF-8 BOM if present.

    Raises NovelError(USAGE_ERROR) with the file path in the message and context
    when the file cannot be read or decoded. USAGE_ERROR is the closest existing
    code: the corpus comes from the user, so an unreadable file is a usage
    problem rather than a NOT_FOUND or INTERNAL failure.
    """
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"cannot read corpus file: {path}",
            context={"path": str(path)},
        ) from exc
    except UnicodeDecodeError as exc:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"corpus file is not valid UTF-8: {path}",
            context={"path": str(path)},
        ) from exc


@dataclass(frozen=True)
class CorpusSample:
    path: Path
    char_count: int
    ai_word_hits: int
    modifier_hits: int
    sentence_repetition: int
    score: float


@dataclass(frozen=True)
class CorpusReport:
    samples: list[CorpusSample]
    scores: list[float]
    min: float
    median: float
    p90: float
    p95: float
    max: float
    suggested_threshold: int
    skipped: int
    errors: list[str] = field(default_factory=list)


def _distribution(scores: list[float]) -> tuple[float, float, float, float, float]:
    """Compute deterministic min / median / p90 / p95 / max from scores.

    Percentiles use the nearest-rank method on sorted scores: for fraction p,
    rank = ceil(p * n) with 1-based indexing. Median of an even count is the
    average of the two middle values.
    """
    ordered = sorted(scores)
    n = len(ordered)
    midpoint = n // 2
    if n % 2 == 1:
        median = ordered[midpoint]
    else:
        median = (ordered[midpoint - 1] + ordered[midpoint]) / 2
    p90 = ordered[math.ceil(0.9 * n) - 1]
    p95 = ordered[math.ceil(0.95 * n) - 1]
    return ordered[0], median, p90, p95, ordered[-1]


def scan_corpus(path: Path | str) -> CorpusReport:
    """Scan a corpus and compute a deterministic score distribution.

    path may be a single non-hidden .txt/.md file or a directory scanned
    recursively. Every valid file is one sample scored by check_quality with the
    default word lists and no style keywords. Blank files, hidden corpus files
    and files that fail to read are skipped; read failures are also recorded in
    report.errors so they stay visible without aborting the scan. Files without
    a corpus extension are not candidates and never count as skipped.

    A missing path raises NovelError(NOT_FOUND), the closest existing code for
    "path does not exist". A path with no valid samples (empty directory, or a
    single file that is not a non-hidden .txt/.md, or only blank / unreadable
    files) raises NovelError(USAGE_ERROR): an empty corpus cannot produce a
    meaningful threshold, which is a usage problem. Both codes are chosen from
    the existing ErrorCode enum without adding new ones.

    suggested_threshold = max(1, ceil(p90)) keeps the gate meaningful even for
    a fully clean corpus.
    """
    root = Path(path)
    if not root.exists():
        raise NovelError(
            ErrorCode.NOT_FOUND,
            f"corpus path not found: {root}",
            context={"path": str(root)},
        )

    if root.is_file():
        if not is_valid_corpus_file(root):
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                "single-file corpus must be a non-hidden .txt/.md file",
                context={"path": str(root)},
            )
        candidates = [root]
    else:
        candidates = sorted(
            (
                candidate
                for candidate in root.rglob("*")
                if candidate.is_file() and candidate.suffix.lower() in CORPUS_EXTENSIONS
            ),
            key=str,
        )

    samples: list[CorpusSample] = []
    errors: list[str] = []
    skipped = 0

    for candidate in candidates:
        if not is_valid_corpus_file(candidate):
            skipped += 1
            continue
        try:
            text = read_sample(candidate)
        except NovelError as exc:
            skipped += 1
            errors.append(str(exc))
            continue
        stripped = "".join(text.split())
        if not stripped:
            skipped += 1
            continue
        details = check_quality(text).details
        samples.append(
            CorpusSample(
                path=candidate,
                char_count=len(stripped),
                ai_word_hits=len(details["ai_word_hits"]),
                modifier_hits=len(details["modifier_hits"]),
                sentence_repetition=details["sentence_repetition"],
                score=details["score"],
            )
        )

    if not samples:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"corpus contains no readable samples: {root}",
            context={"path": str(root), "skipped": skipped, "errors": errors},
        )

    sample_scores = [sample.score for sample in samples]
    stats_min, median, p90, p95, stats_max = _distribution(sample_scores)
    return CorpusReport(
        samples=samples,
        scores=sample_scores,
        min=stats_min,
        median=median,
        p90=p90,
        p95=p95,
        max=stats_max,
        suggested_threshold=max(1, math.ceil(p90)),
        skipped=skipped,
        errors=errors,
    )
