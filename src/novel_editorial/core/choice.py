"""Free-will behavior selector (N27 S3): coarse filter, weights, weighted pick.

The three-stage pipeline is pure local math and never calls an LLM:

  1. ``coarse_filter`` - deterministic relevance cut. A candidate survives
     only when its agent's role duties cover the trigger's topic, or the
     agent carries a motive that matches the topic. Unrelated partners and
     candidates are skipped at zero cost.
  2. ``compute_weights`` - tendency = situational relevance x motive strength
     (0-100 normalized) x personality params (0-10 normalized) x history
     feedback (refusal/acceptance counts folded from behavior_timeline). The
     output is a comparable weight in [0, 1] per candidate; it is deliberately
     NOT normalized to sum to 1 so the values stay comparable across scenes
     (a scene with one strong candidate keeps a high weight). The weighted
     pick normalizes internally.
  3. ``pick_candidate`` - weighted random with a fixed seed. dial=0 always
     picks the highest-weight candidate (deterministic); dial in (0, 1]
     interpolates the distribution towards uniform, so low-weight candidates
     may be picked. dial must be in [0, 1].

``evaluate_choice`` is the silence entrance: it returns an empty list when
there are no candidates or when the best weight is below ``min_weight``. It
only computes tendencies - persisting silence is N28's job, nothing is written
to any database here.

Motive hits and personality params come from function arguments, never from
this layer's own queries. The only database access is the read-only
``load_feedback_counts`` helper that counts refusals / acceptances on
behavior_timeline; the weight functions themselves are side-effect free.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from random import Random

from sqlalchemy import func

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import (
    AgentMotive,
    AgentRole,
    BehaviorTimeline,
    MotiveKind,
)

#: Default silence threshold for ``evaluate_choice``. A neutral candidate
#: scores about 0.5 (relevance 1.0 x neutral motive 1.0 x neutral personality
#: 0.5 x no feedback 1.0), so 0.05 is only crossed by partners whose feedback
#: factor hit the 0.1 floor (roughly 35+ refusals) or whose personality factor
#: is near zero. Defaulting to "almost never silent" keeps the N1 single-
#: candidate behaviors firing unchanged (S4 compatibility); callers can raise
#: the threshold when they want a more selective office.
DEFAULT_MIN_WEIGHT = 0.05

#: One refusal multiplies the tendency by 1 / (1 + 0.25) ~= 0.8 (four refusals
#: halve it); one acceptance multiplies it by 1.25. The rates are symmetric
#: and mild on purpose: a single refusal must never silence a partner
#: (stubbornness is a first-class parameter, N27-C), while repeated refusals
#: visibly lower the same-kind tendency (FW-G3 evolution).
REJECT_PENALTY = 0.25
ACCEPT_BONUS = 0.25

#: History feedback is clamped to [0.1, 1.0]. The floor keeps a minimum
#: willingness to participate no matter how often the partner was rejected
#: (silence is optional, not a punishment - 09 design); the 1.0 ceiling means
#: acceptances restore the tendency but never push a partner above the
#: no-burden baseline, so no single factor dominates the product.
FEEDBACK_FLOOR = 0.1

#: Situational-relevance grades used by ``compute_weights``. A candidate whose
#: role duty AND a matching motive both cover the trigger topic is the most
#: relevant (1.0); role duty alone is 0.8 (in charge but not personally
#: invested); a matching motive alone is 0.6 (carrying something but outside
#: the role's beat). When no trigger/agents are supplied the relevance is
#: neutral 1.0: the caller already guaranteed the coarse filter.
RELEVANCE_ROLE_AND_MOTIVE = 1.0
RELEVANCE_ROLE_ONLY = 0.8
RELEVANCE_MOTIVE_ONLY = 0.6
RELEVANCE_UNSPECIFIED = 1.0


@dataclass(frozen=True)
class ChoiceCandidate:
    """One candidate behavior: an agent, a kind, and a content template.

    ``agent`` is the caller's stable agent identifier - the same key space as
    the ``agents`` and ``params`` mappings. ``content`` may contain ``$``
    placeholders; rendering is S4's job, this layer never renders.
    """

    agent: str
    kind: str
    content: str


@dataclass(frozen=True)
class PersonalityParams:
    """The four personality parameters (N27-C), integers in 0-10."""

    proactivity: int
    stubbornness: int
    talkativeness: int
    patience: int


@dataclass(frozen=True)
class FeedbackCounts:
    """History feedback for one agent: refusal / acceptance counts."""

    rejected: int = 0
    accepted: int = 0


#: Neutral personality fallback. Matches the Agent constructor's unknown-role
#: fallback in store/models.py, so a missing params entry never blocks speech.
DEFAULT_PERSONALITY = PersonalityParams(proactivity=5, stubbornness=5, talkativeness=5, patience=5)

#: behavior_timeline sources counted as a refusal / an acceptance. decision:
#: rows are author verdicts on the writer's draft (agent_id = the writer);
#: delegation: rows are partner-to-partner requests (agent_id = the requester
#: whose initiative was refused / accepted). review:add and refusal:* rows are
#: opinions, not verdicts, and are deliberately not counted.
REJECTED_SOURCES = ("decision:reject", "delegation:refused")
ACCEPTED_SOURCES = ("decision:accept", "delegation:accepted")


@dataclass(frozen=True)
class _Topics:
    """Topic signature of a trigger or a role duty.

    ``kinds`` are MotiveKind values the topic can arouse; ``keywords`` are
    case-insensitive substrings matched against motive content. Two topics
    overlap when their kind sets or keyword sets intersect.
    """

    kinds: frozenset[str]
    keywords: frozenset[str]


def _topics(
    *,
    kinds: frozenset[str] = frozenset(),
    keywords: frozenset[str] = frozenset(),
) -> _Topics:
    return _Topics(kinds=kinds, keywords=keywords)


#: Deterministic trigger -> topic table. Every trigger point must opt in here
#: (the same discipline as derive_motives): an unknown trigger is an
#: integration gap and raises USAGE_ERROR instead of silently skipping.
_TRIGGER_ISSUES: dict[str, _Topics] = {
    "draft_generated": _topics(
        kinds=frozenset({MotiveKind.GOAL.value}),
        keywords=frozenset({"draft", "稿", "初稿", "章节"}),
    ),
    "draft_revised": _topics(
        kinds=frozenset({MotiveKind.GOAL.value}),
        keywords=frozenset({"draft", "稿", "章节", "钩子"}),
    ),
    "draft_gate_passed": _topics(
        kinds=frozenset({MotiveKind.GOAL.value}),
        keywords=frozenset({"draft", "稿", "质量", "gate"}),
    ),
    "style_set": _topics(
        kinds=frozenset({MotiveKind.IMPRESSION.value}),
        keywords=frozenset({"style", "风格", "锚点"}),
    ),
    "plot_planted": _topics(
        kinds=frozenset({MotiveKind.FORESHADOW.value}),
        keywords=frozenset({"plot", "线索", "伏笔"}),
    ),
    "talk_first_round": _topics(
        kinds=frozenset({MotiveKind.GOAL.value}),
        keywords=frozenset({"direction", "方向", "基调"}),
    ),
    "review_add": _topics(
        kinds=frozenset({MotiveKind.IMPRESSION.value, MotiveKind.PENDING_ISSUE.value}),
        keywords=frozenset({"review", "审稿", "意见", "退稿"}),
    ),
    "decision_accept": _topics(
        kinds=frozenset({MotiveKind.GOAL.value}),
        keywords=frozenset({"decision", "采纳", "认可", "拍板"}),
    ),
    "decision_reject": _topics(
        kinds=frozenset({MotiveKind.PENDING_ISSUE.value}),
        keywords=frozenset({"decision", "退稿", "拒绝", "退回"}),
    ),
    "review_conflict": _topics(
        kinds=frozenset({MotiveKind.FORESHADOW.value, MotiveKind.PENDING_ISSUE.value}),
        keywords=frozenset({"conflict", "矛盾", "冲突"}),
    ),
}


#: Deterministic role duty -> topic table. Roles are the AgentRole values; an
#: unknown role simply never covers a trigger topic (motive hits still keep
#: its candidates), matching the model's neutral fallback for unknown roles.
_ROLE_ISSUES: dict[str, _Topics] = {
    AgentRole.EDITOR_IN_CHIEF: _topics(
        kinds=frozenset({MotiveKind.GOAL.value, MotiveKind.PENDING_ISSUE.value}),
        keywords=frozenset({"direction", "方向", "基调", "主线", "拍板"}),
    ),
    AgentRole.EDITOR: _topics(
        kinds=frozenset({MotiveKind.GOAL.value, MotiveKind.PENDING_ISSUE.value}),
        keywords=frozenset({"quality", "质量", "节奏", "gate"}),
    ),
    AgentRole.WRITER: _topics(
        kinds=frozenset({MotiveKind.GOAL.value}),
        keywords=frozenset(
            {"draft", "稿", "初稿", "章节", "钩子", "review", "审稿", "意见", "退稿"}
        ),
    ),
    AgentRole.REVIEWER: _topics(
        kinds=frozenset({MotiveKind.FORESHADOW.value}),
        keywords=frozenset(
            {"consistency", "style", "一致", "矛盾", "伏笔", "线索", "风格", "锚点"}
        ),
    ),
}


def _topics_overlap(left: _Topics, right: _Topics) -> bool:
    return bool(left.kinds & right.kinds) or bool(left.keywords & right.keywords)


def _motive_hits_topic(motive: AgentMotive, topics: _Topics) -> bool:
    if motive.kind in topics.kinds:
        return True
    content = motive.content.lower()
    return any(keyword in content for keyword in topics.keywords)


def _group_motives(motives: Sequence[AgentMotive]) -> dict[str, list[AgentMotive]]:
    grouped: dict[str, list[AgentMotive]] = {}
    for motive in motives:
        grouped.setdefault(motive.agent_id, []).append(motive)
    return grouped


def _agent_has_hit(motives: Sequence[AgentMotive], topics: _Topics) -> bool:
    return any(_motive_hits_topic(motive, topics) for motive in motives)


def coarse_filter(
    trigger: str,
    candidates: Sequence[ChoiceCandidate],
    agents: Mapping[str, str],
    motives: Sequence[AgentMotive],
) -> list[ChoiceCandidate]:
    """Deterministically keep only candidates relevant to ``trigger``.

    A candidate survives when its agent's role duty overlaps the trigger's
    topic OR the agent carries a motive that matches the topic. Candidate
    order is preserved. Unknown triggers raise USAGE_ERROR so integration gaps
    are visible instead of silently silencing a partner.
    """
    topics = _TRIGGER_ISSUES.get(trigger)
    if topics is None:
        raise NovelError(ErrorCode.USAGE_ERROR, f"unknown choice trigger: {trigger}")
    motives_by_agent = _group_motives(motives)
    kept: list[ChoiceCandidate] = []
    for candidate in candidates:
        role = agents.get(candidate.agent)
        role_hit = role is not None and _topics_overlap(_ROLE_ISSUES.get(role, _topics()), topics)
        motive_hit = _agent_has_hit(motives_by_agent.get(candidate.agent, ()), topics)
        if role_hit or motive_hit:
            kept.append(candidate)
    return kept


def _relevance_for(role_hit: bool, motive_hit: bool) -> float:
    if role_hit and motive_hit:
        return RELEVANCE_ROLE_AND_MOTIVE
    if role_hit:
        return RELEVANCE_ROLE_ONLY
    if motive_hit:
        return RELEVANCE_MOTIVE_ONLY
    return RELEVANCE_UNSPECIFIED


def _motive_factor(
    agent: str,
    motives_by_agent: Mapping[str, Sequence[AgentMotive]],
    topics: _Topics | None,
) -> float:
    relevant: list[int] = []
    for motive in motives_by_agent.get(agent, ()):
        if topics is None or _motive_hits_topic(motive, topics):
            relevant.append(motive.strength)
    if not relevant:
        return 1.0
    strongest = max(max(0, min(100, strength)) for strength in relevant)
    return strongest / 100.0


def _personality_factor(params: PersonalityParams | None) -> float:
    current = params if params is not None else DEFAULT_PERSONALITY
    values = (
        max(0, min(10, current.proactivity)),
        max(0, min(10, current.stubbornness)),
        max(0, min(10, current.talkativeness)),
        max(0, min(10, current.patience)),
    )
    return sum(values) / len(values) / 10.0


def _feedback_factor(feedback: FeedbackCounts) -> float:
    factor = (1.0 + ACCEPT_BONUS * feedback.accepted) / (
        1.0 + REJECT_PENALTY * feedback.rejected
    )
    return max(FEEDBACK_FLOOR, min(1.0, factor))


def compute_weights(
    candidates: Sequence[ChoiceCandidate],
    motives: Sequence[AgentMotive],
    params: Mapping[str, PersonalityParams],
    feedback: Mapping[str, FeedbackCounts] | None = None,
    *,
    agents: Mapping[str, str] | None = None,
    trigger: str | None = None,
) -> list[float]:
    """Compute the speaking tendency for every candidate, in input order.

    tendency = relevance x motive-strength x personality x feedback.

    - relevance: role duty + motive hit 1.0, role duty only 0.8, motive hit
      only 0.6; without ``agents``/``trigger`` it is neutral 1.0.
    - motive strength: the strongest matching motive's strength / 100; a
      partner without a matching motive is neutral 1.0 (N1 single-candidate
      behaviors keep firing without motives).
    - personality: the mean of the four 0-10 params, normalized to [0, 1].
      All four params enter the selector weight (09 design); stubbornness and
      patience also gate state thresholds later (N28/N29), not here.
    - feedback: refusals lower, acceptances restore (see ``_feedback_factor``).

    The output is a comparable [0, 1] value per candidate, not normalized to
    sum to 1, so the silence threshold keeps its meaning across scenes.
    """
    topics = _TRIGGER_ISSUES.get(trigger) if trigger is not None else None
    motives_by_agent = _group_motives(motives)
    feedback = feedback if feedback is not None else {}
    weights: list[float] = []
    for candidate in candidates:
        role_hit = False
        if topics is not None and agents is not None:
            role = agents.get(candidate.agent)
            role_hit = role is not None and _topics_overlap(
                _ROLE_ISSUES.get(role, _topics()), topics
            )
        motive_hit = topics is not None and _agent_has_hit(
            motives_by_agent.get(candidate.agent, ()), topics
        )
        relevance = _relevance_for(role_hit, motive_hit)
        motive = _motive_factor(candidate.agent, motives_by_agent, topics)
        personality = _personality_factor(params.get(candidate.agent))
        history = _feedback_factor(feedback.get(candidate.agent, FeedbackCounts()))
        weights.append(relevance * motive * personality * history)
    return weights


def pick_candidate(weighted: Sequence[float], dial: float, seed: int) -> int | None:
    """Pick one candidate index by weighted random with a fixed seed.

    dial=0 always returns the highest-weight index (ties resolve to the first
    in input order). dial in (0, 1] blends the weights towards uniform, so
    low-weight candidates can be picked; dial=1 is fully uniform. A fixed seed
    reproduces the exact same pick. Returns None for an empty or all-zero
    weight list (the silence entrance handles that before this is called).
    dial outside [0, 1] raises USAGE_ERROR.
    """
    if dial < 0.0 or dial > 1.0:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"dial must be in [0, 1], got {dial}",
        )
    if not weighted:
        return None
    weights = list(weighted)
    if any(weight < 0.0 for weight in weights):
        raise NovelError(ErrorCode.USAGE_ERROR, "weights must be non-negative")
    if dial == 0.0:
        return max(range(len(weights)), key=lambda index: weights[index])
    if sum(weights) <= 0.0:
        return None
    count = len(weights)
    effective = [weight * (1.0 - dial) + dial / count for weight in weights]
    rng = Random(seed)
    return rng.choices(range(count), weights=effective, k=1)[0]


def evaluate_choice(
    trigger: str,
    candidates: Sequence[ChoiceCandidate],
    agents: Mapping[str, str],
    motives: Sequence[AgentMotive],
    params: Mapping[str, PersonalityParams],
    feedback: Mapping[str, FeedbackCounts] | None = None,
    *,
    dial: float = 0.0,
    seed: int = 42,
    min_weight: float = DEFAULT_MIN_WEIGHT,
) -> list[ChoiceCandidate]:
    """Silence entrance: run the three stages and return 0 or 1 candidates.

    Returns an empty list when the coarse filter drops everything, when the
    best weight is below ``min_weight``, or when the pick lands nowhere.
    Nothing is written to any database here; persisting the chosen behavior
    (or the silence) belongs to S4 / N28.
    """
    if not 0.0 <= min_weight <= 1.0:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"min_weight must be in [0, 1], got {min_weight}",
        )
    kept = coarse_filter(trigger, candidates, agents, motives)
    if not kept:
        return []
    weights = compute_weights(
        kept,
        motives,
        params,
        feedback,
        agents=agents,
        trigger=trigger,
    )
    if max(weights) < min_weight:
        return []
    index = pick_candidate(weights, dial, seed)
    if index is None:
        return []
    return [kept[index]]


def load_feedback_counts(db: DB, workspace_id: str) -> dict[str, FeedbackCounts]:
    """Read-only refusal / acceptance counts per agent from behavior_timeline.

    Only sources in ``REJECTED_SOURCES`` / ``ACCEPTED_SOURCES`` are counted
    (author decisions and delegation verdicts); opinions such as review:add or
    refusal:* are not. The query is a pure COUNT over the workspace timeline
    and never writes.
    """
    counts: dict[str, FeedbackCounts] = {}
    with db.workspace_session(workspace_id) as session:
        rejected_rows = (
            session.query(BehaviorTimeline.agent_id, func.count())
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.source.in_(REJECTED_SOURCES),
            )
            .group_by(BehaviorTimeline.agent_id)
            .all()
        )
        accepted_rows = (
            session.query(BehaviorTimeline.agent_id, func.count())
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.source.in_(ACCEPTED_SOURCES),
            )
            .group_by(BehaviorTimeline.agent_id)
            .all()
        )
    for agent_id, rejected in rejected_rows:
        counts[agent_id] = FeedbackCounts(rejected=int(rejected))
    for agent_id, accepted in accepted_rows:
        current = counts.get(agent_id, FeedbackCounts())
        counts[agent_id] = FeedbackCounts(
            rejected=current.rejected,
            accepted=int(accepted),
        )
    return counts
