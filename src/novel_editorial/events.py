"""Shared event contract for collaboration logs and visibility."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EventType(StrEnum):
    SYSTEM = "system"
    AGENT_MESSAGE = "agent.message"
    DRAFT_CREATED = "draft.created"
    QUALITY_GATE_PASSED = "quality_gate.passed"
    DECISION_REQUESTED = "decision.requested"
    REVIEW_REJECTED = "review.rejected"


class Event(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    type: EventType
    time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor: str
    workspace: str | None = None
    payload: dict = Field(default_factory=dict)
