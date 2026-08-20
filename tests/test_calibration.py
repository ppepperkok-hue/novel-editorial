from pathlib import Path

import pytest

from novel_editorial.core.calibration import (
    CORPUS_EXTENSIONS,
    CorpusSample,
    is_valid_corpus_file,
    read_sample,
    scan_corpus,
)
from novel_editorial.core.errors import ErrorCode, NovelError

REPEATED_ENDINGS_TEXT = "他走进院子。她走进院子。大家走进院子。"
CLEAN_TEXT = "他推开门，走进院子，把伞靠在墙边。"
AI_TEXT = "他静静地站着，缓缓转身，月光宛如薄纱，悄然洒落。她走进院子。他走进院子。"
MODIFIER_TEXT = "他静静地看着窗外。"
AI_SINGLE_TEXT = "她不禁莞尔。"
AI_TWO_TEXT = "她不禁莞尔，仿佛在笑。"


def test_corpus_extensions_constant() -> None:
    assert CORPUS_EXTENSIONS == {".txt", ".md"}


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_is_valid_corpus_file_accepts_txt_and_md(tmp_path: Path) -> None:
    for name in ("notes.txt", "notes.md", "UPPER.TXT"):
        path = _write(tmp_path, name, "正文")
        assert is_valid_corpus_file(path)


def test_is_valid_corpus_file_rejects_non_corpus_hidden_and_directory(
    tmp_path: Path,
) -> None:
    py_file = _write(tmp_path, "notes.py", "print(1)")
    hidden = _write(tmp_path, ".hidden.txt", "正文")
    directory = tmp_path / "notes.md"
    directory.mkdir()
    assert not is_valid_corpus_file(py_file)
    assert not is_valid_corpus_file(hidden)
    assert not is_valid_corpus_file(directory)


def test_read_sample_returns_utf8_text(tmp_path: Path) -> None:
    path = _write(tmp_path, "sample.txt", CLEAN_TEXT)
    assert read_sample(path) == CLEAN_TEXT


