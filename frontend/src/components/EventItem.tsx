import type { EditorialEvent } from "../api/client";
import { formatDateTime } from "../utils/format";

const EVENT_LABELS: Record<string, string> = {
  system: "系统",
  "agent.message": "伙伴发言",
  "draft.created": "新草稿",
  "quality_gate.passed": "质量门通过",
  "decision.requested": "待拍板",
  "review.rejected": "审稿退回",
};

function eventLabel(type: string): string {
  return EVENT_LABELS[type] ?? type;
}

function payloadSummary(payload: Record<string, unknown>): string {
  const entries = Object.entries(payload);
  if (entries.length === 0) {
    return "";
  }
  return entries
    .map(([key, value]) => {
      if (typeof value === "string") {
        return `${key}: ${value}`;
      }
      return `${key}: ${JSON.stringify(value)}`;
    })
    .join(" · ");
}

interface EventItemProps {
  event: EditorialEvent;
  onClick: () => void;
}

export default function EventItem({ event, onClick }: EventItemProps) {
  const summary = payloadSummary(event.payload);
  return (
    <li className="event-item">
      <button
        type="button"
        className="event-item-button"
        onClick={onClick}
        data-testid="event-item-button"
      >
        <span className="event-item-head">
          <span className="event-item-type">{eventLabel(event.type)}</span>
          <span className="event-item-actor">{event.actor}</span>
          <span className="event-item-time">{formatDateTime(event.time)}</span>
        </span>
        {summary ? <span className="event-item-summary">{summary}</span> : null}
      </button>
    </li>
  );
}
