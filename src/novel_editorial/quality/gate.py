"""AI-flavor quality gate: word-list hits, modifier density, repetition, style fit."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

DEFAULT_AI_WORDS: frozenset[str] = frozenset(
    {
        "宛如",
        "仿佛",
        "不禁",
        "悄然",
        "瞬间",
        "璀璨",
        "缱绻",
        "氤氲",
        "曼妙",
        "呢喃",
        "萦绕",
        "凛冽",
        "深邃",
        "斑斓",
        "熠熠",
        "静谧",
        "怅然",
        "悠远",
        "缥缈",
        "婆娑",
        "刹那",
        "苍穹",
        "潋滟",
        "旖旎",
    }
)

DEFAULT_MODIFIERS: frozenset[str] = frozenset(
    {
        "静静",
        "缓缓",
        "轻轻",
        "深深",
        "淡淡",
        "微微",
        "渐渐",
        "悄悄",
        "默默",
        "狠狠",
        "幽幽",
        "怔怔",
        "茫茫",
        "隐隐",
        "袅袅",
    }
)

AI_WORD_WEIGHT = 6
MODIFIER_WEIGHT = 3
REPETITION_WEIGHT = 4
STYLE_MISS_WEIGHT = 0.5

_SENTENCE_SPLIT_RE = re.compile(r"[。！？；…!?;\n]+")
_PUNCT_RE = re.compile(r"[，,、。！？；…!?;\s]+")


@dataclass(frozen=True)
class QualityReport:
    passed: bool
    score: float
    details: dict[str, Any]


def split_sentences(text: str) -> list[str]:
    """Split prose into non-empty sentences on terminal punctuation."""
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]


def sentence_endings(sentences: list[str]) -> dict[str, list[int]]:
    """Map each 3-char sentence ending to the 1-based indexes of sentences sharing it."""
    endings: dict[str, list[int]] = {}
    for index, sentence in enumerate(sentences, start=1):
        core = _PUNCT_RE.sub("", sentence)
        if len(core) >= 3:
            endings.setdefault(core[-3:], []).append(index)
    return endings


def count_sentence_repetition(text: str) -> int:
    """Count redundant endings: sentences beyond the first sharing a 3-char ending."""
    endings = sentence_endings(split_sentences(text))
    return sum(len(positions) - 1 for positions in endings.values() if len(positions) >= 2)


def check_quality(
    text: str,
    *,
    threshold: int = 8,
    ai_words: frozenset[str] = DEFAULT_AI_WORDS,
    modifiers: frozenset[str] = DEFAULT_MODIFIERS,
    style_keywords: frozenset[str] = frozenset(),
) -> QualityReport:
    """Score AI flavor and decide whether the text passes the gate."""
    ai_hits = sorted(word for word in ai_words if word in text)
    modifier_hits = sorted(word for word in modifiers if word in text)
    repetition = count_sentence_repetition(text)
    style_hits = sorted(keyword for keyword in style_keywords if keyword in text)
    missing_style = len(style_keywords) - len(style_hits)
    consistency = len(style_hits) / len(style_keywords) if style_keywords else 1.0
    score = (
        len(ai_hits) * AI_WORD_WEIGHT
        + len(modifier_hits) * MODIFIER_WEIGHT
        + repetition * REPETITION_WEIGHT
        + missing_style * STYLE_MISS_WEIGHT
    )
    details: dict[str, Any] = {
        "ai_word_hits": ai_hits,
        "modifier_hits": modifier_hits,
        "sentence_repetition": repetition,
        "style_hits": style_hits,
        "style_keyword_total": len(style_keywords),
        "style_consistency": consistency,
        "score": score,
        "threshold": threshold,
    }
    return QualityReport(passed=score <= threshold, score=score, details=details)
