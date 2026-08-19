from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import record_message
from novel_editorial.core.config import load_settings
from novel_editorial.core.memory import archive_memory_notes
from novel_editorial.core.setting import add_setting
from novel_editorial.core.views import search_all_layers, search_memory
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, AgentMemory, SettingEntry

runner = CliRunner()


def _create_workspace(
    tmp_path: Path,
    monkeypatch,
    *,
    title: str = "视图之书",
    genre: str = "都市",
    description: str = "雨夜的都市故事",
) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(
        app,
        [
            "works",
            "create",
            title,
            "--genre",
            genre,
            "--description",
            description,
        ],
    )
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _add_note(workspace_id: str, target: str, content: str) -> None:
    result = runner.invoke(
        app,
        ["memory", "note", workspace_id, target, "--content", content, "--as", target],
    )
    assert result.exit_code == 0, result.output


def _writer_id(db: DB, workspace_id: str) -> str:
    with db.workspace_session(workspace_id) as session:
        writer = session.query(Agent).filter_by(workspace_id=workspace_id, role="writer").first()
        assert writer is not None
        return writer.id


def _add_raw_note(
    db: DB,
    workspace_id: str,
    agent_id: str,
    content: str,
    *,
    strength: int = 100,
    last_accessed_at: datetime | None = None,
    created_at: datetime | None = None,
) -> AgentMemory:
    with db.workspace_session(workspace_id) as session:
        note = AgentMemory(
            workspace_id=workspace_id,
            agent_id=agent_id,
            content=content,
            strength=strength,
            last_accessed_at=last_accessed_at or datetime.now(UTC),
            created_at=created_at or datetime.now(UTC),
        )
        session.add(note)
        session.commit()
        return note


def test_writer_view_includes_own_notes_only(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _add_note(workspace_id, "写手", "写手私藏")
    _add_note(workspace_id, "责编", "责编私藏")

    viewed = runner.invoke(app, ["memory", "view", workspace_id, "--as", "写手"])
    assert viewed.exit_code == 0, viewed.output
    assert "写手私藏" in viewed.output
    assert "责编私藏" not in viewed.output
    assert "视图之书" in viewed.output
    assert "章纲" in viewed.output

    packed = runner.invoke(app, ["memory", "pack", workspace_id])
    assert packed.exit_code == 0, packed.output
    assert packed.output == viewed.output


@pytest.mark.parametrize("role", ["总编", "主编", "责编"])
def test_editor_view_profile_and_conversation_without_private_memory(
    tmp_path: Path, monkeypatch, role: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _add_note(workspace_id, "写手", "写手私藏")
    settings = load_settings()
    db = DB(settings)
    record_message(db, workspace_id, role="author", actor="作者", content="主角动机到底是什么")
    record_message(db, workspace_id, role="agent", actor="写手", content="他想要一场公平的雨")

    viewed = runner.invoke(app, ["memory", "view", workspace_id, "--as", role])
    assert viewed.exit_code == 0, viewed.output
    assert "作品档案" in viewed.output
    assert "视图之书" in viewed.output
    assert "雨夜的都市故事" in viewed.output
    assert "最近对话" in viewed.output
    assert "主角动机到底是什么" in viewed.output
    assert "他想要一场公平的雨" in viewed.output
    assert "写手私藏" not in viewed.output


def test_boss_view_band_drafts_reviews_decisions(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="雨夜的开场，钩子埋下。"),
    )
    generated = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "雨夜"])
    assert generated.exit_code == 0, generated.output
    draft_id = generated.output.split()[1]
    assert (
        runner.invoke(
            app,
            ["review", "add", draft_id, "--from", "责编", "--content", "钩子再亮一点"],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            ["decision", "note", draft_id, "--content", "方向没问题"],
        ).exit_code
        == 0
    )

    viewed = runner.invoke(app, ["memory", "view", workspace_id, "--as", "作者"])
    assert viewed.exit_code == 0, viewed.output
    assert "班子状态" in viewed.output
    for name in ("总编", "责编", "写手", "审稿"):
        assert name in viewed.output
    assert "草稿" in viewed.output
    assert "雨夜" in viewed.output
    assert "v1" in viewed.output
    assert "最近意见" in viewed.output
    assert "钩子再亮一点" in viewed.output
    assert "最近决策" in viewed.output
    assert "方向没问题" in viewed.output


