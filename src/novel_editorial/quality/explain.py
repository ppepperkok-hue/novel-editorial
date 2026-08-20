"""Sentence-level AI-flavor explanation with rule-based rewrite suggestions."""

from __future__ import annotations

from dataclasses import dataclass

from novel_editorial.quality.gate import (
    DEFAULT_AI_WORDS,
    DEFAULT_MODIFIERS,
    sentence_endings,
    split_sentences,
)

AI_WORD_SUGGESTIONS: dict[str, str] = {
    "宛如": "用具体比喻或直接写物象",
    "仿佛": "直接写本体，去掉「仿佛」",
    "不禁": "写具体动作，删掉「不禁」",
    "悄然": "换成具体动作或声音",
    "瞬间": "直接写那一刻发生了什么",
    "璀璨": "换成具体的光或物象",
    "缱绻": "换成具体互动或细节",
    "氤氲": "换成具体的气味、雾气或颜色",
    "曼妙": "换成具体的姿态或动作",
    "呢喃": "换成具体的说话内容或声音",
    "萦绕": "换成具体的听觉或嗅觉细节",
    "凛冽": "换成具体的温度或风感",
    "深邃": "换成具体的深度或眼神细节",
    "斑斓": "换成具体的颜色",
    "熠熠": "换成具体的光源或亮度",
    "静谧": "换成具体的声音细节",
    "怅然": "换成具体的表情或动作",
    "悠远": "换成具体的距离或声音",
    "缥缈": "换成具体的事物形态",
    "婆娑": "换成具体的枝叶或身影动作",
    "刹那": "直接写事件，删掉「刹那」",
    "苍穹": "换成「天」或具体的天空细节",
    "潋滟": "换成具体的水光描写",
    "旖旎": "换成具体的景物细节",
}

MODIFIER_DENSITY_THRESHOLD = 2
MODIFIER_DENSITY_SUGGESTION = "同一句修饰词太多，保留一个，其余换成具体动作或名词"

CLEAN_MESSAGE = "未发现明显 AI 味"

KIND_LABELS = {
    "ai_word": "AI 词命中",
    "modifier_density": "修饰词密度",
    "sentence_repetition": "句式重复",
}


@dataclass(frozen=True)
class ExplanationIssue:
    sentence: int
    snippet: str
    kind: str
    word: str | None
    suggestion: str


def ai_word_suggestion(word: str) -> str:
    """Return the rewrite suggestion for one AI-flavor word."""
    return AI_WORD_SUGGESTIONS.get(word, f"删掉「{word}」，换成具体动作或感官细节")


def style_consistency_summary(
    text: str,
    style_keywords: frozenset[str],
) -> str | None:
    """Summarize how many style keywords appear in the text.

    Mirrors check_quality's style_hits semantics: a keyword counts as a hit
    when it appears anywhere in the text. Returns None when no style keywords
    are supplied so callers can omit the summary line entirely.
    """
    if not style_keywords:
        return None
    total = len(style_keywords)
    hits = sorted(keyword for keyword in style_keywords if keyword in text)
    misses = sorted(keyword for keyword in style_keywords if keyword not in text)
    if not misses:
        return f"style: 命中 {total}/{total}"
    hit_part = f"（{'、'.join(hits)}）" if hits else ""
    return f"style: 命中 {len(hits)}/{total}{hit_part}；缺失：{'、'.join(misses)}"


def explain_quality(
    text: str,
    *,
    ai_words: frozenset[str] = DEFAULT_AI_WORDS,
    modifiers: frozenset[str] = DEFAULT_MODIFIERS,
) -> list[ExplanationIssue]:
    """Locate AI-flavor issues per sentence and attach rewrite suggestions."""
    sentences = split_sentences(text)
    repetition_notes: dict[int, str] = {}
    for ending, positions in sentence_endings(sentences).items():
        if len(positions) < 2:
            continue
        for position in positions[1:]:
            repetition_notes[position] = (
                f"句尾「{ending}」与第 {positions[0]} 句重复，改写结尾动词或调整句式"
            )

    issues: list[ExplanationIssue] = []
    for index, sentence in enumerate(sentences, start=1):
        for word in sorted({word for word in ai_words if word in sentence}):
            issues.append(
                ExplanationIssue(index, sentence, "ai_word", word, ai_word_suggestion(word))
            )
        modifier_occurrences = sum(sentence.count(word) for word in modifiers)
        if modifier_occurrences >= MODIFIER_DENSITY_THRESHOLD:
            issues.append(
                ExplanationIssue(
                    index,
                    sentence,
                    "modifier_density",
                    None,
                    MODIFIER_DENSITY_SUGGESTION,
                )
            )
        if index in repetition_notes:
            issues.append(
                ExplanationIssue(
                    index,
                    sentence,
                    "sentence_repetition",
                    None,
                    repetition_notes[index],
                )
            )
    return issues


def render_explanation(issues: list[ExplanationIssue]) -> str:
    """Render issues grouped by sentence with the original text and suggestions."""
    if not issues:
        return CLEAN_MESSAGE
    by_sentence: dict[int, list[ExplanationIssue]] = {}
    for issue in issues:
        by_sentence.setdefault(issue.sentence, []).append(issue)
    lines: list[str] = []
    for index in sorted(by_sentence):
        issues_for_sentence = by_sentence[index]
        lines.append(f"句 {index}: {issues_for_sentence[0].snippet}")
        for issue in issues_for_sentence:
            word_part = f"「{issue.word}」" if issue.word else ""
            lines.append(f"  - [{KIND_LABELS[issue.kind]}]{word_part} → {issue.suggestion}")
    return "\n".join(lines)
