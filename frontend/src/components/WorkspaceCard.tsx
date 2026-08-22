import type { OverviewItem } from "../api/client";
import { formatDateTime } from "../utils/format";

interface WorkspaceCardProps {
  item: OverviewItem;
  selected: boolean;
  onClick: () => void;
}

export default function WorkspaceCard({
  item,
  selected,
  onClick,
}: WorkspaceCardProps) {
  return (
    <button
      type="button"
      className={`workspace-card${selected ? " workspace-card--selected" : ""}`}
      onClick={onClick}
      aria-pressed={selected}
      data-testid="workspace-card"
    >
      <span className="workspace-card-title">{item.title}</span>
      <span className="workspace-card-meta">状态：{item.status}</span>
      <span className="workspace-card-meta">待拍板：{item.pending_count}</span>
      <span className="workspace-card-meta">进度：{item.structure}</span>
      <span className="workspace-card-meta">
        最近活动：{formatDateTime(item.last_activity)}
      </span>
    </button>
  );
}
