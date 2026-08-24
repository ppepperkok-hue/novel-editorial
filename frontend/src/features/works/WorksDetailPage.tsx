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

interface AgentProfileFieldProps {
  label: string;
  value: string;
}

function AgentProfileField({ label, value }: AgentProfileFieldProps) {
  return (
    <p className="agent-field">
      <span className="agent-field-label">{label}</span>
      <span className="agent-field-value">{value}</span>
    </p>
  );
}

function AgentCard({ agent }: { agent: BandAgent }) {
  return (
    <li className="agent-card" data-testid="agent-card">
      <header className="agent-card-head">
        <h4>{agent.name}</h4>
        <span className="agent-role">{roleLabel(agent.role)}</span>
      </header>
      <AgentProfileField label="性格" value={agent.personality} />
      <AgentProfileField label="立场" value={agent.stance} />
      <AgentProfileField label="价值观" value={agent.values} />
      <AgentProfileField label="审美" value={agent.aesthetic} />
      <AgentProfileField label="情绪基线" value={agent.emotion_baseline} />
      <AgentProfileField label="心情" value={agent.mood} />
      <AgentProfileField label="工作习惯" value={agent.work_habits} />
      <AgentProfileField label="弱点" value={agent.weaknesses} />
      <AgentProfileField label="人际预设" value={agent.relationship_presets} />
      <AgentProfileField label="私心" value={agent.private_motive} />
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
        <h2>作品详情</h2>
        <Link className="text-link" to="/works">
          返回作品列表
        </Link>
      </header>
      <nav className="workspace-toolbar" aria-label="工作台入口">
        <Link
          className="text-link"
          to={`/works/${workspaceId ?? ""}/talk`}
          data-testid="workspace-talk-link"
        >
          进入对话工作台
        </Link>
        <Link
          className="text-link"
          to={`/works/${workspaceId ?? ""}/writer`}
          data-testid="workspace-writer-link"
        >
          进入正文工作台
        </Link>
      </nav>
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
          <section className="works-overview" data-testid="works-overview">
            <h3>{workspace.data.title}</h3>
            <p className="works-overview-meta">
              类型：{workspace.data.genre || "未设定"} · 状态：
              {workspace.data.status}
            </p>
            {workspace.data.description ? (
              <p className="works-overview-desc">
                {workspace.data.description}
              </p>
            ) : null}
            <p className="works-overview-meta">
              创建于 {formatDateTime(workspace.data.created_at)}
            </p>
          </section>
          <section className="band-section" data-testid="band-section">
            <h3>班子档案</h3>
            {workspace.data.band.length === 0 ? (
              <EmptyState title="班子还没有成员" hint="创建作品后默认班子会自动就位" />
            ) : null}
            {workspace.data.band.length > 0 ? (
              <ul className="agent-grid">
                {workspace.data.band.map((agent) => (
                  <AgentCard key={agent.id} agent={agent} />
                ))}
              </ul>
            ) : null}
          </section>
        </>
      ) : null}
    </section>
  );
}
