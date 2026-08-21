"""Style learning service: corpus collection and deterministic style profiling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from novel_editorial.core.calibration import (
    CORPUS_EXTENSIONS,
    is_valid_corpus_file,
    read_sample,
)
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.quality.gate import (
    DEFAULT_AI_WORDS,
    DEFAULT_MODIFIERS,
    split_sentences,
)

SHORT_SENTENCE_LIMIT = 15


def collect_corpus_texts(path: Path | str) -> list[str]:
    """Collect non-blank texts from a corpus path.

    ``path`` may be a single non-hidden .txt/.md file or a directory scanned
    recursively. Every valid file contributes one text sample; blank files,
    hidden files, non-corpus files and files that fail to read are skipped.
    A missing path raises NovelError(NOT_FOUND). A path with no readable
    samples raises NovelError(USAGE_ERROR) with the same wording family as the
    calibration service (N9).
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

    texts: list[str] = []
    skipped = 0
    errors: list[str] = []
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
        if not text.split():
            skipped += 1
            continue
        texts.append(text)

    if not texts:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"corpus contains no readable samples: {root}",
            context={"path": str(root), "skipped": skipped, "errors": errors},
        )
    return texts


@dataclass(frozen=True)
class StyleProfile:
    """Deterministic style statistics computed from corpus texts."""

    samples: int
    total_chars: int
    avg_sentence_len: float
    short_sentence_ratio: float
    modifier_per_1000: float
    ai_word_hits: list[str]


def compute_style_profile(texts: list[str]) -> StyleProfile:
    """Compute a deterministic style profile from non-blank corpus texts.

    Blank texts are ignored; an empty input list yields a zero-valued profile.
    Sentence lengths are whitespace-stripped character counts from
    ``quality.gate.split_sentences``. Modifier and AI-word hits follow the
    quality-gate semantics: each word-list entry matching anywhere in the
    merged text counts once.
    """
    samples = [text for text in texts if text.split()]
    if not samples:
        return StyleProfile(
            samples=0,
            total_chars=0,
            avg_sentence_len=0.0,
            short_sentence_ratio=0.0,
            modifier_per_1000=0.0,
            ai_word_hits=[],
        )

    sentences = [sentence for text in samples for sentence in split_sentences(text)]
    sentence_lengths = [len("".join(sentence.split())) for sentence in sentences]
    total_chars = sum(sentence_lengths)
    sentence_count = len(sentence_lengths)
    short_count = sum(length <= SHORT_SENTENCE_LIMIT for length in sentence_lengths)
    joined = "".join(samples)
    modifier_hits = sum(1 for modifier in DEFAULT_MODIFIERS if modifier in joined)
    ai_word_hits = sorted(word for word in DEFAULT_AI_WORDS if word in joined)
    return StyleProfile(
        samples=len(samples),
        total_chars=total_chars,
        avg_sentence_len=total_chars / sentence_count,
        short_sentence_ratio=short_count / sentence_count,
        modifier_per_1000=modifier_hits * 1000 / total_chars,
        ai_word_hits=ai_word_hits,
    )


def build_suggested_description(profile: StyleProfile) -> str:
    """Build a deterministic style description from a style profile.

    Rule-based description covering sentence length, rhythm and modifier
    density, joined with ideographic commas (e.g. "短句，节奏快，修饰克制").
    A zero-valued profile (samples == 0) yields an empty string.
    """
    if profile.samples == 0:
        return ""
    if profile.avg_sentence_len <= 12:
        length_part = "短句"
    elif profile.avg_sentence_len <= 18:
        length_part = "句子不长"
    else:
        length_part = "长句较多"
    if profile.short_sentence_ratio >= 0.5:
        rhythm_part = "节奏快"
    elif profile.short_sentence_ratio >= 0.3:
        rhythm_part = "长短句相间"
    else:
        rhythm_part = "句子舒展"
    if profile.modifier_per_1000 <= 5:
        modifier_part = "修饰克制"
    else:
        modifier_part = "修饰偏多"
    return "，".join((length_part, rhythm_part, modifier_part))
