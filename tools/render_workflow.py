"""Render n8n workflow JSON from the agent prompt assets in prompts/agents/.

This is the evolution loop for the pipeline: edit a prompt file (or its
frontmatter model/temperature), run this script, validate, push to n8n.

    python tools/render_workflow.py            # updates n8n/novel_workflow.json
    node tools/archive/validate_workflow_deep.mjs
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / "n8n" / "novel_workflow.json"
AGENTS = ROOT / "prompts" / "agents"

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
        model = meta.get("model", "")
        temperature = meta.get("temperature", "")
        node = nodes.get(node_name)
        if node is None:
            continue
        body = node["parameters"]["jsonBody"]
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
