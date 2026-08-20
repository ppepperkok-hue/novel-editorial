from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings

runner = CliRunner()

CLEAN_TEXT = "他推开门，走进院子，把伞靠在墙边。"
AI_TEXT = "他静静地站着，缓缓转身，月光宛如薄纱，悄然洒落。她走进院子。他走进院子。"


def _corpus_dir(tmp_path: Path) -> Path:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "clean.txt").write_text(CLEAN_TEXT, encoding="utf-8")
    (corpus / "ai.txt").write_text(AI_TEXT, encoding="utf-8")
    return corpus


def _invoke(tmp_path: Path, monkeypatch, *args: str):
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    return runner.invoke(app, list(args))


def test_quality_calibrate_prints_samples_distribution_and_suggestion(
    tmp_path: Path, monkeypatch
) -> None:
    corpus = _corpus_dir(tmp_path)

    result = _invoke(tmp_path, monkeypatch, "quality", "calibrate", str(corpus))

    assert result.exit_code == 0, result.output
    assert "samples: 2" in result.output
    assert "clean.txt: 字数" in result.output
    assert "ai.txt: 字数" in result.output
    assert "AI 词" in result.output
    assert "修饰词" in result.output
    assert "句式重复" in result.output
    assert "score 0.0" in result.output
    assert "score 22.0" in result.output
    assert (
        "distribution: min 0.0 median 11.0 p90 22.0 p95 22.0 max 22.0"
        in result.output
    )
    assert "suggested threshold: 22" in result.output


def test_quality_calibrate_single_file(tmp_path: Path, monkeypatch) -> None:
    sample = tmp_path / "one.txt"
    sample.write_text(AI_TEXT, encoding="utf-8")

    result = _invoke(tmp_path, monkeypatch, "quality", "calibrate", str(sample))

    assert result.exit_code == 0, result.output
    assert "samples: 1" in result.output
    assert "score 22.0" in result.output
    assert "suggested threshold: 22" in result.output


def test_quality_calibrate_apply_writes_threshold(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    corpus = _corpus_dir(tmp_path)

    result = _invoke(
        tmp_path, monkeypatch, "quality", "calibrate", str(corpus), "--apply"
    )

    assert result.exit_code == 0, result.output
    assert "apply: quality_threshold = 22" in result.output
    assert f"config updated: {config_path}" in result.output
    content = config_path.read_text(encoding="utf-8")
    assert "[defaults]" in content
    assert "quality_threshold = 22" in content
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 22


def test_quality_calibrate_apply_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    corpus = _corpus_dir(tmp_path)

    first = _invoke(
        tmp_path, monkeypatch, "quality", "calibrate", str(corpus), "--apply"
    )
    assert first.exit_code == 0, first.output
    content_after_first = config_path.read_text(encoding="utf-8")

    second = _invoke(
        tmp_path, monkeypatch, "quality", "calibrate", str(corpus), "--apply"
    )

    assert second.exit_code == 0, second.output
    assert config_path.read_text(encoding="utf-8") == content_after_first


def test_quality_calibrate_without_apply_never_writes_config(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "config.toml"
    corpus = _corpus_dir(tmp_path)

    result = _invoke(tmp_path, monkeypatch, "quality", "calibrate", str(corpus))

    assert result.exit_code == 0, result.output
    assert not config_path.exists()


def test_quality_calibrate_reports_skipped_and_warnings(
    tmp_path: Path, monkeypatch
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "clean.txt").write_text(CLEAN_TEXT, encoding="utf-8")
    (corpus / ".hidden.txt").write_text("secret", encoding="utf-8")
    (corpus / "broken.txt").write_bytes(b"\xc3\x28")

    result = _invoke(tmp_path, monkeypatch, "quality", "calibrate", str(corpus))

    assert result.exit_code == 0, result.output
    assert "skipped: 2" in result.output
    assert "warning:" in result.output
    assert "score 0.0" in result.output


def test_quality_calibrate_empty_corpus_exits_2(tmp_path: Path, monkeypatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    result = _invoke(tmp_path, monkeypatch, "quality", "calibrate", str(empty))

    assert result.exit_code == 2
    assert "no readable samples" in result.output


def test_quality_calibrate_missing_path_exits_1(tmp_path: Path, monkeypatch) -> None:
    result = _invoke(
        tmp_path, monkeypatch, "quality", "calibrate", str(tmp_path / "nope")
    )

    assert result.exit_code == 1
    assert "not found" in result.output
