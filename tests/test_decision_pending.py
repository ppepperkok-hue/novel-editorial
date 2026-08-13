from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.llm.client import MockLLMClient

runner = CliRunner()

AI_FLAVORED_REPLY = "璀璨的瞬间，仿佛宛如梦境，氤氲萦绕，深邃而静谧。"


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "待拍板之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _mock_llm(monkeypatch, reply: str) -> None:
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply=reply),
    )


def _generate(workspace_id: str, monkeypatch, *, title: str, reply: str):
    _mock_llm(monkeypatch, reply)
    result = runner.invoke(app, ["draft", "generate", workspace_id, "--title", title])
    assert result.exit_code == 0, result.output
    return result


def test_generate_quality_passed_hints_and_lists_pending(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    generated = _generate(
        workspace_id, monkeypatch, title="第一章", reply="雨夜的开场，写得干净利落。"
    )
    draft_id = generated.output.split()[1]
    assert f"awaiting decision: {draft_id}" in generated.output

    pending = runner.invoke(app, ["decision", "pending", workspace_id])
    assert pending.exit_code == 0, pending.output
    assert draft_id in pending.output
    assert "第一章" in pending.output
    assert "draft" in pending.output


def test_pending_empty_state(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    pending = runner.invoke(app, ["decision", "pending", workspace_id])
    assert pending.exit_code == 0, pending.output
    assert "no pending decisions" in pending.output


def test_revise_quality_passed_still_hints_and_lists_pending(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    generated = _generate(
        workspace_id, monkeypatch, title="第一章", reply="第一版正文，短句为主。"
    )
    draft_id = generated.output.split()[1]

    _mock_llm(monkeypatch, "修订后的第二版正文，钩子更硬。")
    revised = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "重写铺垫"])
    assert revised.exit_code == 0, revised.output
    assert f"awaiting decision: {draft_id}" in revised.output

    pending = runner.invoke(app, ["decision", "pending", workspace_id])
    assert pending.exit_code == 0, pending.output
    assert draft_id in pending.output
    assert "v2" in pending.output


def test_accept_removes_from_pending(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    generated = _generate(
        workspace_id, monkeypatch, title="第一章", reply="通过质量门的正文。"
    )
    draft_id = generated.output.split()[1]

    accepted = runner.invoke(app, ["decision", "accept", draft_id])
    assert accepted.exit_code == 0, accepted.output

    pending = runner.invoke(app, ["decision", "pending", workspace_id])
    assert pending.exit_code == 0, pending.output
    assert "no pending decisions" in pending.output
    assert draft_id not in pending.output


def test_reject_removes_from_pending(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    generated = _generate(
        workspace_id, monkeypatch, title="第一章", reply="通过质量门的正文。"
    )
    draft_id = generated.output.split()[1]

    rejected = runner.invoke(app, ["decision", "reject", draft_id])
    assert rejected.exit_code == 0, rejected.output

    pending = runner.invoke(app, ["decision", "pending", workspace_id])
    assert pending.exit_code == 0, pending.output
    assert "no pending decisions" in pending.output
    assert draft_id not in pending.output


def test_quality_failed_has_no_hint_and_is_not_pending(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    generated = _generate(
        workspace_id, monkeypatch, title="AI味章节", reply=AI_FLAVORED_REPLY
    )
    draft_id = generated.output.split()[1]
    assert "awaiting decision" not in generated.output

    pending = runner.invoke(app, ["decision", "pending", workspace_id])
    assert pending.exit_code == 0, pending.output
    assert "no pending decisions" in pending.output
    assert draft_id not in pending.output
