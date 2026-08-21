from pathlib import Path

import pytest

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.style_learn import (
    StyleProfile,
    build_suggested_description,
    collect_corpus_texts,
    compute_style_profile,
)

DIMENSION_TEXT = "她静静地站着，月光宛如薄纱。他悄然转身离去。"


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_collect_corpus_texts_directory_recursive(tmp_path: Path) -> None:
    _write(tmp_path, "b.md", "月光。")
    _write(tmp_path, "a.txt", "微风。")
    (tmp_path / "sub").mkdir()
    _write(tmp_path / "sub", "c.txt", "细雨。")

    texts = collect_corpus_texts(tmp_path)

    assert texts == ["微风。", "月光。", "细雨。"]


def test_collect_corpus_texts_single_file(tmp_path: Path) -> None:
    path = _write(tmp_path, "chapter.txt", "月光宛如薄纱。")

    assert collect_corpus_texts(path) == ["月光宛如薄纱。"]


def test_collect_corpus_texts_skips_hidden_empty_and_non_corpus(tmp_path: Path) -> None:
    _write(tmp_path, ".hidden.txt", "隐藏。")
    _write(tmp_path, "empty.txt", " \n\n")
    _write(tmp_path, "blank.md", "")
    _write(tmp_path, "notes.py", "print(1)")
    _write(tmp_path, "notes.md", "正文。")

    assert collect_corpus_texts(tmp_path) == ["正文。"]


def test_collect_corpus_texts_reads_bom_file(tmp_path: Path) -> None:
    path = tmp_path / "bom.txt"
    path.write_bytes(b"\xef\xbb\xbf" + "月光宛如薄纱。".encode())

    assert collect_corpus_texts(path) == ["月光宛如薄纱。"]


def test_collect_corpus_texts_empty_directory_raises_usage_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(NovelError) as exc_info:
        collect_corpus_texts(empty)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR
    assert "no readable samples" in exc_info.value.message


def test_collect_corpus_texts_only_skipped_files_raises_usage_error(
    tmp_path: Path,
) -> None:
    _write(tmp_path, ".hidden.txt", "隐藏。")
    _write(tmp_path, "empty.txt", " ")

    with pytest.raises(NovelError) as exc_info:
        collect_corpus_texts(tmp_path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR
    assert "no readable samples" in exc_info.value.message


def test_collect_corpus_texts_only_unreadable_files_raises_usage_error(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff\xfe\x00\x80")

    with pytest.raises(NovelError) as exc_info:
        collect_corpus_texts(tmp_path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR


def test_collect_corpus_texts_missing_path_raises_not_found(tmp_path: Path) -> None:
    with pytest.raises(NovelError) as exc_info:
        collect_corpus_texts(tmp_path / "missing")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_collect_corpus_texts_single_non_corpus_file_raises_usage_error(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, "notes.py", "print(1)")

    with pytest.raises(NovelError) as exc_info:
        collect_corpus_texts(path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR


def test_collect_corpus_texts_skips_punctuation_only_files(tmp_path: Path) -> None:
    _write(tmp_path, "normal.txt", "月光宛如薄纱。")
    _write(tmp_path, "separator.txt", "……\n……")

    assert collect_corpus_texts(tmp_path) == ["月光宛如薄纱。"]


def test_collect_corpus_texts_only_punctuation_raises_usage_error(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "separator.txt", "……\n……")

    with pytest.raises(NovelError) as exc_info:
        collect_corpus_texts(tmp_path)
    assert exc_info.value.code == ErrorCode.USAGE_ERROR
    assert "no readable samples" in exc_info.value.message


def test_compute_style_profile_dimensions() -> None:
    profile = compute_style_profile([DIMENSION_TEXT])

    assert profile.samples == 1
    assert profile.total_chars == 20
    assert profile.avg_sentence_len == 10.0
    assert profile.short_sentence_ratio == 1.0
    assert profile.modifier_per_1000 == 50.0
    assert profile.ai_word_hits == ["宛如", "悄然"]


def test_compute_style_profile_merges_multiple_texts() -> None:
    profile = compute_style_profile(["她静静地站着。", "月光宛如薄纱，风轻轻吹过。"])

    assert profile.samples == 2
    assert profile.total_chars == 18
    assert profile.avg_sentence_len == 9.0
    assert profile.short_sentence_ratio == 1.0
    assert profile.modifier_per_1000 == pytest.approx(2 * 1000 / 18)
    assert profile.ai_word_hits == ["宛如"]


def test_compute_style_profile_empty_texts_returns_zero_profile() -> None:
    profile = compute_style_profile([])

    assert profile == StyleProfile(
        samples=0,
        total_chars=0,
        avg_sentence_len=0.0,
        short_sentence_ratio=0.0,
        modifier_per_1000=0.0,
        ai_word_hits=[],
    )


def test_compute_style_profile_punctuation_only_returns_zero_profile() -> None:
    profile = compute_style_profile(["……\n……"])

    assert profile == StyleProfile(
        samples=0,
        total_chars=0,
        avg_sentence_len=0.0,
        short_sentence_ratio=0.0,
        modifier_per_1000=0.0,
        ai_word_hits=[],
    )


def test_compute_style_profile_is_deterministic() -> None:
    texts = ["她静静地站着。", "月光宛如薄纱，风轻轻吹过。"]

    assert compute_style_profile(texts) == compute_style_profile(texts)


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (StyleProfile(1, 20, 10.0, 0.6, 3.0, []), "短句，节奏快，修饰克制"),
        (StyleProfile(1, 20, 15.0, 0.4, 6.0, []), "句子不长，长短句相间，修饰偏多"),
        (StyleProfile(1, 20, 20.0, 0.2, 10.0, []), "长句较多，句子舒展，修饰偏多"),
        (StyleProfile(1, 20, 12.0, 0.5, 5.0, []), "短句，节奏快，修饰克制"),
        (StyleProfile(1, 20, 18.0, 0.3, 5.0, []), "句子不长，长短句相间，修饰克制"),
    ],
)
def test_build_suggested_description_branches(profile: StyleProfile, expected: str) -> None:
    assert build_suggested_description(profile) == expected


def test_build_suggested_description_zero_profile_is_empty() -> None:
    zero = StyleProfile(0, 0, 0.0, 0.0, 0.0, [])

    assert build_suggested_description(zero) == ""


def test_collect_compute_build_end_to_end(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", "他推门进来。她静静站着。")
    _write(tmp_path, "b.md", "夜色漫过屋顶，把一切都笼罩在模糊的轮廓里，像是谁轻轻叹了口气。")

    texts = collect_corpus_texts(tmp_path)
    profile = compute_style_profile(texts)

    assert profile.samples == 2
    assert profile.total_chars == 40
    assert profile.avg_sentence_len == pytest.approx(40 / 3)
    assert profile.short_sentence_ratio == pytest.approx(2 / 3)
    assert profile.modifier_per_1000 == 50.0
    assert profile.ai_word_hits == []
    assert build_suggested_description(profile) == "句子不长，节奏快，修饰偏多"
