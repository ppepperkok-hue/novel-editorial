"""Trial-reader feedback flow: annotated JSONL parsing and gate alignment analysis."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.quality.gate import check_quality


@dataclass(frozen=True)
class FeedbackSample:
    """One annotated trial-reader sample with its source line for error reporting."""

    label: str
    text: str
    line: int


@dataclass(frozen=True)
class FeedbackReport:
    """Alignment report between reader annotations and the quality gate."""

    samples: list[FeedbackSample]
    bad_count: int
    good_count: int
    bad_stats: tuple[float, ...]
    good_stats: tuple[float, ...]
    threshold_used: int
    agreement: float
    suggested_threshold: int | None
    suggested_agreement: float | None


def _stats(scores: list[float]) -> tuple[float, ...]:
    """Return (min, median, p90, max) with calibration's nearest-rank percentiles.

    Matches core.calibration._distribution semantics: p90 uses rank
    ceil(0.9 * n) on sorted scores, and the median of an even count is the mean
    of the two middle values. An empty group yields an empty tuple.
    """
    if not scores:
        return ()
    ordered = sorted(scores)
    n = len(ordered)
    midpoint = n // 2
    if n % 2 == 1:
        median = ordered[midpoint]
    else:
        median = (ordered[midpoint - 1] + ordered[midpoint]) / 2
    p90 = ordered[math.ceil(0.9 * n) - 1]
    return (ordered[0], median, p90, ordered[-1])


def load_feedback_samples(path: str | Path) -> list[FeedbackSample]:
    """Load one JSONL file of annotated samples, one JSON object per line.

    Each line is `{"label": "bad"|"good", "text": "..."}`; text may contain
    escaped newlines. Blank lines are skipped and surrounding whitespace on a
    line is tolerated. A missing path raises NovelError(NOT_FOUND); an invalid
    line (bad JSON, a non-object value, an unknown or missing label, or a blank
    text) raises NovelError(USAGE_ERROR) with the 1-based line number in the
    message; a file with no valid samples raises NovelError(USAGE_ERROR).
    """
    root = Path(path)
    if not root.exists():
        raise NovelError(
            ErrorCode.NOT_FOUND,
            f"feedback file not found: {root}",
            context={"path": str(root)},
        )
    try:
        raw = root.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"cannot read feedback file: {root}",
            context={"path": str(root)},
        ) from exc
    except UnicodeDecodeError as exc:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"feedback file is not valid UTF-8: {root}",
            context={"path": str(root)},
        ) from exc

    samples: list[FeedbackSample] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                f"feedback file line {line_number}: invalid JSON: {root}",
                context={"path": str(root), "line": line_number},
            ) from exc
        if not isinstance(data, dict):
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                f"feedback file line {line_number}: expected a JSON object: {root}",
                context={"path": str(root), "line": line_number},
            )
        label = data.get("label")
        if label not in ("bad", "good"):
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                f"feedback file line {line_number}: label must be 'bad' or 'good': {root}",
                context={"path": str(root), "line": line_number},
            )
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                f"feedback file line {line_number}: text must be a non-empty string: {root}",
                context={"path": str(root), "line": line_number},
            )
        samples.append(FeedbackSample(label=label, text=text, line=line_number))

    if not samples:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"feedback file contains no valid samples: {root}",
            context={"path": str(root)},
        )
    return samples


def analyze_feedback(samples: list[FeedbackSample], threshold: int) -> FeedbackReport:
    """Score every sample with check_quality and compare annotations to the gate.

    A sample is gate-bad when score > threshold; agreement is the fraction of
    samples whose annotation matches the gate verdict. When bad samples exist,
    the suggested threshold maximizes agreement over the candidate set of all
    sample scores plus the current threshold; ties are broken toward the higher
    threshold (more conservative). suggested_agreement is the agreement at that
    threshold; without bad samples both are None, because there is no evidence
    for raising the gate. Empty input yields a report with empty stats, 0.0
    agreement and no suggestion.
    """
    scored = [(sample, check_quality(sample.text).score) for sample in samples]
    if not scored:
        return FeedbackReport(
            samples=[],
            bad_count=0,
            good_count=0,
            bad_stats=(),
            good_stats=(),
            threshold_used=threshold,
            agreement=0.0,
            suggested_threshold=None,
            suggested_agreement=None,
        )

    bad_scores = [score for sample, score in scored if sample.label == "bad"]
    good_scores = [score for sample, score in scored if sample.label == "good"]
    bad_stats = _stats(bad_scores)
    good_stats = _stats(good_scores)
    total = len(scored)

    def agreement_at(gate_threshold: int | float) -> float:
        return (
            sum(
                1
                for sample, score in scored
                if (sample.label == "bad") == (score > gate_threshold)
            )
            / total
        )

    agreement = agreement_at(threshold)
    suggested_threshold: int | None = None
    suggested_agreement: float | None = None
    if bad_scores:
        candidates = sorted({score for _, score in scored} | {float(threshold)})
        best = max(
            candidates,
            key=lambda candidate: (agreement_at(candidate), candidate),
        )
        suggested_threshold = int(best)
        suggested_agreement = agreement_at(suggested_threshold)

    return FeedbackReport(
        samples=samples,
        bad_count=len(bad_scores),
        good_count=len(good_scores),
        bad_stats=bad_stats,
        good_stats=good_stats,
        threshold_used=threshold,
        agreement=agreement,
        suggested_threshold=suggested_threshold,
        suggested_agreement=suggested_agreement,
    )
