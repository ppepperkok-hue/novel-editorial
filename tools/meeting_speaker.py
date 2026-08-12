"""Speaker candidacy for free meetings.

Mandatory targets come from @mentions; everyone else is ranked by interest
keyword overlap with the event and recent messages. Busy agents and agents
still inside the per-speaker cooldown are excluded. The limit caps how many
non-mandatory agents may be asked to speak per event.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from tools import meeting_mentions
from tools.meeting_executor import AGENT_PERSONA, agent_label

INTEREST_KEYWORDS = {
    "planner": ["选题", "方向", "大纲", "剧情", "节奏", "卷"],
    "guard": ["设定", "吃书", "伏笔", "矛盾", "世界观", "规则", "OOC"],
    "writer": ["正文", "写法", "细节", "场景", "章节", "文笔"],
    "editor": ["文风", "语感", "AI味", "标点", "句子", "润色"],
    "reviewer": ["逻辑", "漏洞", "矛盾", "底线", "审稿", "严谨"],
    "reader": ["读者", "追读", "钩子", "情绪", "爽点", "体验"],
    "eic": ["决策", "拍板", "仲裁", "结论", "定夺", "优先级"],
    "memory": ["记忆", "摘要", "台账", "留痕", "记录"],
    "work_meta": ["书名", "简介", "标签", "主角", "卷目标"],
    "ending_judge": ["完结", "收尾", "回收", "终局"],
    "knowledge_keeper": ["知识", "经验", "热点", "草案", "维护"],
}


def _event_text(event):
    return str(event.get("content") or "")


def _recent_text(conn, session_id, limit=5):
    rows = conn.execute(
        "SELECT body FROM meeting_messages WHERE session_id=? AND status='active' "
        "ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return " ".join(str(r["body"] or "") for r in reversed(rows))


def _score(agent, text):
    keywords = INTEREST_KEYWORDS.get(agent, [])
    if not keywords or not text:
        return 0
    return sum(1 for kw in keywords if kw in text)


def _last_speak_at(conn, session_id, agent):
    row = conn.execute(
        "SELECT created_at FROM meeting_messages WHERE session_id=? "
        "AND from_agent=? AND kind='speech' ORDER BY id DESC LIMIT 1",
        (session_id, agent),
    ).fetchone()
    if not row or not row["created_at"]:
        return None
    try:
        return datetime.strptime(str(row["created_at"]), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def candidate_speakers(conn, session, event, agent_pool, busy=(), k=2, cooldown_s=60):
    """返回候选发言名单：[{agent, reason, score, mandatory}]。
    必答（被 @）在前；其余按兴趣词命中数取 top k。"""
    session_id = int(session["id"])
    agent_pool = [str(a).replace(".md", "") for a in (agent_pool or [])]
    busy = {str(a).replace(".md", "") for a in (busy or [])}
    content = _event_text(event)
    sender = str(event.get("from_agent") or "").replace(".md", "")

    # 必答：@ 命中（排除发送者本人）。
    persona_names = [agent_label(a) for a in agent_pool]
    mentioned = meeting_mentions.resolve_mention_targets(content, persona_names, agent_label(sender))
    mentioned_agents = [
        a for a in agent_pool if agent_label(a) in mentioned
    ]

    candidates = []
    seen = set()
    for agent in mentioned_agents:
        if agent in busy or agent == sender:
            continue
        candidates.append(
            {"agent": agent, "reason": "mentioned", "score": 99, "mandatory": True}
        )
        seen.add(agent)

    text = f"{content} {_event_text(event)} {_recent_text(conn, session_id)}"
    scored = []
    for agent in agent_pool:
        if agent in seen or agent in busy or agent == sender:
            continue
        last = _last_speak_at(conn, session_id, agent)
        if last is not None and datetime.now() - last < timedelta(seconds=cooldown_s):
            continue
        score = _score(agent, text)
        if score > 0:
            scored.append({"agent": agent, "reason": "interest", "score": score, "mandatory": False})
    scored.sort(key=lambda item: item["score"], reverse=True)
    candidates.extend(scored[: max(0, k)])
    return candidates
