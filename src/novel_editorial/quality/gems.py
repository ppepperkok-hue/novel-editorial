"""Good-sentence spotting: deterministic signals that hint at concrete detail.

The AI-flavor gate tells the author what to rewrite; this module tells them
what to keep. Detection is purely rule-based and never consults gate scores,
so an AI-flavored sentence that still carries concrete detail can be flagged
as a good sentence too.

Sensory hits are a starting point, not a verdict: they only hint at concrete
physical detail, and the author keeps final judgment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from novel_editorial.quality.gate import split_sentences

SIGNAL_DIALOGUE = "dialogue"
SIGNAL_NUMBER_DETAIL = "number_detail"
SIGNAL_SENSORY = "sensory"

# Dialogue signal: any of the CJK/curly quote characters.
DIALOGUE_QUOTE_CHARS = frozenset("「」『』“”‘’")
_OPEN_QUOTE_CHARS = frozenset("「『“‘")
_CLOSE_QUOTE_CHARS = frozenset("」』”’")

# Sensory signal: single-character hints of concrete physical detail
# (24 chars). These are hints, not verdicts.
SENSORY_DETAIL_WORDS = frozenset("光影声味汗血锈霜雪雨风烟尘灰铁灯钟门窗锁刀火水石")

_NUMERAL_CHARS = "零一二三四五六七八九十百千两"
_NUMBER_UNIT_CHARS = "点时分年月日岁号秒米里斤两钱块元"
_NUMBER_DETAIL_RE = re.compile(rf"[0-9{_NUMERAL_CHARS}]+[{_NUMBER_UNIT_CHARS}]")


@dataclass(frozen=True)
class GoodSentence:
    """A sentence flagged as a good-sentence candidate.

    Attributes:
        index: 1-based sentence index in the source text.
        snippet: The sentence itself (as returned by split_sentences).
        signals: Matched signal labels, deduplicated in fixed order.
    """

    index: int
    snippet: str
    signals: list[str]


def _sentence_signals(sentence: str) -> list[str]:
    """Return matched signal labels for one sentence in fixed order."""
    signals: list[str] = []
    if any(char in DIALOGUE_QUOTE_CHARS for char in sentence):
        signals.append(SIGNAL_DIALOGUE)
    if _NUMBER_DETAIL_RE.search(sentence) is not None:
        signals.append(SIGNAL_NUMBER_DETAIL)
    if any(char in SENSORY_DETAIL_WORDS for char in sentence):
        signals.append(SIGNAL_SENSORY)
    return signals


def find_good_sentences(text: str) -> list[GoodSentence]:
    """Return good-sentence candidates in sentence order.

    A sentence is a candidate when it carries at least one concrete-detail
    signal; every matched signal is listed (deduplicated, fixed order).
    Empty or signal-free text returns an empty list.

    split_sentences cuts at terminal punctuation inside quotes, so an
    unfinished quote fragment (e.g. "「别开灯" followed by "」他说") is merged
    back into a single GoodSentence: index keeps the first fragment, snippet
    concatenates both, and signals are merged. A following fragment only merges
    when it starts with a close quote and contains no open quote. Fragments
    that start with a close quote and cannot merge are quote residue, not
    sentences, and are always skipped, so no gem ever starts with a close
    quote.
    """
    gems: list[GoodSentence] = []
    pending: GoodSentence | None = None

    def flush() -> None:
        nonlocal pending
        if pending is not None:
            gems.append(pending)
            pending = None

    for index, sentence in enumerate(split_sentences(text), start=1):
        signals = _sentence_signals(sentence)
        starts_with_close = bool(sentence) and sentence[0] in _CLOSE_QUOTE_CHARS
        contains_open = any(char in _OPEN_QUOTE_CHARS for char in sentence)
        if pending is not None and starts_with_close and not contains_open:
            merged_snippet = pending.snippet + sentence
            pending = GoodSentence(
                index=pending.index,
                snippet=merged_snippet,
                signals=_sentence_signals(merged_snippet),
            )
            continue
        flush()
        if starts_with_close:
            continue
        if signals:
            if contains_open:
                pending = GoodSentence(index=index, snippet=sentence, signals=signals)
            else:
                gems.append(GoodSentence(index=index, snippet=sentence, signals=signals))
    flush()
    return gems
