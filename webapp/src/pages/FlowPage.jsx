import { useMemo } from "react";
import { Background, Controls, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { API_BASE, getFlow } from "../api.js";
import { EmptyState, ErrorState, LoadingState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { Badge } from "../components/ui/badge.jsx";
import { Button } from "../components/ui/button.jsx";
import { useApi } from "../lib/use-api.js";

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

const NODE_STYLE = {
  idle: { borderColor: "var(--line)", color: "var(--ink-2)", background: "var(--surface-2)" },
  ok: { borderColor: "var(--ok)", color: "var(--ok)", background: "var(--ok-soft)" },
  failed: { borderColor: "var(--bad)", color: "var(--bad)", background: "var(--bad-soft)" },
  run: { borderColor: "var(--accent)", color: "var(--accent-ink)", background: "var(--accent-soft)" },
};

const EDGE_STYLE = {
  idle: { stroke: "var(--line-strong)" },
  ok: { stroke: "var(--ok)" },
  failed: { stroke: "var(--bad)" },
  run: { stroke: "var(--accent)" },
};

/** 链路：调度全链路拓扑。@stable */
export default function FlowPage() {
  const { data: flow, error, loading, refresh } = useApi(getFlow, { interval: 15000 });

  const { nodes, edges } = useMemo(() => {
    if (!flow) return { nodes: [], edges: [] };
    const last = flow.last_run || {};
    const overall = last.status || "idle";
    const nodeStatus = flow.node_status || {};
    const failed = new Set(flow.failed_ids || []);
    const statusOf = (nid) =>
      nodeStatus[nid] || (failed.has(nid) ? "failed" : overall === "running" ? "run" : "idle");

    const byGroup = {};
    for (const n of flow.nodes || []) {
      (byGroup[n.group] = byGroup[n.group] || []).push(n);
    }
    const rfNodes = [];
    for (const [group, list] of Object.entries(byGroup)) {
      const x = GROUP_X[group] ?? 0;
      list.forEach((n, i) => {
        const st = statusOf(n.id);
        rfNodes.push({
          id: n.id,
          position: { x, y: i * 84 },
          data: { label: n.label },
          style: { ...NODE_STYLE[st], width: 160, borderRadius: 6, fontSize: 12 },
        });
      });
    }
    const rfEdges = (flow.edges || []).map((e, i) => ({
      id: `e-${i}`,
      source: e.source,
      target: e.target,
      type: "smoothstep",
      style: EDGE_STYLE[statusOf(e.target)],
    }));
    return { nodes: rfNodes, edges: rfEdges };
  }, [flow]);

  const last = flow?.last_run || null;
  const statusTone = last?.status === "failed" || last?.status === "error" ? "bad" : "ok";
  const statusText =
    last?.status === "running"
      ? "运行中"
      : last?.status === "failed" || last?.status === "error"
        ? "上次失败"
        : last?.status === "partial"
          ? "上次部分成功"
          : last
            ? "上次成功"
            : "待命";

  return (
    <>
      <PageHeader
        title="链路"
        desc="调度全链路拓扑，不运行也能人工审查"
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.open(API_BASE + "/api/export/flow", "_blank")}
          >
            导出 HTML 报告
          </Button>
        }
      />
      {error ? (
        <ErrorState message="链路数据不可达" detail={error} onRetry={refresh} />
      ) : loading ? (
        <LoadingState rows={6} />
      ) : !flow ? (
        <EmptyState title="暂无链路数据" />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Badge tone={statusTone}>{statusText}</Badge>
            {last ? (
              <span className="text-xs text-ink-2">
                {String(last.run_id || "").slice(0, 24)} · 发布 {last.published ?? 0} 章
              </span>
            ) : null}
            <span className="ml-auto flex flex-wrap gap-1.5">
              {Object.entries(GROUP_X).map(([g]) => (
                <span
                  key={g}
                  className="inline-flex h-5 items-center rounded-pill border border-line bg-surface-2 px-2 text-[10.5px] text-ink-2"
                >
                  {GROUP_LABEL[g]}
                </span>
              ))}
            </span>
          </div>
          <div className="mt-4 h-[620px] overflow-hidden rounded-card border border-line bg-surface">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              fitView
              minZoom={0.25}
              maxZoom={1.5}
              nodesConnectable={false}
              proOptions={{ hideAttribution: true }}
            >
              <Background gap={24} color="var(--line)" />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
          <p className="mt-2 text-[11.5px] text-ink-3">
            红 = 失败节点 · 蓝 = 运行中 · 绿 = 上次成功 · 灰 = 待命
          </p>
        </>
      )}
    </>
  );
}
