"""Relationship dynamics (S7): per-pair trust/friction/familiarity.

Events move the numbers: rejected feedback raises friction, accepted
proposals and kept promises raise trust, collaboration raises familiarity.
Values stay in [0, 1] and decay weekly so stale history fades.
"""

from __future__ import annotations

from datetime import datetime, timedelta

DELTAS = {
    "feedback_rejected": {"friction": 0.10},
    "proposal_accepted": {"trust": 0.10},
    "collaboration": {"familiarity": 0.05},
    "promise_kept": {"trust": 0.10},
    "promise_broken": {"trust": -0.10, "friction": 0.05},
}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clamp(value):
    return max(0.0, min(1.0, round(float(value or 0.0), 4)))


def _err(message):
    return {"ok": False, "error": message}


def ensure(conn, agent, other, novel_id=0):
    """Create the relationship row when missing; always returns the row."""
    agent = str(agent or "").strip()
    other = str(other or "").strip()
    novel_id = int(novel_id or 0)
    if not agent or not other:
        return _err("agent and other are required")
    row = conn.execute(
        "SELECT * FROM agent_relations WHERE agent=? AND other=? AND novel_id=?",
        (agent, other, novel_id),
    ).fetchone()
    if row:
        return {"ok": True, "relation": dict(row)}
    conn.execute(
        "INSERT INTO agent_relations(agent,other,novel_id,familiarity,trust,friction,updated_at) "
        "VALUES(?,?,?,0,0,0,?)",
        (agent, other, novel_id, _now()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM agent_relations WHERE agent=? AND other=? AND novel_id=?",
        (agent, other, novel_id),
    ).fetchone()
    return {"ok": True, "relation": dict(row)}


def apply_event(conn, agent, other, event_type, novel_id=0):
    """Apply one relationship event; unknown events are ignored explicitly."""
    if event_type not in DELTAS:
        return _err(f"unknown event_type: {event_type}")
    created = ensure(conn, agent, other, novel_id)
    if not created.get("ok"):
        return created
    relation = created["relation"]
    deltas = DELTAS[event_type]
    for key, delta in deltas.items():
        relation[key] = _clamp(float(relation.get(key) or 0.0) + delta)
    conn.execute(
        "UPDATE agent_relations SET familiarity=?, trust=?, friction=?, updated_at=? "
        "WHERE id=?",
        (
            relation["familiarity"],
            relation["trust"],
            relation["friction"],
            _now(),
            relation["id"],
        ),
    )
    conn.commit()
    return {"ok": True, "relation": relation, "event": event_type}


def decay(conn, novel_id=0, days=7):
    """Decay trust/familiarity 5% and friction 10% per 7 days, scaled by
    the elapsed `days`; values stay in [0, 1]."""
    try:
        scale = max(0.0, float(days or 0)) / 7.0
    except (TypeError, ValueError):
        scale = 1.0
    trust_factor = 0.95 ** scale
    friction_factor = 0.90 ** scale
    scope = "AND novel_id=?" if novel_id else ""
    params = (int(novel_id),) if novel_id else ()
    rows = conn.execute(
        f"SELECT id, familiarity, trust, friction FROM agent_relations "
        f"WHERE (familiarity>0 OR trust>0 OR friction>0) {scope}",
        params,
    ).fetchall()
    updated = 0
    for row in rows:
        familiarity = _clamp(float(row["familiarity"] or 0.0) * trust_factor)
        trust = _clamp(float(row["trust"] or 0.0) * trust_factor)
        friction = _clamp(float(row["friction"] or 0.0) * friction_factor)
        if (familiarity, trust, friction) != (
            float(row["familiarity"] or 0.0),
            float(row["trust"] or 0.0),
            float(row["friction"] or 0.0),
        ):
            conn.execute(
                "UPDATE agent_relations SET familiarity=?, trust=?, friction=? "
                "WHERE id=?",
                (familiarity, trust, friction, row["id"]),
            )
            updated += 1
    conn.commit()
    return {"ok": True, "decayed": updated}