def test_memory_view_invalid_role_exit_2(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["memory", "view", workspace_id, "--as", "路人"])
    assert result.exit_code == 2
    assert "invalid view role" in result.output


def test_memory_view_missing_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["memory", "view", "nope", "--as", "主编"])
    assert result.exit_code == 1
    assert "workspace not found" in result.output


@pytest.mark.smoke
def test_memory_search_hits_every_source_with_citation(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch, description="钩子驱动的悬疑故事")
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="雨夜开场，钩子埋在最暗处。"),
    )
    generated = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert generated.exit_code == 0, generated.output
    draft_id = generated.output.split()[1]
    settings = load_settings()
    db = DB(settings)
    record_message(db, workspace_id, role="author", actor="作者", content="第三章的钩子别忘了")
    assert (
        runner.invoke(
            app,
            ["review", "add", draft_id, "--from", "责编", "--content", "这个钩子太弱了"],
        ).exit_code
        == 0
    )
    _add_note(workspace_id, "写手", "钩子埋在下雨天")

    result = runner.invoke(app, ["memory", "search", workspace_id, "钩子"])
    assert result.exit_code == 0, result.output
    assert "[档案]" in result.output
    assert "（来源: 作品《视图之书》）" in result.output
    assert "[对话]" in result.output
    assert "（来源: 作者）" in result.output
    assert "[意见]" in result.output
    assert "（来源: 责编）" in result.output
    assert "[版本]" in result.output
    assert "（来源: 第一章 v1）" in result.output
    assert "[笔记]" in result.output
    assert "（来源: 写手）" in result.output
    assert "钩子埋在最暗处" in result.output


