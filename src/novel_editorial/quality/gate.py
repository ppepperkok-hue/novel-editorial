"""AI-flavor quality gate. Real detector lands in U13."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityReport:
    passed: bool
    score: float
    details: dict


def basic_gate(text: str, ai_words: set[str] | None = None) -> QualityReport:
    """Placeholder gate; always passes until U13 implements detection."""
    return QualityReport(passed=True, score=0.0, details={})
