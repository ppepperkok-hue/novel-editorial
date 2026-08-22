"""Tests for M5-N26-S1: preset editorial band templates."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.style import get_style_anchor
from novel_editorial.core.templates import (
    TEMPLATES,
    BandTemplate,
    get_template,
    list_templates,
)
from novel_editorial.core.workspace import create_workspace
from novel_editorial.store.db import DB, DEFAULT_BAND
from novel_editorial.store.models import Agent, AgentRole, StyleAnchor

_BAND_FIELDS = (
    "role",
    "name",
    "personality",
    "stance",
    "values",
    "aesthetic",
    "emotion_baseline",
    "mood",
    "work_habits",
    "weaknesses",
    "relationship_presets",
    "private_motive",
)
_ROLES = (
    AgentRole.EDITOR_IN_CHIEF,
    AgentRole.EDITOR,
    AgentRole.WRITER,
    AgentRole.REVIEWER,
)


def _db(tmp_path: Path, monkeypatch) -> DB:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    db = DB(load_settings())
    db.init_schema()
    return db


def _agents_by_role(db: DB, workspace_id: str) -> dict[str, Agent]:
    with db.workspace_session(workspace_id) as session:
        agents = session.query(Agent).all()
    return {agent.role: agent for agent in agents}


def test_templates_fields_complete() -> None:
    assert set(TEMPLATES) == {"网文", "同人", "正统"}
    for template in TEMPLATES.values():
        assert template.name
        assert template.description
        assert template.style_description
        assert {member["role"] for member in template.band} == set(_ROLES)
        for member in template.band:
            assert set(member) == set(_BAND_FIELDS)
            assert member["name"]


def test_band_template_is_frozen() -> None:
    template = get_template("网文")
    with pytest.raises(FrozenInstanceError):
        template.__setattr__("name", "改名")


def test_list_templates_order_stable() -> None:
    first = [template.name for template in list_templates()]
    second = [template.name for template in list_templates()]
    assert first == ["网文", "同人", "正统"]
    assert second == first


def test_get_template_unknown_raises_usage_error() -> None:
    with pytest.raises(NovelError) as exc_info:
        get_template("不存在")
    assert exc_info.value.code == ErrorCode.USAGE_ERROR
    for name in ("网文", "同人", "正统"):
        assert name in exc_info.value.message


def test_create_workspace_with_template_persists_band_and_anchor(
    tmp_path: Path, monkeypatch
) -> None:
    db = _db(tmp_path, monkeypatch)
    template = get_template("同人")
    workspace = create_workspace(db, title="同人之书", template=template)

    by_role = _agents_by_role(db, workspace.id)
    assert set(by_role) == set(_ROLES)
    for member in template.band:
        agent = by_role[member["role"]]
        for field in _BAND_FIELDS:
            assert getattr(agent, field) == member[field]

    anchor = get_style_anchor(db, workspace.id)
    assert anchor.description == template.style_description
    assert anchor.forbidden_words == ""


def test_create_workspace_without_template_matches_default_band_and_no_anchor(
    tmp_path: Path, monkeypatch
) -> None:
    db = _db(tmp_path, monkeypatch)
    workspace = create_workspace(db, title="默认之书")

    by_role = _agents_by_role(db, workspace.id)
    assert set(by_role) == set(_ROLES)
    for member in DEFAULT_BAND:
        agent = by_role[member["role"]]
        for field in _BAND_FIELDS:
            assert getattr(agent, field) == member[field]

    with db.workspace_session(workspace.id) as session:
        anchor = session.query(StyleAnchor).filter_by(workspace_id=workspace.id).first()
    assert anchor is None


def test_create_workspace_with_empty_style_description_skips_anchor(
    tmp_path: Path, monkeypatch
) -> None:
    db = _db(tmp_path, monkeypatch)
    template = BandTemplate(
        name="无风格",
        description="测试",
        band=get_template("网文").band,
        style_description="",
    )
    workspace = create_workspace(db, title="无风格之书", template=template)

    assert set(_agents_by_role(db, workspace.id)) == set(_ROLES)
    with db.workspace_session(workspace.id) as session:
        anchor = session.query(StyleAnchor).filter_by(workspace_id=workspace.id).first()
    assert anchor is None