def test_read_sample_unreadable_file_raises_novel_error_with_path(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad.txt"
    path.write_bytes(b"\xff\xfe\x00\x80")
    with pytest.raises(NovelError) as exc_info:
        read_sample(path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR
    assert str(path) in exc_info.value.message
    assert exc_info.value.context["path"] == str(path)


def test_scan_corpus_directory_sorts_samples_and_scores(tmp_path: Path) -> None:
    _write(tmp_path, "b.md", AI_TEXT)
    _write(tmp_path, "a.txt", CLEAN_TEXT)
    _write(tmp_path, "c.txt", REPEATED_ENDINGS_TEXT)
    (tmp_path / "sub").mkdir()
    _write(tmp_path / "sub", "e.md", MODIFIER_TEXT)

    report = scan_corpus(tmp_path)

    assert [sample.path.name for sample in report.samples] == [
        "a.txt",
        "b.md",
        "c.txt",
        "e.md",
    ]
    assert report.scores == [0.0, 22.0, 8.0, 3.0]
    assert report.samples[0] == CorpusSample(
        path=tmp_path / "a.txt",
        char_count=17,
        ai_word_hits=0,
        modifier_hits=0,
        sentence_repetition=0,
        score=0.0,
    )
    assert report.samples[1] == CorpusSample(
        path=tmp_path / "b.md",
        char_count=36,
        ai_word_hits=2,
        modifier_hits=2,
        sentence_repetition=1,
        score=22.0,
    )
    assert report.samples[2] == CorpusSample(
        path=tmp_path / "c.txt",
        char_count=19,
        ai_word_hits=0,
        modifier_hits=0,
        sentence_repetition=2,
        score=8.0,
    )
    assert report.samples[3] == CorpusSample(
        path=tmp_path / "sub" / "e.md",
        char_count=9,
        ai_word_hits=0,
        modifier_hits=1,
        sentence_repetition=0,
        score=3.0,
    )
    assert report.min == 0.0
    assert report.median == 5.5
    assert report.p90 == 22.0
    assert report.p95 == 22.0
    assert report.max == 22.0
    assert report.suggested_threshold == 22
    assert report.skipped == 0
    assert report.errors == []


def test_scan_corpus_single_file(tmp_path: Path) -> None:
    path = _write(tmp_path, "chapter.txt", AI_SINGLE_TEXT)

    report = scan_corpus(path)

    assert len(report.samples) == 1
    assert report.samples[0].path == path
    assert report.samples[0].char_count == 6
    assert report.samples[0].ai_word_hits == 1
    assert report.samples[0].modifier_hits == 0
    assert report.samples[0].sentence_repetition == 0
    assert report.samples[0].score == 6.0
    assert report.scores == [6.0]
    assert report.min == report.median == report.p90 == report.p95 == report.max == 6.0
    assert report.suggested_threshold == 6


def test_scan_corpus_skips_hidden_empty_and_ignores_non_corpus(
    tmp_path: Path,
) -> None:
    _write(tmp_path, ".hidden.txt", AI_TEXT)
    _write(tmp_path, "empty.txt", "   \n\n")
    _write(tmp_path, "blank.md", "")
    _write(tmp_path, "readme.py", "print(1)")
    _write(tmp_path, ".gitkeep", "")
    _write(tmp_path, "notes.md", CLEAN_TEXT)

    report = scan_corpus(tmp_path)

    assert [sample.path.name for sample in report.samples] == ["notes.md"]
    assert report.scores == [0.0]
    assert report.suggested_threshold == 1
    assert report.skipped == 3
    assert report.errors == []


def test_scan_corpus_distribution_boundaries(tmp_path: Path) -> None:
    texts = [
        CLEAN_TEXT,
        CLEAN_TEXT,
        MODIFIER_TEXT,
        MODIFIER_TEXT,
        AI_SINGLE_TEXT,
        AI_SINGLE_TEXT,
        REPEATED_ENDINGS_TEXT,
        REPEATED_ENDINGS_TEXT,
        AI_TWO_TEXT,
        AI_TEXT,
    ]
    for index, text in enumerate(texts, start=1):
        _write(tmp_path, f"c{index:02d}.txt", text)

    report = scan_corpus(tmp_path)

    assert report.scores == [0.0, 0.0, 3.0, 3.0, 6.0, 6.0, 8.0, 8.0, 12.0, 22.0]
    assert report.min == 0.0
    assert report.median == 6.0
    assert report.p90 == 12.0
    assert report.p95 == 22.0
    assert report.max == 22.0
    assert report.suggested_threshold == 12


def test_scan_corpus_two_samples_even_median(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", CLEAN_TEXT)
    _write(tmp_path, "b.txt", AI_TEXT)

    report = scan_corpus(tmp_path)

    assert report.scores == [0.0, 22.0]
    assert report.median == 11.0
    assert report.p90 == report.p95 == report.max == 22.0
    assert report.suggested_threshold == 22


def test_scan_corpus_all_zero_scores_suggest_threshold_one(tmp_path: Path) -> None:
    for name in ("a.txt", "b.txt", "c.txt"):
        _write(tmp_path, name, CLEAN_TEXT)

    report = scan_corpus(tmp_path)

    assert report.scores == [0.0, 0.0, 0.0]
    assert report.min == report.median == report.p90 == report.p95 == report.max == 0.0
    assert report.suggested_threshold == 1


def test_scan_corpus_empty_directory_raises_usage_error(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    with pytest.raises(NovelError) as exc_info:
        scan_corpus(empty_dir)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR


def test_scan_corpus_directory_with_only_skipped_files_raises(tmp_path: Path) -> None:
    _write(tmp_path, ".hidden.txt", AI_TEXT)
    _write(tmp_path, "empty.txt", " ")

    with pytest.raises(NovelError) as exc_info:
        scan_corpus(tmp_path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR


def test_scan_corpus_missing_path_raises_not_found(tmp_path: Path) -> None:
    with pytest.raises(NovelError) as exc_info:
        scan_corpus(tmp_path / "missing")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_scan_corpus_single_non_corpus_file_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "notes.py", "print(1)")
    with pytest.raises(NovelError) as exc_info:
        scan_corpus(path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR


def test_scan_corpus_single_hidden_file_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, ".hidden.txt", AI_TEXT)
    with pytest.raises(NovelError) as exc_info:
        scan_corpus(path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR


def test_scan_corpus_read_failure_skipped_and_exposed(tmp_path: Path) -> None:
    good = _write(tmp_path, "good.txt", CLEAN_TEXT)
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff\xfe\x00\x80")

    report = scan_corpus(tmp_path)

    assert [sample.path for sample in report.samples] == [good]
    assert report.skipped == 1
    assert len(report.errors) == 1
    assert str(bad) in report.errors[0]


def test_scan_corpus_only_unreadable_files_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff\xfe\x00\x80")

    with pytest.raises(NovelError) as exc_info:
        scan_corpus(tmp_path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR


def test_scan_corpus_is_deterministic(tmp_path: Path) -> None:
    _write(tmp_path, "b.md", AI_TEXT)
    _write(tmp_path, "a.txt", CLEAN_TEXT)
    _write(tmp_path, "c.txt", REPEATED_ENDINGS_TEXT)
    _write(tmp_path, ".hidden.txt", AI_TEXT)
    _write(tmp_path, "empty.txt", " ")

    first = scan_corpus(tmp_path)
    second = scan_corpus(tmp_path)

    assert first == second
    assert first.scores == second.scores
    assert first.suggested_threshold == second.suggested_threshold