def test_memory_search_is_case_insensitive(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _add_note(workspace_id, "写手", "The Hook is here")

    result = runner.invoke(app, ["memory", "search", workspace_id, "hook"])
    assert result.exit_code == 0, result.output
    assert "[笔记]" in result.output
    assert "The Hook is here" in result.output


def test_memory_search_isolated_between_workspaces(tmp_path: Path, monkeypatch) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, title="甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, title="乙书")
    _add_note(workspace_a, "写手", "甲书秘密钩子")

    leaked = runner.invoke(app, ["memory", "search", workspace_b, "甲书秘密钩子"])
    assert leaked.exit_code == 0, leaked.output
    assert leaked.output.strip() == "no matches"

    found = runner.invoke(app, ["memory", "search", workspace_a, "甲书秘密钩子"])
    assert found.exit_code == 0, found.output
    assert "[笔记]" in found.output


def test_memory_search_no_matches(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["memory", "search", workspace_id, "不存在的词"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "no matches"


def test_memory_search_blank_keyword_usage_error(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["memory", "search", workspace_id, "   "])
    assert result.exit_code == 2
    assert "must not be empty" in result.output


def test_memory_search_escapes_like_wildcards(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _add_note(workspace_id, "写手", "进度100%达标")
    _add_note(workspace_id, "写手", "进度100分达标")
    _add_note(workspace_id, "写手", "代号a_b")
    _add_note(workspace_id, "写手", "代号aXb")
    _add_note(workspace_id, "写手", r"路径 C:\temp 存档")

    percent = runner.invoke(app, ["memory", "search", workspace_id, "%"])
    assert percent.exit_code == 0, percent.output
    assert "进度100%达标" in percent.output
    assert "进度100分达标" not in percent.output
    assert "代号a_b" not in percent.output
    assert "代号aXb" not in percent.output
    assert r"路径 C:\temp 存档" not in percent.output

    underscore = runner.invoke(app, ["memory", "search", workspace_id, "_"])
    assert underscore.exit_code == 0, underscore.output
    assert "代号a_b" in underscore.output
    assert "代号aXb" not in underscore.output
    assert "进度100%达标" not in underscore.output

    backslash = runner.invoke(app, ["memory", "search", workspace_id, "\\"])
    assert backslash.exit_code == 0, backslash.output
    assert r"路径 C:\temp 存档" in backslash.output
    assert "进度100%达标" not in backslash.output
    assert "代号a_b" not in backslash.output

    composite = runner.invoke(app, ["memory", "search", workspace_id, "100%达标"])
    assert composite.exit_code == 0, composite.output
    assert "进度100%达标" in composite.output
    assert "进度100分达标" not in composite.output


@pytest.mark.parametrize(
    ("searcher", "expected_tables"),
    [
        (search_memory, ("messages", "reviews", "draft_versions", "agent_memories")),
        (
            search_all_layers,
            (
                "messages",
                "reviews",
                "draft_versions",
                "agent_memories",
                "decisions",
                "plot_threads",
            ),
        ),
    ],
)
def test_search_filters_text_layers_in_sql(
    tmp_path: Path, monkeypatch, searcher, expected_tables
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)

    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(Engine, "after_cursor_execute", capture)
    try:
        searcher(db, workspace_id, "钩子")
    finally:
        event.remove(Engine, "after_cursor_execute", capture)

    selects = {table: [] for table in expected_tables}
    for statement in statements:
        lowered = statement.lower()
        if not lowered.startswith("select"):
            continue
        for table in expected_tables:
            if table in lowered:
                selects[table].append(statement)
    for table in expected_tables:
        assert selects[table], f"no SELECT reached the {table} layer"
        assert all(
            "like" in statement.lower() for statement in selects[table]
        ), f"{table} layer was not filtered in SQL with LIKE"


@pytest.mark.parametrize("searcher", [search_memory, search_all_layers])
def test_search_excludes_archived_notes(
    tmp_path: Path, monkeypatch, searcher
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)
    note = _add_raw_note(db, workspace_id, writer_id, "归档前的秘密钩子")
    archive_memory_notes(db, workspace_id, [note.id])

    result = searcher(db, workspace_id, "秘密钩子")
    assert "[笔记]" not in result
    assert "归档前的秘密钩子" not in result


def test_search_memory_orders_notes_by_effective_strength(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    (tmp_path / "config.toml").write_text(
        "[defaults]\nmemory_decay_per_day = 5\n", encoding="utf-8"
    )
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)
    now = datetime.now(UTC)
    _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "钩子甲",
        strength=100,
        last_accessed_at=now - timedelta(days=10),
        created_at=now - timedelta(days=3),
    )
    _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "钩子乙",
        strength=80,
        last_accessed_at=now - timedelta(days=2),
        created_at=now - timedelta(days=2),
    )
    _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "钩子丙",
        strength=100,
        last_accessed_at=now - timedelta(days=1),
        created_at=now - timedelta(days=1),
    )

    result = search_memory(db, workspace_id, "钩子")
    note_lines = [line for line in result.splitlines() if line.startswith("[笔记]")]
    assert len(note_lines) == 3
    # effective strength: 丙 95, 乙 70, 甲 50; stored strength would tie 甲/丙.
    assert "钩子丙" in note_lines[0]
    assert "钩子乙" in note_lines[1]
    assert "钩子甲" in note_lines[2]


def test_search_memory_fts_and_like_agree_on_notes(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)
    now = datetime.now(UTC)
    for index in range(3):
        _add_raw_note(
            db,
            workspace_id,
            writer_id,
            f"共识钩子{index}",
            strength=50,
            last_accessed_at=now,
            created_at=now - timedelta(minutes=3 - index),
        )
    archived = _add_raw_note(db, workspace_id, writer_id, "归档共识钩子")
    archive_memory_notes(db, workspace_id, [archived.id])

    liked = search_memory(db, workspace_id, "共识钩子", _force_fts=False)
    ftsed = search_memory(db, workspace_id, "共识钩子", _force_fts=True)
    assert ftsed == liked
    assert "归档共识钩子" not in ftsed
    note_lines = [line for line in ftsed.splitlines() if line.startswith("[笔记]")]
    assert len(note_lines) == 3
    assert "共识钩子0" in note_lines[0]
    assert "共识钩子1" in note_lines[1]
    assert "共识钩子2" in note_lines[2]


def test_search_rehearses_hit_notes_and_caps_at_100(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    (tmp_path / "config.toml").write_text(
        "[defaults]\nmemory_rehearsal_boost = 25\n", encoding="utf-8"
    )
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)
    hit = _add_raw_note(db, workspace_id, writer_id, "会被想起的钩子", strength=90)
    miss = _add_raw_note(db, workspace_id, writer_id, "无关内容", strength=90)

    search_memory(db, workspace_id, "钩子")
    with db.workspace_session(workspace_id) as session:
        hit_refreshed = session.query(AgentMemory).filter_by(id=hit.id).first()
        miss_refreshed = session.query(AgentMemory).filter_by(id=miss.id).first()
    assert hit_refreshed is not None
    assert hit_refreshed.strength == 100
    assert miss_refreshed is not None
    assert miss_refreshed.strength == 90


def test_search_rehearsal_failure_keeps_result_and_warns(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)
    _add_raw_note(db, workspace_id, writer_id, "抢救失败的钩子")

    def boom(*args, **kwargs):
        raise RuntimeError("rehearsal write failed")

    monkeypatch.setattr("novel_editorial.core.views.rehearse_memory_note", boom)
    result = search_memory(db, workspace_id, "钩子")
    assert "[笔记]" in result
    assert "抢救失败的钩子" in result
    captured = capsys.readouterr()
    assert "warning: memory rehearsal failed" in captured.err
    assert "rehearsal write failed" in captured.err


@pytest.mark.smoke
def test_search_memory_hits_setting_layer_with_citation(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    add_setting(
        db,
        workspace_id,
        kind="character",
        name="林墨",
        content="雨夜里沉默寡言的侦探",
        source="第一章手稿",
    )

    result = search_memory(db, workspace_id, "雨夜")
    assert "[设定] 人物：林墨——雨夜里沉默寡言的侦探（来源: 第一章手稿 v1）" in result

    all_layers = search_all_layers(db, workspace_id, "雨夜")
    assert "[设定] 人物：林墨——雨夜里沉默寡言的侦探（来源: 第一章手稿 v1）" in all_layers


def test_search_setting_layer_matches_name_only(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    add_setting(
        db,
        workspace_id,
        kind="timeline",
        name="雨夜时间线",
        content="第一章",
        source="作者",
    )

    result = search_memory(db, workspace_id, "雨夜")
    assert "[设定] 时间线：雨夜时间线——第一章（来源: 作者 v1）" in result


def test_search_setting_layer_fts_and_like_agree(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    add_setting(
        db,
        workspace_id,
        kind="world",
        name="世界观",
        content="灵气复苏三百年",
        source="大纲",
    )

    liked = search_memory(db, workspace_id, "灵气复苏", _force_fts=False)
    ftsed = search_memory(db, workspace_id, "灵气复苏", _force_fts=True)
    assert ftsed == liked
    assert "[设定]" in ftsed

    liked_all = search_all_layers(db, workspace_id, "灵气复苏", _force_fts=False)
    ftsed_all = search_all_layers(db, workspace_id, "灵气复苏", _force_fts=True)
    assert ftsed_all == liked_all
    assert "[设定]" in ftsed_all


def test_search_without_settings_keeps_other_layers(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _add_note(workspace_id, "写手", "钩子埋在下雨天")
    db = DB(load_settings())

    result = search_memory(db, workspace_id, "钩子")
    assert "[设定]" not in result
    assert "[笔记]" in result

    all_layers = search_all_layers(db, workspace_id, "钩子")
    assert "[设定]" not in all_layers
    assert "[笔记]" in all_layers


def test_search_setting_layer_isolated_between_workspaces(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, title="甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, title="乙书")
    db = DB(load_settings())
    add_setting(
        db,
        workspace_a,
        kind="character",
        name="甲书角色",
        content="只属于甲书的秘密钩子",
        source="作者",
    )

    leaked = search_memory(db, workspace_b, "只属于甲书的秘密钩子")
    assert leaked == "no matches"
    leaked_all = search_all_layers(db, workspace_b, "只属于甲书的秘密钩子")
    assert leaked_all == "no matches"

    found = search_memory(db, workspace_a, "只属于甲书的秘密钩子")
    assert "[设定]" in found


def test_search_setting_layer_orders_by_updated_at(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    now = datetime.now(UTC)
    with db.workspace_session(workspace_id) as session:
        session.add(
            SettingEntry(
                workspace_id=workspace_id,
                kind="character",
                name="甲",
                content="钩子甲",
                source="作者",
                current_version=1,
                created_at=now - timedelta(days=2),
                updated_at=now - timedelta(days=2),
            )
        )
        session.add(
            SettingEntry(
                workspace_id=workspace_id,
                kind="character",
                name="乙",
                content="钩子乙",
                source="作者",
                current_version=1,
                created_at=now - timedelta(days=1),
                updated_at=now - timedelta(days=1),
            )
        )
        session.commit()

    result = search_memory(db, workspace_id, "钩子")
    setting_lines = [line for line in result.splitlines() if line.startswith("[设定]")]
    assert len(setting_lines) == 2
    assert "钩子甲" in setting_lines[0]
    assert "钩子乙" in setting_lines[1]
