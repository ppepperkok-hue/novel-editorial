import { useEffect, useMemo, useState } from "react";
import { Background, Controls, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { getFlow } from "../api.js";

const API_BASE =
  location.protocol === "file:" || !location.host ? "http://localhost:8000" : "";

const GROUP_X = {
  trigger: 0,
  preflight: 200,
  dispatch: 400,
  meta: 600,
  plan: 800,
  track_a: 1000,
  track_b: 1200,
  publish: 1400,
  wrapup: 1600,
};

const GROUP_LABEL = {
  trigger: "触发",
  preflight: "预检",
  dispatch: "分派",
  meta: "作品资料",
  plan: "大纲与守护",
  track_a: "A 轨写作",
  track_b: "B 轨写作",
  publish: "发布链",
  wrapup: "收尾",
};

const STATUS_META = {
  completed: ["上次成功", "ok"],
  success: ["上次成功", "ok"],
  partial: ["上次部分成功", "warn"],
  failed: ["上次失败", "bad"],
  error: ["上次失败", "bad"],
  running: ["运行中", "run"],
};

export default function FlowPage() {
  const [flow, setFlow] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await getFlow();
        if (alive) {
          setFlow(r);
          setError("");
        }
      } catch (e) {
        if (alive) setError(String(e));
      }
    };
    load();
    const t = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const { nodes, edges } = useMemo(() => {
    if (!flow) return { nodes: [], edges: [] };
    const last = flow.last_run || {};
    const status = last.status || "idle";
    const failed = new Set(flow.failed_ids || []);
    const byGroup = {};
    for (const n of flow.nodes || []) {
      (byGroup[n.group] = byGroup[n.group] || []).push(n);
    }
    const rfNodes = [];
    for (const [group, list] of Object.entries(byGroup)) {
      const x = GROUP_X[group] ?? 0;
      list.forEach((n, i) => {
        rfNodes.push({
          id: n.id,
          position: { x, y: i * 84 },
          data: { label: n.label },
          className: `flow-node flow-${status}${failed.has(n.id) ? " flow-failed" : ""}`,
          style: { width: 160 },
        });
      });
    }
    const rfEdges = (flow.edges || []).map((e, i) => ({
      id: `e-${i}`,
      source: e.source,
      target: e.target,
      type: "smoothstep",
      className: `flow-edge flow-${status}`,
    }));
    return { nodes: rfNodes, edges: rfEdges };
  }, [flow]);

  const last = flow?.last_run || null;
  const sm = STATUS_META[last?.status] || ["待命（暂无运行）", "idle"];
  const groupLegend = Object.entries(GROUP_X).map(([g]) => (
    <span key={g} className="chip chip-soft">
      {GROUP_LABEL[g]}
    </span>
  ));

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm text-red-400">
          链路数据不可达：{error}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <div className="panel flex flex-wrap items-center gap-3 px-4 py-2.5 text-xs">
          <span className="text-sm font-semibold">日更链路</span>
          <span className={`chip ${sm[1] === "ok" ? "chip-ok" : sm[1] === "warn" ? "chip-warn" : sm[1] === "bad" ? "chip-bad" : sm[1] === "run" ? "chip-warn" : "chip-soft"}`}>
            {sm[0]}
          </span>
          {last ? (
            <>
              <span className="muted">
                {String(last.run_id || "").slice(0, 24)} · 发布 {last.published ?? 0} 章
              </span>
              {last.error ? <span className="muted text-red-400">{(last.error || "").slice(0, 90)}</span> : null}
            </>
          ) : null}
          <a
            className="btn ml-auto !px-3 !py-1"
            href={API_BASE + "/api/export/flow"}
            download="pipeline-flow.html"
          >
            ⬇ 导出 HTML 报告
          </a>
        </div>
        <div className="panel flex flex-wrap items-center gap-1.5 px-4 py-2.5 text-xs">
          <span className="muted mr-1">图例：</span>
          {groupLegend}
          <span className="chip chip-soft">● 绿=成功 · 橙=部分 · 红=失败 · 蓝=运行中 · 灰=待命</span>
        </div>
      </div>

      <div className="panel overflow-hidden p-0">
        <div className="flow-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            minZoom={0.25}
            maxZoom={1.5}
            nodesConnectable={false}
            nodesDraggable
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={24} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      </div>
    </div>
  );
}
