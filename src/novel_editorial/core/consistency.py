"""Rule-based draft consistency checks against settings and open threads (N19 C1).

The service is deterministic and strictly read-only: it never records events
and never mutates the database. The same input always produces the same
report.

Checks
------
- ``character_missing``: a ``character`` setting whose name never appears in
  the text. Appearing names are recorded in ``character_mentions`` and do not
  produce issues.
- ``number_conflict``: a ``timeline`` / ``world`` / ``character`` setting that
  states a number+unit pair, when a sentence that also mentions the topic word
  (the entry name, plus any ``前缀：`` prefix found in the content) uses a value
  that is absent from the setting's value set for that unit. Arabic and Chinese
  numerals (including 两) are normalized to integers; supported units are
  点/时/分/年/月/日/岁/号. Values already present in the setting, different
  units, and sentences without the topic word are never reported.
- ``thread_missing``: an open (``planted`` / ``pending``) plot thread whose
  keywords never appear in the text.

Keyword extraction follows the spec's recommended option: the 2-4 char n-gram
set of the thread content; content that normalizes to a single character uses
that character as its only keyword. Whitespace and punctuation are stripped
from both the content and the text before n-gram generation and substring
matching.

Report counts: ``settings_checked`` counts the entries that actually
participate in a check (kind in ``character`` / ``timeline`` / ``world``;
``relation`` entries are never consulted); ``threads_checked`` counts open
threads only. Thread keyword hits are tracked internally (they suppress the
issue) and are not exposed in the report, whose shape is fixed by the spec.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.plot import OPEN_STATUSES, list_threads
from novel_editorial.core.setting import list_settings
from novel_editorial.quality.gate import split_sentences
from novel_editorial.store.db import DB
from novel_editorial.store.models import PlotThread, SettingEntry

IssueKind = Literal["character_missing", "number_conflict", "thread_missing"]
IssueSeverity = Literal["info", "conflict"]

_NUMBER_CHECK_KINDS = frozenset({"character", "timeline", "world"})
_THREAD_NAME_LIMIT = 20
_KIND_ORDER: dict[str, int] = {
    "character_missing": 0,
    "number_conflict": 1,
    "thread_missing": 2,
}
_CHINESE_DIGITS: dict[str, int] = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_NUMBER_RE = re.compile(
    r"(?P<num>\d+|[零一二三四五六七八九十百千两]+)"
    r"[ \t\u3000]*(?P<unit>[点时分年月日岁号])"
)
_STRIP_RE = re.compile(
    r"[\s，,、。！？；…!?;：:·「」『』“”‘’（）()\[\]【】《》〈〉<>\u2014\u2013-]+"
)


@dataclass(frozen=True)
class ConsistencyIssue:
    """One finding of a consistency check."""

    kind: IssueKind
    severity: IssueSeverity
    setting_name: str
    detail: str
    sentence: int | None = None


@dataclass(frozen=True)
class ConsistencyReport:
    """Deterministic output of :func:`check_consistency`."""

    issues: list[ConsistencyIssue]
    settings_checked: int
    threads_checked: int
    character_mentions: dict[str, int]


@dataclass(frozen=True)
class _NumberPair:
    unit: str
    value: int
    raw: str


def check_consistency(db: DB, workspace_id: str, text: str) -> ConsistencyReport:
    """Check draft text against the workspace settings and open threads.

    Raises :class:`NovelError` with ``USAGE_ERROR`` when the text is blank
    after stripping. The workspace is only consulted after that guard, and the
    whole check never writes to the database.
    """
    if not text.strip():
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            "正文为空，无法核查",
            context={"workspace_id": workspace_id, "reason": "empty draft text"},
        )
    settings = list_settings(db, workspace_id)
    checked_settings = [entry for entry in settings if entry.kind in _NUMBER_CHECK_KINDS]
    sentences = split_sentences(text)

    issues: list[ConsistencyIssue] = []
    character_mentions: dict[str, int] = {}
    for entry in checked_settings:
        if entry.kind != "character":
            continue
        count = text.count(entry.name)
        if count == 0:
            issues.append(
                ConsistencyIssue(
                    kind="character_missing",
                    severity="info",
                    setting_name=entry.name,
                    detail="设定人物未在正文出现",
                )
            )
        else:
            character_mentions[entry.name] = count

    issues.extend(_number_conflicts(checked_settings, sentences))
    threads = _open_threads(db, workspace_id)
    issues.extend(_thread_issues(threads, _normalize(text)))
    issues.sort(key=_issue_sort_key)

    return ConsistencyReport(
        issues=issues,
        settings_checked=len(checked_settings),
        threads_checked=len(threads),
        character_mentions=character_mentions,
    )


def _number_conflicts(entries: list[SettingEntry], sentences: list[str]) -> list[ConsistencyIssue]:
    """Compare setting number pairs against each text sentence."""
    issues: list[ConsistencyIssue] = []
    for entry in entries:
        setting_pairs = _extract_pairs(entry.content)
        if not setting_pairs:
            continue
        topics = _topic_words(entry)
        setting_by_unit = _group_by_unit(setting_pairs)
        for index, sentence in enumerate(sentences, start=1):
            if not any(topic in sentence for topic in topics):
                continue
            sentence_by_unit = _group_by_unit(_extract_pairs(sentence))
            if not sentence_by_unit:
                continue
            for unit, setting_values in setting_by_unit.items():
                sentence_values = sentence_by_unit.get(unit)
                if not sentence_values:
                    continue
                setting_value_set = {pair.value for pair in setting_values}
                setting_value_list = "、".join(pair.raw for pair in setting_values)
                for text_pair in sentence_values:
                    if text_pair.value in setting_value_set:
                        continue
                    issues.append(
                        ConsistencyIssue(
                            kind="number_conflict",
                            severity="conflict",
                            setting_name=entry.name,
                            detail=(
                                f"正文「{text_pair.raw}」不在设定值中"
                                f"（设定含：{setting_value_list}）（句 {index}）"
                            ),
                            sentence=index,
                        )
                    )
    return issues


def _thread_issues(threads: list[PlotThread], normalized_text: str) -> list[ConsistencyIssue]:
    """Report open threads whose keywords never appear in the text."""
    issues: list[ConsistencyIssue] = []
    for thread in threads:
        keywords = _thread_keywords(thread.content)
        if any(keyword in normalized_text for keyword in keywords):
            continue
        issues.append(
            ConsistencyIssue(
                kind="thread_missing",
                severity="info",
                setting_name=_truncate(thread.content.strip()),
                detail="伏笔关键词未出现",
            )
        )
    return issues


def _open_threads(db: DB, workspace_id: str) -> list[PlotThread]:
    return [thread for thread in list_threads(db, workspace_id) if thread.status in OPEN_STATUSES]


def _extract_pairs(text: str) -> list[_NumberPair]:
    """Extract deduplicated number+unit pairs from a text span."""
    pairs: list[_NumberPair] = []
    for match in _NUMBER_RE.finditer(text):
        num_text = match.group("num")
        unit = match.group("unit")
        value = int(num_text) if num_text.isdigit() else _chinese_numeral_to_int(num_text)
        pairs.append(_NumberPair(unit=unit, value=value, raw=num_text + unit))
    return _dedupe_pairs(pairs)


def _dedupe_pairs(pairs: list[_NumberPair]) -> list[_NumberPair]:
    seen: set[tuple[str, int, str]] = set()
    result: list[_NumberPair] = []
    for pair in pairs:
        key = (pair.unit, pair.value, pair.raw)
        if key not in seen:
            seen.add(key)
            result.append(pair)
    return result


def _group_by_unit(pairs: list[_NumberPair]) -> dict[str, list[_NumberPair]]:
    grouped: dict[str, list[_NumberPair]] = {}
    for pair in pairs:
        grouped.setdefault(pair.unit, []).append(pair)
    return grouped


def _topic_words(entry: SettingEntry) -> list[str]:
    """Return the entry name plus any ``前缀：`` prefix from its content."""
    topics = [entry.name]
    for colon in ("：", ":"):
        if colon in entry.content:
            prefix = entry.content.split(colon, 1)[0].strip()
            if prefix:
                topics.append(prefix)
            break
    return topics


def _chinese_numeral_to_int(text: str) -> int:
    """Normalize a Chinese numeral (zero to 千) to an integer."""
    total = 0
    current = 0
    for char in text:
        if char in _CHINESE_DIGITS:
            current = _CHINESE_DIGITS[char]
        elif char == "十":
            total += (current or 1) * 10
            current = 0
        elif char == "百":
            total += (current or 1) * 100
            current = 0
        elif char == "千":
            total += (current or 1) * 1000
            current = 0
    return total + current


def _thread_keywords(content: str) -> list[str]:
    """Build the keyword set of normalized thread content.

    Content that normalizes to fewer than 2 chars uses the normalized content
    itself as its only keyword, so a single-char foreshadow still matches when
    the character appears in the text.
    """
    cleaned = _normalize(content)
    if not cleaned:
        return []
    if len(cleaned) < 2:
        return [cleaned]
    keywords: list[str] = []
    seen: set[str] = set()
    for size in range(2, 5):
        for start in range(len(cleaned) - size + 1):
            token = cleaned[start : start + size]
            if token not in seen:
                seen.add(token)
                keywords.append(token)
    return keywords


def _normalize(text: str) -> str:
    """Strip whitespace and punctuation for stable substring matching."""
    return _STRIP_RE.sub("", text)


def _truncate(text: str) -> str:
    if len(text) <= _THREAD_NAME_LIMIT:
        return text
    return text[: _THREAD_NAME_LIMIT - 1] + "…"


def _issue_sort_key(issue: ConsistencyIssue) -> tuple[int, int]:
    """Conflicts first; the rest follow 人物 → 数字 → 伏笔 kind order."""
    return (0 if issue.severity == "conflict" else 1, _KIND_ORDER[issue.kind])
