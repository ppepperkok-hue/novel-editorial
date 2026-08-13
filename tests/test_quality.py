from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.log import build_workspace_log
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.quality.gate import check_quality
from novel_editorial.store.db import DB
from novel_editorial.store.models import Draft

runner = CliRunner()

AI_FLAVOR_SAMPLES = [
    "月光宛如薄纱，悄然洒落，他静静地凝视着远方。",
    "她的笑容仿佛春风，瞬间融化了他心底的坚冰，他怔怔地看着她。",
    "夜色氤氲，小巷静谧，他缓缓走过，心中怅然若失。",
    "星光璀璨，苍穹深邃，她不禁轻轻叹息。",
    "琴声悠远，余音袅袅，仿佛还在耳边萦绕。",
    "他默默站在窗前，望着远方，思绪缥缈如烟。",
    "湖面潋滟，波光粼粼，她微微勾起唇角。",
    "风轻轻拂过，树叶婆娑作响，他怔怔地望着那抹身影。",
    "记忆如潮水般涌来，他不禁陷入深深的回忆。",
    "雪落无声，天地静谧，她静静地闭上了眼睛。",
]

PLAIN_SAMPLES = [
    "他推开门，走进院子，把伞靠在墙边。",
    "她把碗放进水池，拧开水龙头开始洗碗。",
    "下午三点，他准时到了车站。",
    "老师说作业明天交，大家记得带课本。",
    "他坐在桌前，打开电脑，开始写报告。",
    "雨停了，路上还有积水，他绕开走了。",
    "她点了两份外卖，一份米饭一份面条。",
    "球滚到墙角，他跑过去捡起来。",
    "车在红灯前停下，他看了看手表。",
    "他把钥匙放在门口的鞋柜上，换鞋进屋。",
]


def test_quality_gate_test_set_accuracy() -> None:
    ai_judged_failed = sum(not check_quality(text).passed for text in AI_FLAVOR_SAMPLES)
    plain_judged_passed = sum(check_quality(text).passed for text in PLAIN_SAMPLES)
    accuracy = (ai_judged_failed + plain_judged_passed) / (
        len(AI_FLAVOR_SAMPLES) + len(PLAIN_SAMPLES)
    )
    assert accuracy >= 0.9
    assert ai_judged_failed == len(AI_FLAVOR_SAMPLES)
    assert plain_judged_passed == len(PLAIN_SAMPLES)


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "质量之书", "--genre", "都市"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _draft_status(workspace_id: str, draft_id: str) -> str:
    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).filter_by(id=draft_id).first()
        assert draft is not None
        return draft.status


def test_generate_marks_quality_failed_and_blocks_accept(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply=AI_FLAVOR_SAMPLES[0]),
    )
    created = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert created.exit_code == 0, created.output
    draft_id = created.output.split()[1]
    assert _draft_status(workspace_id, draft_id) == "quality_failed"

    accepted = runner.invoke(app, ["decision", "accept", draft_id])
    assert accepted.exit_code == 2
    assert "quality gate" in accepted.output

    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply="他推开门，走进院子。"),
    )
    revised = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "按质量门修改"])
    assert revised.exit_code == 0, revised.output
    assert _draft_status(workspace_id, draft_id) == "draft"

    accepted = runner.invoke(app, ["decision", "accept", draft_id])
    assert accepted.exit_code == 0, accepted.output


def test_quality_check_command_reports(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply=AI_FLAVOR_SAMPLES[0]),
    )
    created = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    draft_id = created.output.split()[1]

    result = runner.invoke(app, ["quality", "check", draft_id])
    assert result.exit_code == 0, result.output
    assert "passed: False" in result.output
    assert "score:" in result.output
    assert "宛如" in result.output


def test_quality_threshold_configurable(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("NOVEL_QUALITY_THRESHOLD", "100")
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply=AI_FLAVOR_SAMPLES[0]),
    )
    created = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert created.exit_code == 0, created.output
    draft_id = created.output.split()[1]
    assert _draft_status(workspace_id, draft_id) == "draft"


def test_invalid_quality_threshold_reports_config_error(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("NOVEL_QUALITY_THRESHOLD", "high")
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 1
    assert "invalid quality threshold" in result.output


def test_regenerate_accepted_draft_is_rejected(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply="他推开门，走进院子。"),
    )
    created = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    draft_id = created.output.split()[1]
    accepted = runner.invoke(app, ["decision", "accept", draft_id])
    assert accepted.exit_code == 0, accepted.output

    again = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert again.exit_code == 2
    assert "cannot regenerate an accepted draft" in again.output


def test_workspace_log_aggregates_flow(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply="他推开门，走进院子。"),
    )
    runner.invoke(app, ["talk", "send", workspace_id, "写一个雨夜故事"])
    created = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    draft_id = created.output.split()[1]
    runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "责编", "--content", "退稿：钩子不成立"],
    )
    runner.invoke(app, ["decision", "note", draft_id, "--content", "先补大纲"])

    log_result = runner.invoke(app, ["log", workspace_id])
    assert log_result.exit_code == 0, log_result.output
    assert "== 对话 ==" in log_result.output
    assert "== 草稿 ==" in log_result.output
    assert "== 意见 ==" in log_result.output
    assert "== 决策 ==" in log_result.output
    assert "退稿：钩子不成立" in log_result.output
    assert "先补大纲" in log_result.output

    settings = load_settings()
    log_text = build_workspace_log(DB(settings), workspace_id)
    assert "第一章" in log_text
