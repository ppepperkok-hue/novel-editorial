from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.style import extract_style_keywords
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.quality.explain import CLEAN_MESSAGE, explain_quality, render_explanation
from novel_editorial.quality.gate import check_quality
from novel_editorial.store.db import DB
from novel_editorial.store.models import Draft

runner = CliRunner()

REPEATED_ENDINGS_TEXT = "他走进院子。她走进院子。大家走进院子。"
CLEAN_TEXT = "他推开门，走进院子，把伞靠在墙边。"
AI_TEXT = "他静静地站着，缓缓转身，月光宛如薄纱，悄然洒落。她走进院子。他走进院子。"


def test_sentence_repetition_detected_only_for_repeated_endings() -> None:
    repeated = check_quality(REPEATED_ENDINGS_TEXT)
    clean = check_quality(CLEAN_TEXT)
    assert repeated.details["sentence_repetition"] == 2
    assert clean.details["sentence_repetition"] == 0
    assert repeated.score == clean.score + 8


def test_style_consistency_distinguishes_hit_counts() -> None:
    keywords = frozenset({"克制", "留白", "利落"})
    many_hits = check_quality("他的笔触克制，留白很多。", style_keywords=keywords)
    few_hits = check_quality("雨停了，他收起伞。", style_keywords=keywords)
    assert many_hits.details["style_consistency"] == 2 / 3
    assert few_hits.details["style_consistency"] == 0.0
    assert many_hits.details["style_hits"] == ["克制", "留白"]
    assert many_hits.score < few_hits.score


def test_check_quality_details_include_new_dimensions() -> None:
    report = check_quality(CLEAN_TEXT)
    assert report.details["sentence_repetition"] == 0
    assert report.details["style_hits"] == []
    assert report.details["style_consistency"] == 1.0
    assert report.score == 0


def test_extract_style_keywords_separated() -> None:
    keywords = extract_style_keywords("短句、利落，强画面感")
    assert keywords == frozenset({"短句", "利落", "强画面感"})
    assert extract_style_keywords("") == frozenset()
    assert extract_style_keywords("   ") == frozenset()


def test_extract_style_keywords_continuous_ngrams() -> None:
    keywords = extract_style_keywords("白描克制留白")
    assert {"白描", "克制", "留白"} <= keywords
    assert "描克制" in keywords
    assert all(2 <= len(keyword) <= 4 for keyword in keywords)


def test_explain_lists_positions_types_and_suggestions() -> None:
    issues = explain_quality(AI_TEXT)
    kinds = {issue.kind for issue in issues}
    assert {"ai_word", "modifier_density", "sentence_repetition"} <= kinds
    assert any(issue.word == "宛如" for issue in issues)

    rendered = render_explanation(issues)
    assert "句 1" in rendered
    assert "AI 词命中" in rendered
    assert "修饰词密度" in rendered
    assert "句式重复" in rendered
    assert "物象" in rendered


def test_explain_clean_text_reports_no_issues() -> None:
    issues = explain_quality(CLEAN_TEXT)
    assert issues == []
    assert render_explanation(issues) == CLEAN_MESSAGE


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "解释之书", "--genre", "都市"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _draft_status(workspace_id: str, draft_id: str) -> str:
    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).filter_by(id=draft_id).first()
        assert draft is not None
        return draft.status


def _generate(tmp_path: Path, monkeypatch, workspace_id: str, reply: str, title: str) -> str:
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply=reply),
    )
    result = runner.invoke(app, ["draft", "generate", workspace_id, "--title", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[1]


def test_quality_check_shows_new_dimensions(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    styled = runner.invoke(
        app,
        ["style", "set", workspace_id, "--description", "克制、留白、利落"],
    )
    assert styled.exit_code == 0, styled.output
    draft_id = _generate(tmp_path, monkeypatch, workspace_id, AI_TEXT, "第一章")

    result = runner.invoke(app, ["quality", "check", draft_id])
    assert result.exit_code == 0, result.output
    assert "sentence repetition: 1" in result.output
    assert "style hits: 0/3" in result.output
    assert "(consistency 0.00)" in result.output


def test_generate_passes_style_keywords_into_gate(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("NOVEL_QUALITY_THRESHOLD", "1")
    styled = runner.invoke(
        app,
        ["style", "set", workspace_id, "--description", "利落、短句、强画面感"],
    )
    assert styled.exit_code == 0, styled.output
    draft_id = _generate(tmp_path, monkeypatch, workspace_id, "雨停了，他收起伞。", "第一章")
    assert _draft_status(workspace_id, draft_id) == "quality_failed"


def test_quality_explain_command_lists_issues_and_suggestions(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate(tmp_path, monkeypatch, workspace_id, AI_TEXT, "第一章")

    result = runner.invoke(app, ["quality", "explain", draft_id])
    assert result.exit_code == 0, result.output
    assert "句 1" in result.output
    assert "宛如" in result.output
    assert "AI 词命中" in result.output
    assert "修饰词密度" in result.output
    assert "句式重复" in result.output
    assert "物象" in result.output


def test_quality_explain_command_clean_text(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate(tmp_path, monkeypatch, workspace_id, CLEAN_TEXT, "第一章")

    result = runner.invoke(app, ["quality", "explain", draft_id])
    assert result.exit_code == 0, result.output
    assert CLEAN_MESSAGE in result.output


def test_quality_explain_unknown_draft_exits_1(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["quality", "explain", "nope"])
    assert result.exit_code == 1
    assert "draft not found" in result.output
