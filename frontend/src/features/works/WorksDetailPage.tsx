import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";

import type { BandAgent } from "../../api/client";
import {
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "../../components/StateViews";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { formatDateTime } from "../../utils/format";
import { useWorkspace } from "./useWorksQueries";

const ROLE_LABELS: Record<string, string> = {
  editor_in_chief: "总编",
  editor: "责编",
  writer: "写手",
  reviewer: "审稿",
};

function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

const WORKBENCHES: ReadonlyArray<readonly [string, string]> = [
  ["对话", "talk"],
  ["写作", "writer"],
  ["拍板", "decisions"],
  ["结构", "structure"],
  ["设定", "settings"],
  ["质量", "quality"],
  ["编辑部", "freewill"],
];

function AgentCard({ agent }: { agent: BandAgent }) {
  return (
    <li className="agent-card" data-testid="agent-card">
      <header className="agent-head">
        <span className="agent-avatar" aria-hidden="true">
          {agent.name.slice(0, 1)}
        </span>
        <div className="agent-identity">
          <h4>{agent.name}</h4>
          <span className="agent-role">{roleLabel(agent.role)}</span>
        </div>
        <span className="agent-mood">{agent.mood}</span>
      </header>
      <p className="agent-stance">{agent.stance}</p>
      <details className="agent-profile">
        <summary>完整档案</summary>
        <dl className="agent-fields">
          <dt>性格</dt>
          <dd>{agent.personality}</dd>
          <dt>价值观</dt>
          <dd>{agent.values}</dd>
          <dt>审美</dt>
          <dd>{agent.aesthetic}</dd>
          <dt>情绪基线</dt>
          <dd>{agent.emotion_baseline}</dd>
          <dt>工作习惯</dt>
          <dd>{agent.work_habits}</dd>
          <dt>弱点</dt>
          <dd>{agent.weaknesses}</dd>
          <dt>人际预设</dt>
          <dd>{agent.relationship_presets}</dd>
          <dt>私心</dt>
          <dd>{agent.private_motive}</dd>
        </dl>
      </details>
    </li>
  );
}

export default function WorksDetailPage() {
  const { workspaceId } = useParams();
  const workspace = useWorkspace(workspaceId);
  const setCurrentWorkspace = useWorkspaceStore(
    (state) => state.setCurrentWorkspace,
  );

  useEffect(() => {
    if (workspace.data !== undefined) {
      setCurrentWorkspace({
        id: workspace.data.id,
        title: workspace.data.title,
      });
    }
  }, [setCurrentWorkspace, workspace.data]);

  return (
    <section className="works-page" data-testid="works-detail-page">
      <header className="page-header">
        <h2>{workspace.data?.title ?? "作品详情"}</h2>
        <Link className="text-link" to="/works">
          返回作品列表
        </Link>
      </header>

      {workspace.isPending ? <SkeletonRows count={5} /> : null}
      {workspace.isError ? (
        <ErrorState
          source={`/works/${workspaceId ?? ""}`}
          message={workspace.error.message}
          onRetry={() => void workspace.refetch()}
        />
      ) : null}

      {workspace.isSuccess ? (
        <>
          <div className="kpi-row">
            <div className="kpi">
              <span className="kpi-value">
                {workspace.data.genre || "未设定"}
              </span>
              <span className="kpi-label">类型</span>
            </div>
            <div className="kpi">
              <span className="kpi-value">{workspace.data.status}</span>
              <span className="kpi-label">状态</span>
            </div>
            <div className="kpi kpi--accent">
              <span className="kpi-value">{workspace.data.band.length}</span>
              <span className="kpi-label">编辑部伙伴</span>
            </div>
            <div className="kpi">
              <span className="kpi-value">
                {formatDateTime(workspace.data.created_at).slice(0, 5)}
              </span>
              <span className="kpi-label">创建于</span>
            </div>
          </div>

          {workspace.data.description ? (
            <p className="works-desc" data-testid="works-overview">
              {workspace.data.description}
            </p>
          ) : null}

          <nav className="workspace-toolbar" aria-label="工作台入口">
            {WORKBENCHES.map(([label, path]) => (
              <Link
                key={path}
                className="workbench-link"
                to={`/works/${workspaceId ?? ""}/${path}`}
                data-testid={
                  path === "talk"
                    ? "workspace-talk-link"
                    : path === "writer"
                      ? "workspace-writer-link"
                      : undefined
                }
              >
                {label}
              </Link>
            ))}
          </nav>

          <section className="band-section" data-testid="band-section">
            <header className="panel-header">
              <h3>编辑部</h3>
            </header>
            {workspace.data.band.length === 0 ? (
              <EmptyState
                title="班子还没有成员"
                hint="创建作品后默认班子会自动就位"
              />
            ) : (
              <ul className="agent-grid">
                {workspace.data.band.map((agent) => (
                  <AgentCard key={agent.id} agent={agent} />
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}
    </section>
  );
}
