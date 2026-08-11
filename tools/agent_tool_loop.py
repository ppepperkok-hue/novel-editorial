"""Agent tool loop: native function calling for writing agents.

First round carries the agent persona + one-line knowledge index + the
`get_knowledge` tool declaration (tool_choice omitted: DeepSeek V4 rejects
forced tool_choice). If the model emits tool_calls, local knowledge packages
are resolved and returned as `role:"tool"` messages; a second round (no tools)
produces the final answer. Without tool_calls the first round is the answer.

Usage (library):
    from tools import agent_tool_loop
    result = agent_tool_loop.run("writer", task_text, target_words=2000)

CLI:
    python tools/agent_tool_loop.py --agent writer --task "..." [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import config, db  # noqa: E402
from novel_editorial.llm_client import chat_deepseek  # noqa: E402
from novel_editorial.services import knowledge  # noqa: E402

AGENTS_DIR = config.AGENTS_DIR

GET_KNOWLEDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_knowledge",
        "description": (
            "获取与当前任务相关的写作知识包。当任务涉及开篇/黄金三章/章末钩子、"
            "节奏/爽点、人设/OOC/角色关系、伏笔埋设与回收、去AI味/文风/标点、"
            "市场热点/选题/读者心理等主题时，调用本工具获取内容后再作答。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "知识主题关键词，例如：章末钩子、节奏、OOC、伏笔、去AI味、市场热点",
                }
            },
            "required": ["topic"],
        },
    },
}

GET_NOVEL_KNOWLEDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_novel_knowledge",
        "description": (
            "获取当前这部小说的设定知识库：角色当前状态、世界观规则、物品/金手指、"
            "势力、地点、力量体系、已发生的剧情事实与时间线。写正文、设计细纲、"
            "检查设定一致性时，不确定的设定必须调用本工具确认，禁止凭记忆编造。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "查询关键词，例如：角色名、物品名、境界、地点、势力、事件",
                }
            },
            "required": ["topic"],
        },
    },
}


def _parse_asset(path):
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    meta = {}
    if len(parts) >= 3:
        for line in parts[1].strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    body = parts[2].strip() if len(parts) >= 3 else text.strip()
    return meta, body


def build_system(agent, target_words=None):
    path = _resolve_agent_file(agent)
    if path is None:
        raise ValueError(f"unknown agent: {agent}")
    meta, body = _parse_asset(path)
    body = body.replace("{TARGET_WORDS}", str(target_words or 2000))
    index = knowledge.build_knowledge_index(agent)
    tool_rule = (
        "\n\n[可用工具]\n"
        "1. get_knowledge：通用写作知识包。任务涉及开篇/钩子、节奏/爽点、人设/OOC、"
        "伏笔、去AI味、市场热点/选题等主题时调用；知识包内容是硬规则。\n"
        "2. get_novel_knowledge：当前这部小说的设定知识库（角色状态/世界观/物品/势力/"
        "地点/力量体系/剧情事实/时间线）。写正文或设计细纲时，涉及本书已有设定必须调用"
        "确认，禁止凭记忆编造或遗忘设定。\n"
        "根据任务需要自主选择调用，可多次调用不同主题；调用后基于返回内容输出最终结果。"
    )
    if index:
        body += tool_rule + "\n\n" + index
    return meta, body


def _resolve_agent_file(agent):
    """Resolve an agent reference to a prompt file.

    Accepts three shapes:
    1. the canonical file stem (e.g. "writer")
    2. the workflow node name from render_workflow.AGENT_FILES (e.g. "写手A")
    3. the display name from services.agents.AGENT_DISPLAY (e.g. "叙述写手")
    """
    direct = AGENTS_DIR / f"{agent}.md"
    if direct.exists():
        return direct
    from tools.render_workflow import AGENT_FILES  # noqa: PLC0415

    filename = AGENT_FILES.get(agent)
    if filename:
        candidate = AGENTS_DIR / filename
        if candidate.exists():
            return candidate
    from novel_editorial.services.agents import AGENT_DISPLAY  # noqa: PLC0415

    for filename, display in AGENT_DISPLAY.items():
        if display == agent:
            candidate = AGENTS_DIR / filename
            if candidate.exists():
                return candidate
    return None




def _unwrap_text(text):
    """Unwrap `{\"text\": ...}` JSON envelopes into plain prose."""
    if not isinstance(text, str):
        return text
    stripped = text.strip()
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return text
    try:
        obj = json.loads(stripped)
    except ValueError:
        return text
    if isinstance(obj, dict) and isinstance(obj.get("text"), str):
        return obj["text"]
    return text


_ACTIVITY_TYPES = {
    "planner": "plan",
    "guard": "guard",
    "writer": "chapter",
    "editor": "chapter",
    "reviewer": "review",
    "reader": "review",
    "memory": "summary",
    "work_meta": "meta",
    "eic": "review",
    "ending_judge": "ending",
    "knowledge_keeper": "knowledge",
}


def _log_activity(agent, novel_id, activity_type, title, detail, db_path):
    """Best-effort activity trace; never fail the agent call over logging."""
    try:
        from novel_editorial.services import activity  # noqa: PLC0415

        conn = db.connect(db_path or config.DB_PATH)
        try:
            activity.log_activity(
                conn, agent, novel_id or 0, activity_type, title, detail
            )
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        pass


def run(agent, task_text, temperature=None, max_tokens=1600, target_words=None,
        novel_id=None, db_path=None, model=None):
    stem = _resolve_agent_file(agent)
    canonical = stem.stem if stem is not None else agent
    meta, system = build_system(agent, target_words)
    if db_path:
        try:
            from tools import agent_context  # noqa: PLC0415

            conn = db.connect(db_path)
            try:
                snapshot = agent_context.build_context_snapshot(
                    conn, canonical, novel_id or 0
                )
            finally:
                conn.close()
            if snapshot:
                system += "\n\n" + snapshot
        except Exception:  # noqa: BLE001 - context injection must never break the call
            pass
    model = model or meta.get("model") or "deepseek-v4-flash"
    temp = float(temperature) if temperature is not None else float(meta.get("temperature") or 0.5)
    used_knowledge = []
    degraded = False
    activity_type = _ACTIVITY_TYPES.get(canonical, "agent")
    prose_agent = activity_type == "chapter"  # writer/editor output prose, not JSON

    def _final(text, usage=None):
        text = _unwrap_text(text)
        _log_activity(
            canonical,
            novel_id,
            activity_type,
            "完成智能体任务",
            {
                "agent_key": canonical,
                "task": str(task_text or "")[:400],
                "used_knowledge": used_knowledge,
                "degraded": degraded,
                "output": text[:300],
            },
            db_path,
        )
        return {
            "ok": True,
            "text": text,
            "model": model,
            "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0},
            "used_knowledge": used_knowledge,
            "attempts": 2 if used_knowledge else 1,
            "degraded": degraded,
        }

    first = None
    tool_err = None
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0}

    def _accum(cand):
        u = cand.get("usage") or {}
        total_usage["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
        total_usage["completion_tokens"] += int(u.get("completion_tokens") or 0)

    for _attempt in range(3):
        try:
            cand = chat_deepseek(
                model, system, task_text, temperature=temp,
                max_tokens=max_tokens, tools=[GET_KNOWLEDGE_TOOL, GET_NOVEL_KNOWLEDGE_TOOL],
            )
            if (cand.get("text") or "").strip() or cand.get("tool_calls"):
                first = cand
                _accum(cand)
                break
        except Exception as exc:  # noqa: BLE001 - retry, then fall back plain
            tool_err = exc
    if first is None:
        degraded = True
        plain = None
        plain_err = None
        for _attempt in range(3):
            try:
                cand = chat_deepseek(
                    model, system, task_text, temperature=temp, max_tokens=max_tokens,
                    json_mode=False if prose_agent else None,
                )
                if (cand.get("text") or "").strip():
                    plain = cand
                    _accum(cand)
                    break
            except Exception as exc2:  # noqa: BLE001
                plain_err = exc2
        if plain is None:
            _log_activity(
                canonical,
                novel_id,
                "agent",
                "智能体调用失败",
                {
                    "agent_key": canonical,
                    "task": str(task_text or "")[:400],
                    "error": (
                        "tool loop failed "
                        f"(tools={str(tool_err)[:120]}, plain={str(plain_err)[:120]})"
                    ),
                },
                db_path,
            )
            return {
                "ok": False,
                "error": (
                    "tool loop failed "
                    f"(tools={str(tool_err)[:120]}, plain={str(plain_err)[:120]})"
                ),
                "model": model,
                "usage": total_usage,
                "degraded": True,
            }
        return _final(plain["text"], plain.get("usage") or {})

    tool_calls = first.get("tool_calls") or []
    if not tool_calls:
        return _final(first["text"], first.get("usage") or {})

    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": task_text},
        {
            "role": "assistant",
            "content": first.get("text") or "",
            "tool_calls": tool_calls,
        },
    ]
    for tc in tool_calls:
        fn = tc.get("function") or {}
        name = fn.get("name") or ""
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        topic = str(args.get("topic") or "")
        if name == "get_knowledge":
            hits = knowledge.resolve_knowledge(agent, topic)
            used_knowledge.append({"topic": topic, "files": [h["file"] for h in hits]})
            _log_activity(
                canonical,
                novel_id,
                "knowledge_lookup",
                f"检索知识包：{topic}",
                {
                    "tool": name,
                    "topic": topic,
                    "files": [h["file"] for h in hits],
                    "hits": len(hits),
                },
                db_path,
            )
            content = "\n\n".join(
                f"【{h['title']}】\n{h['content']}" for h in hits
            ) or f"未找到与「{topic}」匹配的知识包，请直接作答。"
        elif name == "get_novel_knowledge":
            from tools import novel_knowledge  # noqa: PLC0415

            conn = db.connect(db_path or config.DB_PATH)
            try:
                hits = novel_knowledge.resolve(conn, novel_id or 0, topic)
            finally:
                conn.close()
            used_knowledge.append(
                {"topic": topic, "novel_id": novel_id or 0, "hits": len(hits)}
            )
            _log_activity(
                canonical,
                novel_id,
                "knowledge_lookup",
                f"检索设定库：{topic}",
                {
                    "tool": name,
                    "topic": topic,
                    "novel_id": novel_id or 0,
                    "hits": len(hits),
                },
                db_path,
            )
            content = "\n\n".join(
                f"【{h['category']}·{h['entity']} v{h['version']}】\n{h['content']}"
                for h in hits
            ) or f"知识库中没有与「{topic}」相关的设定，请基于已有材料作答并不要编造新设定。"
        else:
            content = "未知工具"
        msgs.append(
            {
                "role": "tool",
                "tool_call_id": tc.get("id") or "",
                "content": content,
            }
        )

    final = None
    final_err = None
    for _attempt in range(3):
        try:
            cand = chat_deepseek(
                model, None, None, temperature=temp, max_tokens=max_tokens,
                messages=msgs, json_mode=False if prose_agent else None,
            )
            if (cand.get("text") or "").strip():
                final = cand
                _accum(cand)
                break
        except Exception as exc:  # noqa: BLE001 - retry, then degrade
            final_err = exc
    if final is None:
        degraded = True
        _log_activity(
            canonical,
            novel_id,
            "agent",
            "智能体调用失败",
            {
                "agent_key": canonical,
                "task": str(task_text or "")[:400],
                "used_knowledge": used_knowledge,
                "error": f"final round empty/error: {str(final_err)[:120]}",
            },
            db_path,
        )
        return {
            "ok": False,
            "error": (
                "final round empty/error: "
                f"{str(final_err)[:120]}"
            ),
            "model": model,
            "usage": total_usage,
            "used_knowledge": used_knowledge,
            "attempts": 2,
            "degraded": True,
        }

    first_usage = first.get("usage") or {}
    final_usage = final.get("usage") or {}
    usage = {
        "prompt_tokens": int(first_usage.get("prompt_tokens") or 0)
        + int(final_usage.get("prompt_tokens") or 0),
        "completion_tokens": int(first_usage.get("completion_tokens") or 0)
        + int(final_usage.get("completion_tokens") or 0),
    }
    result = _final(final["text"], usage)
    if final.get("tool_calls"):
        # No tools are declared in the final round; a stray tool_calls is
        # semantically ignored under the two-round policy.
        result["warning"] = (
            f"final round returned {len(final.get('tool_calls') or [])} "
            "tool_calls; ignored"
        )
    return result


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Agent 工具循环（知识库按需调用）")
    ap.add_argument("--agent", required=True)
    ap.add_argument("--task", default="")
    ap.add_argument("--task-file", default="")
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--max-tokens", type=int, default=1600)
    ap.add_argument("--target-words", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    task = args.task
    if args.task_file:
        task = Path(args.task_file).read_text(encoding="utf-8")
    if args.dry_run:
        meta, system = build_system(args.agent, args.target_words)
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "agent": args.agent,
                    "model": meta.get("model"),
                    "temperature": meta.get("temperature"),
                    "system_len": len(system),
                    "has_tool_rule": "get_knowledge" in system,
                },
                ensure_ascii=False,
            )
        )
        return
    result = run(
        args.agent, task, temperature=args.temperature,
        max_tokens=args.max_tokens, target_words=args.target_words,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
