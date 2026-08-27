import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getGlobalEvents,
  listWorks,
  type EditorialEvent,
} from "../../api/client";
import {
  useMultiEventStream,
  type StreamState,
} from "../../hooks/useMultiEventStream";
import { usePolling } from "../../hooks/usePolling";

const MAX_MERGED_EVENTS = 50;

export interface OverviewEventFeed {
  events: EditorialEvent[];
  loading: boolean;
  error: Error | null;
  reload: () => void;
  /** Global fallback skipped count; null while the SSE path is live. */
  skipped: number | null;
  /** Aggregated connection state for the EventStreamStatus component. */
  streamStatus: StreamState;
  liveCount: number;
  worksTotal: number;
  degraded: boolean;
  source: "/works" | "/events";
}

function eventTimeMs(time: string): number {
  const ms = Date.parse(time);
  return Number.isNaN(ms) ? 0 : ms;
}

function parseEvent(data: unknown): EditorialEvent | null {
  if (typeof data !== "object" || data === null) {
    return null;
  }
  const record = data as Record<string, unknown>;
  if (
    typeof record.id !== "string" ||
    typeof record.workspace_id !== "string" ||
    typeof record.type !== "string" ||
    typeof record.time !== "string" ||
    typeof record.actor !== "string" ||
    typeof record.payload !== "object" ||
    record.payload === null
  ) {
    return null;
  }
  return {
    id: record.id,
    workspace_id: record.workspace_id,
    type: record.type,
    time: record.time,
    actor: record.actor,
    payload: record.payload as Record<string, unknown>,
  };
}

/**
 * Merge incoming events into the newest-first list, deduplicated by id.
 * Returns the previous reference when nothing changed so consumers can skip
 * unnecessary re-renders.
 */
function mergeEvents(
  current: EditorialEvent[],
  incoming: EditorialEvent[],
): EditorialEvent[] {
  if (incoming.length === 0) {
    return current;
  }
  const byId = new Map<string, EditorialEvent>();
  for (const event of current) {
    byId.set(event.id, event);
  }
  for (const event of incoming) {
    // Keep the previously merged object for duplicates so an unchanged
    // fallback poll resolves to the same array reference and skips re-renders.
    if (!byId.has(event.id)) {
      byId.set(event.id, event);
    }
  }
  const merged = [...byId.values()].sort(
    (a, b) => eventTimeMs(b.time) - eventTimeMs(a.time),
  );
  const capped =
    merged.length > MAX_MERGED_EVENTS ? merged.slice(0, MAX_MERGED_EVENTS) : merged;
  if (
    capped.length === current.length &&
    capped.every((event, index) => event === current[index])
  ) {
    return current;
  }
  return capped;
}

/**
 * Overview-only realtime event feed (FE-I).
 *
 * The backend deliberately has no cross-workspace merge stream, so this hook
 * subscribes one SSE stream per workspace (GET /works/{id}/events/stream),
 * merges incoming events newest-first with dedup by id, and falls back to the
 * existing global GET /events polling (getGlobalEvents) whenever any stream
 * degrades, so the refresh capability is never silently dropped.
 */
export function useOverviewEventFeed(
  pollIntervalMs: number,
  maxFailedOpenAttempts = 3,
): OverviewEventFeed {
  const works = usePolling(listWorks, pollIntervalMs);
  const workspaceIds = useMemo(
    () => (works.data ?? []).map((workspace) => workspace.id),
    [works.data],
  );

  const [events, setEvents] = useState<EditorialEvent[]>([]);

  const mergeIncoming = useCallback((incoming: EditorialEvent[]) => {
    setEvents((prev) => {
      const next = mergeEvents(prev, incoming);
      return next;
    });
  }, []);

  const handleEvent = useCallback(
    (data: unknown) => {
      const event = parseEvent(data);
      if (event === null) {
        return;
      }
      mergeIncoming([event]);
    },
    [mergeIncoming],
  );

  const multi = useMultiEventStream(workspaceIds, {
    pollIntervalMs,
    maxFailedOpenAttempts,
    onEvent: handleEvent,
  });

  // Global polling fallback: enabled only while any stream is degraded.
  const fallback = usePolling(getGlobalEvents, pollIntervalMs, multi.degraded);

  // Merge the fallback snapshot whenever it arrives (dedup by id keeps it
  // harmless next to the live SSE events of healthy streams).
  useEffect(() => {
    if (fallback.data === null) {
      return;
    }
    mergeIncoming(fallback.data.events);
  }, [fallback.data, mergeIncoming]);

  const streamStatus = useMemo<StreamState>(() => {
    const streamValues = Object.values(multi.streams);
    if (streamValues.length === 0) {
      return { status: "connecting", notice: null };
    }
    const openCount = streamValues.filter((state) => state.status === "open").length;
    const total = streamValues.length;
    if (streamValues.some((state) => state.status === "polling")) {
      return {
        status: "polling",
        notice: `${openCount}/${total} 部作品实时，已启用轮询兜底（${Math.round(pollIntervalMs / 1000)} 秒）`,
      };
    }
    if (streamValues.some((state) => state.status === "reconnecting")) {
      return {
        status: "reconnecting",
        notice: `${openCount}/${total} 部作品实时，连接断开正在自动重连…`,
      };
    }
    if (streamValues.every((state) => state.status === "open")) {
      return { status: "open", notice: `${total}/${total} 部作品已连接` };
    }
    return { status: "connecting", notice: `${openCount}/${total} 部作品实时` };
  }, [multi.streams, pollIntervalMs]);

  const streamValues = Object.values(multi.streams);

  const error = works.error ?? (multi.degraded ? fallback.error : null);
  const source = works.error !== null ? "/works" : "/events";
  const degraded = multi.degraded;

  const settling =
    workspaceIds.length > 0 &&
    !degraded &&
    events.length === 0 &&
    streamValues.length > 0 &&
    streamValues.every((state) => state.status === "connecting");
  const loading =
    works.loading ||
    (works.data !== null && degraded && fallback.data === null) ||
    settling;

  const reload = useCallback(() => {
    works.reload();
    if (degraded) {
      fallback.reload();
    }
  }, [degraded, fallback, works]);

  return {
    events,
    loading,
    error,
    reload,
    skipped: degraded ? fallback.data?.skipped ?? null : null,
    streamStatus,
    liveCount: multi.connectedCount,
    worksTotal: workspaceIds.length,
    degraded,
    source,
  };
}
