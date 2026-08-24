import type { EventStreamStatus as StreamStatus } from "../hooks/useEventStream";

const STATUS_LABELS: Record<StreamStatus, string> = {
  connecting: "连接中…",
  open: "已连接",
  reconnecting: "连接断开，正在自动重连…",
  polling: "轮询模式",
};

interface EventStreamStatusProps {
  status: StreamStatus;
  /** Specific notice (reconnect attempts, fallback reason) overrides the label. */
  notice: string | null;
}

/**
 * One-line connection state for the workspace SSE stream.
 *
 * States: connecting (initial handshake), open (live), reconnecting
 * (auto-retry after a drop, with a visible notice), polling (fallback mode
 * after EventSource is unavailable or keeps failing, with interval in the
 * notice). Renders a visible status even when the stream is healthy.
 */
export default function EventStreamStatus({
  status,
  notice,
}: EventStreamStatusProps) {
  return (
    <span
      className={`event-stream-status event-stream-status--${status}`}
      data-testid="event-stream-status"
      role="status"
    >
      实时连接：{notice ?? STATUS_LABELS[status]}
    </span>
  );
}
