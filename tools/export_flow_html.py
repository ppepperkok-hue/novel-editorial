"""Export a self-contained HTML report of the daily pipeline chain.

The report embeds the flow topology + latest run state as inline JSON and
renders it with plain DOM/SVG (no CDN, no external scripts), so it can be
opened offline or shared for manual review.

Usage:
    python tools/export_flow_html.py [--db demo.db] [--out exports/flow-report.html]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import db  # noqa: E402

GROUP_X = {
    "trigger": 0,
    "preflight": 200,
    "dispatch": 400,
    "meta": 600,
    "plan": 800,
    "track_a": 1000,
    "track_b": 1200,
    "publish": 1400,
    "wrapup": 1600,
}

GROUP_LABEL = {
    "trigger": "触发",
    "preflight": "预检",
    "dispatch": "分派",
    "meta": "作品资料",
    "plan": "大纲与守护",
    "track_a": "A 轨写作",
    "track_b": "B 轨写作",
    "publish": "发布链",
    "wrapup": "收尾",
}

EDGE_COLOR = {
    "ok": "#22c55e",
    "warn": "#f59e0b",
    "bad": "#ef4444",
    "run": "#3b82f6",
    "idle": "#64748b",
}


def render_html(conn):
    """Return the full standalone HTML document as a string."""
    from tools import flow_graph  # noqa: PLC0415

    flow = flow_graph.build_flow(conn)
    payload = json.dumps(flow, ensure_ascii=False).replace("</", "<\\/")
    last = flow.get("last_run") or {}
    status = last.get("status") or "idle"
    status_text = {
        "completed": "上次成功",
        "success": "上次成功",
        "partial": "上次部分成功",
        "failed": "上次失败",
        "error": "上次失败",
        "running": "运行中",
    }.get(status, "待命（暂无运行）")
    summary = (
        f"{last.get('run_id') or '—'} · 发布 {last.get('published') or 0} 章 · "
        f"{last.get('started_at') or '—'} → {last.get('finished_at') or '—'}"
    )
    error = last.get("error") or ""
    groups = "".join(
        f'<span class="chip">{GROUP_LABEL[g]}</span>' for g in GROUP_X
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>日更链路报告 · {now}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; background: #141414; color: #e5e7eb;
         font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }}
  header {{ padding: 14px 20px; border-bottom: 1px solid #2b2b2b;
            display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
  h1 {{ font-size: 16px; margin: 0; }}
  .chip {{ background: #1f1f1f; border: 1px solid #3a3a3a; border-radius: 999px;
          padding: 2px 10px; font-size: 12px; color: #9ca3af; }}
  .status {{ font-weight: 600; }}
  .status.ok {{ color: #22c55e; }} .status.warn {{ color: #f59e0b; }}
  .status.bad {{ color: #ef4444; }} .status.run {{ color: #3b82f6; }}
  .status.idle {{ color: #9ca3af; }}
  .muted {{ color: #9ca3af; font-size: 12px; }}
  .err {{ color: #f87171; font-size: 12px; max-width: 520px; overflow: hidden;
         text-overflow: ellipsis; white-space: nowrap; }}
  #wrap {{ position: relative; overflow: auto; height: calc(100vh - 60px); }}
  #canvas {{ position: relative; width: 1840px; height: 900px; }}
  .node {{ position: absolute; width: 160px; box-sizing: border-box;
          border: 1px solid #3a3a3a; border-radius: 10px; background: #1f1f1f;
          padding: 9px 10px; font-size: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.3); }}
  .node.ok {{ border-color: rgba(34,197,94,.65); }}
  .node.warn {{ border-color: rgba(245,158,11,.7); }}
  .node.bad {{ border-color: rgba(239,68,68,.75); }}
  .node.run {{ border-color: rgba(59,130,246,.9); animation: pulse 1.6s infinite; }}
  .node.failed {{ border-width: 2px; border-color: #ef4444;
                 background: rgba(239,68,68,.14); }}
  @keyframes pulse {{ 0%,100% {{ box-shadow: 0 0 0 0 rgba(59,130,246,.45); }}
                      50% {{ box-shadow: 0 0 0 8px rgba(59,130,246,0); }} }}
</style>
</head>
<body>
<header>
  <h1>日更链路报告</h1>
  <span class="status {status}">{status_text}</span>
  <span class="muted">{summary}</span>
  {f'<span class="err">{error}</span>' if error else ""}
  <span class="muted" style="margin-left:auto">生成于 {now}</span>
</header>
<div id="wrap"><div id="canvas"></div></div>
<script id="flow-data" type="application/json">{payload}</script>
<script>
const FLOW = JSON.parse(document.getElementById("flow-data").textContent);
const GROUP_X = {json.dumps(GROUP_X)};
const GROUP_LABEL = {json.dumps(GROUP_LABEL)};
const EDGE = {json.dumps(EDGE_COLOR)};
const STATUS = FLOW.last_run && FLOW.last_run.status || "idle";
const FAILED = new Set(FLOW.failed_ids || []);
function layout() {{
  const byGroup = {{}};
  FLOW.nodes.forEach(n => {{ (byGroup[n.group] = byGroup[n.group] || []).push(n); }});
  const pos = {{}};
  for (const g in byGroup) {{
    const x = GROUP_X[g] || 0;
    byGroup[g].forEach((n, i) => {{ pos[n.id] = {{ x, y: i * 78 }}; }});
  }}
  return pos;
}}
function render() {{
  const pos = layout();
  const canvas = document.getElementById("canvas");
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("width", 1840);
  svg.setAttribute("height", 900);
  svg.style.position = "absolute";
  svg.style.left = 0;
  svg.style.top = 0;
  FLOW.edges.forEach(e => {{
    const s = pos[e.source], t = pos[e.target];
    if (!s || !t) return;
    const x1 = s.x + 160, y1 = s.y + 28, x2 = t.x, y2 = t.y + 28;
    const mx = (x1 + x2) / 2;
    const p = document.createElementNS(svgNS, "path");
    p.setAttribute("d", `M ${{x1}} ${{y1}} C ${{mx}} ${{y1}}, ${{mx}} ${{y2}}, ${{x2}} ${{y2}}`);
    p.setAttribute("fill", "none");
    p.setAttribute("stroke", EDGE[STATUS] || EDGE.idle);
    p.setAttribute("stroke-width", 1.5);
    svg.appendChild(p);
  }});
  canvas.appendChild(svg);
  FLOW.nodes.forEach(n => {{
    const p = pos[n.id];
    if (!p) return;
    const div = document.createElement("div");
    div.className = "node " + (FAILED.has(n.id) ? "failed " : "") + STATUS;
    div.style.left = p.x + "px";
    div.style.top = p.y + "px";
    div.textContent = n.label;
    canvas.appendChild(div);
  }});
  const legend = document.createElement("div");
  legend.style.cssText = "position:absolute;left:0;bottom:-28px;font-size:12px;color:#9ca3af;";
  legend.textContent = "图例：" + Object.values(GROUP_LABEL).join(" · ") + " ｜ 绿=成功 橙=部分 红=失败 蓝=运行中 灰=待命";
  canvas.appendChild(legend);
}}
render();
</script>
</body>
</html>
"""


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="导出自包含 HTML 链路报告")
    ap.add_argument("--db", default=str(ROOT / "demo.db"))
    ap.add_argument(
        "--out",
        default="",
        help="输出路径（默认 exports/flow-report-<时间>.html）",
    )
    args = ap.parse_args()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    out = Path(args.out) if args.out else (
        ROOT / "exports" / f"flow-report-{datetime.now():%Y%m%d-%H%M%S}.html"
    )
    if not out.is_absolute():
        out = ROOT / out
    conn = db.connect(str(db_path))
    try:
        html = render_html(conn)
    finally:
        conn.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(json.dumps({"ok": True, "file": str(out), "bytes": len(html.encode("utf-8"))}))


if __name__ == "__main__":
    main()
