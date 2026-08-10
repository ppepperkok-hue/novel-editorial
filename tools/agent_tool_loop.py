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

from novel_pipeline import config, db  # noqa: E402
from novel_pipeline.llm_client import chat_deepseek  # noqa: E402
from novel_pipeline.services import knowledge  # noqa: E402

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
    path = AGENTS_DIR / f"{agent}.md"
    if not path.exists():
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


def run(agent, task_text, temperature=None, max_tokens=1600, target_words=None, novel_id=None):
    meta, system = build_system(agent, target_words)
    model = meta.get("model") or "deepseek-v4-flash"
    temp = float(temperature) if temperature is not None else float(meta.get("temperature") or 0.5)
    used_knowledge = []
    degraded = False

    def _final(text):
        return {
            "ok": True,
            "text": text,
            "model": model,
            "used_knowledge": used_knowledge,
            "attempts": 2 if used_knowledge else 1,
            "degraded": degraded,
        }

    try:
        first = chat_deepseek(
            model, system, task_text, temperature=temp,
            max_tokens=max_tokens, tools=[GET_KNOWLEDGE_TOOL, GET_NOVEL_KNOWLEDGE_TOOL],
        )
    except Exception as exc:  # noqa: BLE001 - fall back to plain single round
        degraded = True
        try:
            first = chat_deepseek(
                model, system, task_text, temperature=temp, max_tokens=max_tokens
            )
        except Exception as exc2:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"tool loop failed (tools={str(exc)[:120]}, plain={str(exc2)[:120]})",
                "degraded": True,
            }
        return _final(first["text"])

    tool_calls = first.get("tool_calls") or []
    if not tool_calls:
        return _final(first["text"])

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
            content = "\n\n".join(
                f"【{h['title']}】\n{h['content']}" for h in hits
            ) or f"未找到与「{topic}」匹配的知识包，请直接作答。"
        elif name == "get_novel_knowledge":
            from tools import novel_knowledge  # noqa: PLC0415

            conn = db.connect(config.DB_PATH)
            try:
                hits = novel_knowledge.resolve(conn, novel_id or 0, topic)
            finally:
                conn.close()
            used_knowledge.append(
                {"topic": topic, "novel_id": novel_id or 0, "hits": len(hits)}
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

    final = chat_deepseek(
        model, None, None, temperature=temp, max_tokens=max_tokens, messages=msgs
    )
    return _final(final["text"])


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
