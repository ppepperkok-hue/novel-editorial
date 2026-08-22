"""N27 S5 acceptance tests: the five free-will acceptance criteria (09/10).

Each criterion from docs/project-plan/10-free-will-checklist.md maps to at
least one executable assertion, all under the mock LLM (conftest pins
NOVEL_LLM_API_KEY away):

  1. 变体 (variant): the same multi-candidate trigger picks different partners
     under different freedom_seed and the exact same pick under one seed;
  2. 演化 (evolution): after real decide(action="reject") N times, the
     rejected writer's tendency for the same-kind trigger is lower than
     without history and decreases monotonically;
  3. 开关生效 (switches): proactive_enabled=false is fully silent (no
     message, no event, no motive), and motive_llm_enabled warns once when
     on and zero times when off;
  4. 不失控 (no runaway): triggering proactive behavior never modifies the
     draft body - DraftVersion rows and content stay unchanged, so the
     creative-chain gate is assertable;
  5. 可解释 (explainable): the proactive message payload exposes
     kind/trigger, and motives list exposes the source.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core import choice, proactive
from novel_editorial.core.config import Settings, load_settings
from novel_editorial.core.decision import decide
from novel_editorial.core.motives import derive_motives, list_motives
from novel_editorial.core.workspace import create_workspace
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import (
    Agent,
    AgentMotive,
    AgentRole,
    Draft,
    DraftVersion,
    Message,
)

runner = CliRunner()


def _make_db(
    tmp_path: Path,
    *,
    proactive_enabled: bool = True,
    proactive_max_per_agent: int = 3,
    freedom_dial: float = 0.0,
    freedom_seed: int = 42,
    motive_llm_enabled: bool = False,
) -> tuple[DB, str]:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_path=tmp_path / "config.toml",
        proactive_enabled=proactive_enabled,
        proactive_max_per_agent=proactive_max_per_agent,
        freedom_dial=freedom_dial,
        freedom_seed=freedom_seed,
        motive_llm_enabled=motive_llm_enabled,
    )
    db = DB(settings)
    db.init_schema()
    workspace = create_workspace(db, title="自由之书", genre="悬疑")
    return db, workspace.id


def _agent_row(db: DB, workspace_id: str, role: str) -> Agent:
    with db.workspace_session(workspace_id) as session:
        agent = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, role=role)
            .first()
        )
    assert agent is not None
    return agent


def _agent_name(db: DB, workspace_id: str, role: str) -> str:
    return _agent_row(db, workspace_id, role).name


def _isolate_trigger_registry(monkeypatch) -> None:
    """Give one test its own registry copy so wired-trigger extras never leak."""
    monkeypatch.setattr(
        proactive,
        "_PROACTIVE_TRIGGERS",
        {
            trigger: list(specs)
            for trigger, specs in proactive._PROACTIVE_TRIGGERS.items()
        },
    )


def _register_talk_contestants(db: DB, workspace_id: str) -> None:
    """Add editor/writer contestants to talk_first_round besides the built-in 总编."""
    editor = _agent_name(db, workspace_id, AgentRole.EDITOR)
    writer = _agent_name(db, workspace_id, AgentRole.WRITER)
    proactive.register_proactive_trigger(
        trigger="talk_first_round",
        agent=editor,
        kind=proactive.PROACTIVE_KIND_REVIEW,
        content="责编候选",
        condition=lambda context: True,
    )
    proactive.register_proactive_trigger(
        trigger="talk_first_round",
        agent=writer,
        kind=proactive.PROACTIVE_KIND_QUESTION,
        content="写手候选",
        condition=lambda context: True,
    )


def _neutralize_params(db: DB, workspace_id: str) -> None:
    """Give every partner identical neutral params so only the seed matters."""
    with db.workspace_session(workspace_id) as session:
        for agent in session.query(Agent).filter_by(workspace_id=workspace_id).all():
            agent.proactivity = 5
            agent.stubbornness = 5
            agent.talkativeness = 5
            agent.patience = 5
        session.commit()


def _dial_settings(tmp_path: Path, seed: int) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        config_path=tmp_path / "config.toml",
        proactive_enabled=True,
        proactive_max_per_agent=3,
        freedom_dial=1.0,
        freedom_seed=seed,
        motive_llm_enabled=False,
    )


@pytest.mark.smoke
def test_acceptance_variant_seed_changes_pick_same_seed_reproduces(
    tmp_path: Path, monkeypatch
) -> None:
    """FW-G2: same multi-candidate trigger, different seed -> variant; same seed -> same."""
    _isolate_trigger_registry(monkeypatch)
    db, workspace_id = _make_db(tmp_path, freedom_dial=1.0, freedom_seed=0)
    _register_talk_contestants(db, workspace_id)
    _neutralize_params(db, workspace_id)
    context = {"first_round": True, "has_style_anchor": False}

    picks: dict[int, str] = {}
    for seed in range(40):
        db.settings = _dial_settings(tmp_path, seed)
        fired = proactive.evaluate_proactive_triggers(
            db, workspace_id, "talk_first_round", context
        )
        assert len(fired) == 1
        picks[seed] = fired[0].agent

    distinct = sorted(set(picks.values()))
    assert len(distinct) >= 2
    seed_a = next(seed for seed, agent in picks.items() if agent == distinct[0])
    seed_b = next(seed for seed, agent in picks.items() if agent == distinct[1])
    assert seed_a != seed_b

    db.settings = _dial_settings(tmp_path, seed_a)
    first_a = proactive.evaluate_proactive_triggers(
        db, workspace_id, "talk_first_round", context
    )
    second_a = proactive.evaluate_proactive_triggers(
        db, workspace_id, "talk_first_round", context
    )
    assert first_a == second_a

    db.settings = _dial_settings(tmp_path, seed_b)
    first_b = proactive.evaluate_proactive_triggers(
        db, workspace_id, "talk_first_round", context
    )
    second_b = proactive.evaluate_proactive_triggers(
        db, workspace_id, "talk_first_round", context
    )
    assert first_b == second_b
    assert first_a != first_b


@pytest.mark.smoke
def test_acceptance_evolution_rejections_lower_same_kind_tendency(
    tmp_path: Path,
) -> None:
    """FW-G3: real rejections lower the same-kind tendency, monotonically."""
    db, workspace_id = _make_db(tmp_path)
    writer = _agent_row(db, workspace_id, AgentRole.WRITER)
    derive_motives(db, workspace_id, "draft_generated", {"agent_id": writer.id})
    candidate = choice.ChoiceCandidate(
        agent=writer.id, kind="proactive_report", content="交稿候选"
    )
    agents = {writer.id: writer.role}
    params = {
        writer.id: choice.PersonalityParams(
            proactivity=5, stubbornness=6, talkativeness=5, patience=4
        )
    }
    motives = list_motives(db, workspace_id)

    weights: list[float] = []
    for index in range(5):
        with db.workspace_session(workspace_id) as session:
            draft = Draft(
                workspace_id=workspace_id, title=f"第{index}章", status="draft"
            )
            session.add(draft)
            session.commit()
            draft_id = draft.id
        decide(db, workspace_id, draft_id, action="reject")
        feedback = choice.load_feedback_counts(db, workspace_id)
        weight = choice.compute_weights(
            [candidate],
            motives,
            params,
            feedback,
            agents=agents,
            trigger="draft_generated",
        )[0]
        weights.append(weight)

    assert weights == sorted(weights, reverse=True)
    assert len(set(weights)) == len(weights)
    assert weights[-1] < weights[0]


@pytest.mark.smoke
def test_acceptance_switch_proactive_disabled_full_silence(
    tmp_path: Path,
) -> None:
    """FW-G4: proactive_enabled=false -> no message, no event, no motive."""
    db, workspace_id = _make_db(tmp_path, proactive_enabled=False)
    context = {"title": "第一章", "current_version": 1, "passed": True}

    assert (
        proactive.evaluate_proactive_triggers(
            db, workspace_id, "draft_generated", context
        )
        == []
    )
    assert (
        proactive.record_proactive_messages(
            db, workspace_id, "draft_generated", context
        )
        == []
    )
    with db.workspace_session(workspace_id) as session:
        assert session.query(Message).count() == 0
    assert list_events(db, workspace_id) == []
    assert list_motives(db, workspace_id) == []


@pytest.mark.smoke
def test_acceptance_switch_motive_llm_warns_once_when_enabled(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """FW-G4: motive_llm_enabled=true warns once; false warns zero times."""
    monkeypatch.setattr(proactive, "_motive_llm_warning_shown", False)
    db, workspace_id = _make_db(tmp_path, motive_llm_enabled=True)
    context = {"description": "平实克制短句"}
    for _ in range(2):
        fired = proactive.evaluate_proactive_triggers(
            db, workspace_id, "style_set", context
        )
        assert fired == [
            proactive.ProactiveCandidate(
                agent="审稿",
                kind=proactive.PROACTIVE_KIND_CONSISTENCY,
                content=(
                    "风格锚点定了：「$description」。"
                    "我盯着设定看了一遍，开头那句跟「$description」会不会打架？"
                ),
            )
        ]
    captured = capsys.readouterr()
    assert captured.err.count(proactive.MOTIVE_LLM_WARNING) == 1

    monkeypatch.setattr(proactive, "_motive_llm_warning_shown", False)
    db_off, workspace_off = _make_db(
        tmp_path / "off", motive_llm_enabled=False
    )
    proactive.evaluate_proactive_triggers(
        db_off, workspace_off, "style_set", context
    )
    captured_off = capsys.readouterr()
    assert captured_off.err == ""


@pytest.mark.smoke
def test_acceptance_no_runaway_draft_body_untouched(
    tmp_path: Path, monkeypatch
) -> None:
    """FW-G4 red line: proactive behavior never writes the draft body."""
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )
    created = runner.invoke(app, ["works", "create", "守门之书"])
    assert created.exit_code == 0, created.output
    workspace_id = created.output.split()[2].rstrip(":")
    db = DB(load_settings())

    def snapshot_versions() -> list[tuple[int, str]]:
        with db.workspace_session(workspace_id) as session:
            rows = (
                session.query(DraftVersion)
                .order_by(DraftVersion.version)
                .all()
            )
            return [(row.version, row.content) for row in rows]

    assert snapshot_versions() == []
    generated = runner.invoke(
        app, ["draft", "generate", workspace_id, "--title", "第一章"]
    )
    assert generated.exit_code == 0, generated.output
    assert "写手: 《第一章》初稿写完了" in generated.output
    assert "责编: 《第一章》过了质量门" in generated.output
    assert snapshot_versions() == [(1, "正文内容")]

    styled = runner.invoke(
        app,
        ["style", "set", workspace_id, "--description", "克制、留白"],
    )
    assert styled.exit_code == 0, styled.output
    assert "审稿: 风格锚点定了" in styled.output
    assert snapshot_versions() == [(1, "正文内容")]
    with db.workspace_session(workspace_id) as session:
        drafts = session.query(Draft).all()
        assert len(drafts) == 1
        assert drafts[0].status == "draft"
        assert drafts[0].current_version == 1


@pytest.mark.smoke
def test_acceptance_explainable_payload_and_motive_source(
    tmp_path: Path, monkeypatch
) -> None:
    """FW-G1: payload exposes kind/trigger; motives list exposes the source."""
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )
    created = runner.invoke(app, ["works", "create", "可解释之书"])
    assert created.exit_code == 0, created.output
    workspace_id = created.output.split()[2].rstrip(":")
    generated = runner.invoke(
        app, ["draft", "generate", workspace_id, "--title", "第一章"]
    )
    assert generated.exit_code == 0, generated.output

    db = DB(load_settings())
    with db.workspace_session(workspace_id) as session:
        payloads = [
            json.loads(message.payload)
            for message in session.query(Message).all()
        ]
    proactive_payloads = [
        payload
        for payload in payloads
        if payload.get("initiator") == proactive.INITIATOR_AGENT
    ]
    reports = [
        payload
        for payload in proactive_payloads
        if payload.get("kind") == "proactive_report"
    ]
    reviews = [
        payload
        for payload in proactive_payloads
        if payload.get("kind") == "proactive_review"
    ]
    assert reports and reports[0]["trigger"] == "draft_generated"
    assert reviews and reviews[0]["trigger"] == "draft_gate_passed"

    listed = runner.invoke(app, ["events", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert '"kind": "proactive_report", "trigger": "draft_generated"' in listed.output
    assert "proactive_review" in listed.output

    motives = runner.invoke(app, ["motives", "list", workspace_id])
    assert motives.exit_code == 0, motives.output
    assert "[写手]" in motives.output
    assert "[goal]" in motives.output
    assert "source=event:draft_generated" in motives.output
    assert "新章已交" in motives.output

    filtered = runner.invoke(
        app, ["motives", "list", workspace_id, "--agent", "写手"]
    )
    assert filtered.exit_code == 0, filtered.output
    assert "source=event:draft_generated" in filtered.output

    with db.workspace_session(workspace_id) as session:
        stored = session.query(AgentMotive).all()
    assert len(stored) == 1
    assert stored[0].source == "event:draft_generated"
