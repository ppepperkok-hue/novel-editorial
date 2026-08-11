"""Agent asset management: list, save, validate, deploy."""

import json
import subprocess
import sys

from novel_editorial import config
from novel_editorial.services import audit
from tools import render_workflow

AGENT_DISPLAY = {
    "planner.md": "策划官",
    "guard.md": "世界观守护",
    "writer.md": "叙事写手",
    "editor.md": "文字编辑",
    "reviewer.md": "逻辑审稿",
    "reader.md": "读者体验审稿",
    "eic.md": "主编终审",
    "memory.md": "记忆官",
    "work_meta.md": "作品资料",
    "ending_judge.md": "完结评估",
    "knowledge_keeper.md": "知识管家",
}
AGENT_DESC = {
    "planner.md": "生成/增量更新故事圣经与两章细纲",
    "guard.md": "动笔前拦截 OOC/吃书/伏笔矛盾，输出约束与角色言行要点",
    "writer.md": "按细纲+角色卡+守护约束写正文（A/B 共用）",
    "editor.md": "去 AI 味、翻译腔、标点、节奏收紧（A/B 共用）",
    "reviewer.md": "六类底线问题 + 风格检查（A/B 共用）",
    "reader.md": "追读欲/钩子/情绪满足评分（A/B 共用）",
    "eic.md": "仲裁逻辑审稿与读者审稿，输出 verdict 与 must_fix（A/B 共用）",
    "memory.md": "提取摘要、角色状态、事件、伏笔台账（A/B 共用）",
    "work_meta.md": "书名/简介/标签/主角/卷目标",
    "ending_judge.md": "完结评估：剧情进度、伏笔回收、收尾建议",
    "knowledge_keeper.md": "知识库策展人：定时维护知识包、整合经验卡、审查热点",
}


def _extract_node_system(body):
    start = body.find("{role:'system',content:'")
    end = body.find("'},{role:'user'", start)
    if start < 0 or end < 0:
        return None
    return body[start + len("{role:'system',content:'") : end]


def _agent_files():
    if not config.AGENTS_DIR.exists():
        return []
    return sorted(p.name for p in config.AGENTS_DIR.glob("*.md"))


def agents_list():
    wf = json.loads(config.WORKFLOW_JSON.read_text(encoding="utf-8"))
    nodes = {n["name"]: n for n in wf["nodes"]}
    agents = []
    for f in _agent_files():
        meta, prompt = render_workflow.parse_asset(config.AGENTS_DIR / f)
        mapped = [name for name, fn in render_workflow.AGENT_FILES.items() if fn == f]
        synced = not mapped  # agents without workflow nodes need no sync
        for name in mapped:
            node = nodes.get(name)
            if node is None:
                synced = False
                continue
            body = node["parameters"]["jsonBody"]
            if f"agent:'{name}'" not in body:
                synced = False
                continue
            if f"model:'{meta.get('model', '')}'" not in body:
                synced = False
                continue
            if f"temperature:{meta.get('temperature', '')}" not in body:
                synced = False
        agents.append(
            {
                "file": f,
                "name": AGENT_DISPLAY.get(f, f),
                "description": AGENT_DESC.get(f, ""),
                "model": meta.get("model", ""),
                "temperature": meta.get("temperature", ""),
                "prompt": prompt,
                "nodes": mapped,
                "synced": synced,
            }
        )
    return agents


def agent_save(payload, conn=None):
    f = str(payload.get("file") or "")
    path = (config.AGENTS_DIR / f).resolve()
    root = config.AGENTS_DIR.resolve()
    if path.suffix != ".md" or (path != root and root not in path.parents):
        return {"ok": False, "error": "invalid agent file path"}
    if not path.exists():
        return {"ok": False, "error": "unknown agent file"}
    model = str(payload.get("model") or "").strip()
    try:
        temperature = float(payload.get("temperature"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "temperature must be a number"}
    if not (0 <= temperature <= 2):
        return {"ok": False, "error": "temperature must be 0-2"}
    prompt = str(payload.get("prompt") or "").strip()
    if len(prompt) < 20:
        return {"ok": False, "error": "prompt too short"}
    old_head = path.read_text(encoding="utf-8").split("---", 2)
    extra = ""
    if len(old_head) >= 3:
        for line in old_head[1].strip().splitlines():
            if ":" in line and not line.strip().startswith(("model:", "temperature:")):
                extra += line.strip() + "\n"
    path.write_text(
        f"---\nmodel: {model}\ntemperature: {temperature}\n{extra}---\n\n{prompt}\n",
        encoding="utf-8",
    )
    try:
        rendered = subprocess.run(
            [sys.executable, str(config.ROOT / "tools" / "render_workflow.py")],
            cwd=config.ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        validated = subprocess.run(
            ["node", str(config.VALIDATE_JS)],
            cwd=config.ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except OSError as e:
        return {"ok": False, "error": f"render/validate failed: {e}"}
    result = {
        "ok": True,
        "render": (rendered.stdout or rendered.stderr).strip()[-300:],
        "validation": validated.returncode == 0,
        "validation_output": (validated.stdout or validated.stderr).strip()[-300:],
    }
    if conn is not None:
        audit.log(
            conn,
            "agent",
            "save",
            target_type="agent",
            target_id=f,
            detail={"model": model, "temperature": temperature, "validation": result["validation"]},
        )
    return result


def agent_deploy(conn=None):
    from novel_editorial.services.control import deploy_workflow  # noqa: PLC0415

    result = deploy_workflow()
    if conn is not None:
        audit.log(conn, "agent", "deploy", detail={"nodes": result.get("nodes"), "ok": result.get("ok")})
    return result
