"""AI-flavor quality gate: word-list hits and modifier density."""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class QualityReport:
    passed: bool
    score: float
    details: dict


def check_quality(
    text: str,
    *,
    threshold: int = 8,
    ai_words: frozenset[str] = DEFAULT_AI_WORDS,
    modifiers: frozenset[str] = DEFAULT_MODIFIERS,
) -> QualityReport:
    """Score AI flavor and decide whether the text passes the gate."""
    ai_hits = sorted(word for word in ai_words if word in text)
    modifier_hits = sorted(word for word in modifiers if word in text)
    score = len(ai_hits) * AI_WORD_WEIGHT + len(modifier_hits) * MODIFIER_WEIGHT
    details = {
        "ai_word_hits": ai_hits,
        "modifier_hits": modifier_hits,
        "score": score,
        "threshold": threshold,
    }
    return QualityReport(passed=score <= threshold, score=score, details=details)
