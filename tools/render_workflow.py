"""Render n8n workflow JSON from the agent prompt assets in prompts/agents/.

This is the evolution loop for the pipeline: edit a prompt file (or its
frontmatter model/temperature), run this script, validate, push to n8n.

PROXY_MODE=True: agent nodes call the local /api/agent/run endpoint. The
system prompt is assembled at runtime by tools/agent_tool_loop.py (persona +
knowledge index + get_knowledge tool), so n8n only carries agent name, model,
temperature, the dynamic target_words expression and the user task.

    python tools/render_workflow.py            # updates n8n/novel_workflow.json
    node tools/validate_workflow_deep.mjs
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / "n8n" / "novel_workflow.json"
AGENTS = ROOT / "prompts" / "agents"
PROXY_BASE = "http://127.0.0.1:8000/api/agent/run"
PROXY_MODE = True

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
AGENT_MARK = "{agent:'"


def extract_user_expr(body):
    """Extract the n8n user-content expression(s) from a DeepSeek jsonBody."""
    if "task:" in body and "{role:'system'" not in body:
        # already in proxy mode: task:<expr>}) }}
        t0 = body.find("task:")
        t1 = body.find("}) }}", t0)
        if t0 >= 0 and t1 > t0:
            return body[t0 + len("task:") : t1]
    s0 = body.find(START_MARK)
    s1 = body.find(END_MARK, s0)
    if s0 < 0 or s1 < 0:
        return None
    # keep the leading quote of the user expression: content:'...'+expr...
    c0 = body.find("content:", s1)
    c1 = body.rfind("}]})", c0)
    if c0 < 0 or c1 < 0:
        return None
    return body[c0 + len("content:") : c1]


def extract_target_words_expr(system):
    """Extract the n8n target_words expression from a system string."""
    idx = system.find(TARGET_WORDS_EXPR)
    if idx < 0:
        return None
    start = system.find("((", idx - 1)
    end = system.find(")", idx) + 1
    if start < 0 or end <= 0:
        return None
    expr = system[start:end]
    # close the extra parens of `(($expr||2000))`
    if not expr.endswith(")||2000))"):
        return None
    return expr


def build_proxy_body(agent, meta, system_has_target_words, user_expr):
    model = meta.get("model", "")
    temperature = meta.get("temperature", "")
    max_tokens = meta.get("max_tokens", "")
    fields = [f"agent:'{agent}'"]
    if model:
        fields.append(f"model:'{model}'")
    if temperature:
        fields.append(f"temperature:{temperature}")
    if max_tokens:
        fields.append(f"max_tokens:{max_tokens}")
    if system_has_target_words:
        fields.append("target_words:(($('解析本地资料').first().json.target_words)||2000)")
    fields.append(f"task:{user_expr}")
    return "={{ JSON.stringify({" + ", ".join(fields) + "}) }}"


def parse_asset(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise SystemExit(f"bad frontmatter in {path}")
    parts = text.split("---", 2)
    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, parts[2].strip()


def esc_system(text):
    """Escape system text for a single-quoted n8n expression string, keeping
    the TARGET_WORDS placeholder expansion unescaped."""
    chunks = text.split(TARGET_WORDS_PLACEHOLDER)
    escaped = [c.replace("\\", "\\\\").replace("'", "\\'") for c in chunks]
    return TARGET_WORDS_EXPR.join(escaped)


def main():
    wf = json.loads(WF.read_text(encoding="utf-8"))
    nodes = {n["name"]: n for n in wf["nodes"]}
    changed = []
    for node_name, filename in AGENT_FILES.items():
        asset = AGENTS / filename
        if not asset.exists():
            continue
        meta, system = parse_asset(asset)
        node = nodes.get(node_name)
        if node is None:
            continue
        body = node["parameters"]["jsonBody"]
        if PROXY_MODE:
            user_expr = extract_user_expr(body)
            if user_expr is None:
                continue
            new_body = build_proxy_body(
                node_name, meta, "{TARGET_WORDS}" in system, user_expr
            )
            node["parameters"]["url"] = PROXY_BASE
            node["parameters"]["headerParameters"] = {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                    {
                        "name": "Authorization",
                        "value": "={{ $env.PANEL_TOKEN ? 'Bearer ' + $env.PANEL_TOKEN : 'none' }}",
                    },
                ]
            }
            if new_body != body:
                node["parameters"]["jsonBody"] = new_body
                changed.append(node_name)
            continue
        model = meta.get("model", "")
        temperature = meta.get("temperature", "")
        sm = body.find("model:'")
        tm = body.find("temperature:", sm)
        s0 = body.find(START_MARK)
        s1 = body.find(END_MARK, s0)
        if sm < 0 or tm < 0 or s0 < 0 or s1 < 0:
            continue
        m0 = sm + len("model:'")
        m1 = body.find("'", m0)
        t0 = tm + len("temperature:")
        t1 = body.find(",", t0)
        new_body = (
            body[:m0]
            + model
            + body[m1:t0]
            + temperature
            + body[t1:s0 + len(START_MARK)]
            + esc_system(system)
            + body[s1:]
        )
        if new_body != body:
            node["parameters"]["jsonBody"] = new_body
            changed.append(node_name)
    WF.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print("rendered; changed nodes:", changed or "none")


if __name__ == "__main__":
    main()
