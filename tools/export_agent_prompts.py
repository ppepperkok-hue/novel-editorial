"""Export LLM agent system prompts from the n8n workflow into prompts/agents/.

Each agent becomes a markdown file with frontmatter (model, temperature) and
the system prompt as body. Edit those files, then run render_workflow.py.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / "n8n" / "novel_workflow.json"
OUT = ROOT / "prompts" / "agents"

AGENT_FILES = {
    "Planner出大纲": "planner.md",
    "守护细纲": "guard.md",
    "生成作品资料": "work_meta.md",
    "写手A": "writer.md",
    "写手B": "writer.md",
    "润色A": "editor.md",
    "润色B": "editor.md",
    "审稿A": "reviewer.md",
    "审稿B": "reviewer.md",
    "读者审稿A": "reader.md",
    "读者审稿B": "reader.md",
    "主编终审A": "eic.md",
    "主编终审B": "eic.md",
    "提炼剧情A": "memory.md",
    "提炼剧情B": "memory.md",
}

TARGET_WORDS_EXPR = "'+(($('解析本地资料').first().json.target_words)||2000)+'"
TARGET_WORDS_PLACEHOLDER = "{TARGET_WORDS}"

START_MARK = "{role:'system',content:'"
END_MARK = "'},{role:'user'"


def _find_system_end(body, s0):
    """Locate the system/user boundary without truncating inside the prompt.

    END_MARK appearing inside the system text must not count; only accept a
    marker directly followed by the user-message content field.
    """
    pos = s0
    while True:
        s1 = body.find(END_MARK, pos)
        if s1 < 0:
            return -1
        if body[s1 + len(END_MARK) :].startswith(",content:"):
            return s1
        pos = s1 + 1


def main():
    wf = json.loads(WF.read_text(encoding="utf-8"))
    nodes = {n["name"]: n for n in wf["nodes"]}
    proxy = any(
        "{agent:'" in str(n.get("parameters", {}).get("jsonBody") or "")
        for n in wf["nodes"]
    )
    if proxy:
        print(
            "PROXY_MODE=True：提示词资产直接维护在 prompts/agents/*.md，"
            "无需从工作流导出（工作流只携带 agent 名/模型/温度/task）。"
        )
        return
    OUT.mkdir(parents=True, exist_ok=True)
    written = set()
    for node_name, filename in AGENT_FILES.items():
        node = nodes.get(node_name)
        if node is None:
            continue
        body = node["parameters"]["jsonBody"]
        sm = body.find("model:'")
        if sm < 0:
            print("skip (no model field):", node_name)
            continue
        model_end = body.find("'", sm + len("model:'"))
        if model_end < 0:
            print("skip (unterminated model field):", node_name)
            continue
        model = body[sm + len("model:'") : model_end]
        tm = body.find("temperature:", sm)
        if tm < 0:
            print("skip (no temperature field):", node_name)
            continue
        temp_end = body.find(",", tm)
        if temp_end < 0:
            temp_end = len(body)
        temperature = body[tm + len("temperature:") : temp_end]
        mt = body.find("max_tokens:", sm)
        if mt >= 0:
            mt_end = body.find(",", mt)
            if mt_end < 0:
                mt_end = len(body)
            max_tokens = body[mt + len("max_tokens:") : mt_end]
        else:
            max_tokens = ""
        s0 = body.find(START_MARK)
        s1 = _find_system_end(body, s0)
        if s0 < 0 or s1 < 0:
            print("skip (no system match):", node_name)
            continue
        system = body[s0 + len(START_MARK) : s1]
        system = system.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
        system = system.replace(TARGET_WORDS_EXPR, TARGET_WORDS_PLACEHOLDER)
        content = (
            f"---\nmodel: {model}\ntemperature: {temperature}\n"
            + (f"max_tokens: {max_tokens}\n" if max_tokens else "")
            + f"---\n\n{system}\n"
        )
        (OUT / filename).write_text(content, encoding="utf-8")
        written.add(filename)
    print("exported:", sorted(written))


if __name__ == "__main__":
    main()
