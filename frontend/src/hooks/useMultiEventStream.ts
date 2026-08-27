import { useEffect, useMemo, useRef, useState } from "react";

import type { EventStreamStatus } from "./useEventStream";

export interface StreamState {
  status: EventStreamStatus;
  notice: string | null;
}

export interface UseMultiEventStreamOptions {
  /** Fallback polling interval (ms), shown in degrade notices. */
  pollIntervalMs?: number;
  /** Consecutive failed open attempts per stream before it degrades to polling. */
  maxFailedOpenAttempts?: number;
  /**
   * Called with the parsed event payload whenever any stream receives one.
   * Feature-agnostic: the hook only forwards data; merging, sorting and
   * deduplication are left to the caller.
   */
  onEvent?: (data: unknown) => void;
}

export interface UseMultiEventStreamResult {
  /** Per-workspace connection state, keyed by workspace id. */
  streams: Record<string, StreamState>;
  /** Number of streams currently open (live). */
  connectedCount: number;
  /** True when any stream degraded to polling; the caller enables fallback refresh. */
  degraded: boolean;
}

const DEFAULT_POLL_INTERVAL_MS = 30000;
const DEFAULT_MAX_FAILED_OPEN_ATTEMPTS = 3;

function streamUrl(workspaceId: string): string {
  return `/works/${encodeURIComponent(workspaceId)}/events/stream`;
}

/**
 * Subscribe to GET /works/{id}/events/stream for every workspace id and
 * expose the per-stream connection state.
 *
 * - Streams are attached and detached incrementally as `workspaceIds` change.
 * - Event data is parsed as JSON and forwarded to the optional `onEvent`
 *   callback; invalid JSON is passed through as the raw string.
 * - A stream that never opens after repeated attempts degrades to "polling"
 *   (the caller decides what polling means); a drop after a successful open
 *   is left to EventSource's built-in auto-reconnect.
 */
export function useMultiEventStream(
  workspaceIds: string[],
  options: UseMultiEventStreamOptions = {},
): UseMultiEventStreamResult {
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const maxFailedOpenAttempts =
    options.maxFailedOpenAttempts ?? DEFAULT_MAX_FAILED_OPEN_ATTEMPTS;

  const onEventRef = useRef(options.onEvent);
  onEventRef.current = options.onEvent;
  const pollIntervalMsRef = useRef(pollIntervalMs);
  pollIntervalMsRef.current = pollIntervalMs;
  const maxFailedOpenAttemptsRef = useRef(maxFailedOpenAttempts);
  maxFailedOpenAttemptsRef.current = maxFailedOpenAttempts;

  const [streams, setStreams] = useState<Record<string, StreamState>>({});
  const sourcesRef = useRef(new Map<string, EventSource>());
  // Streams that degraded to polling must not be re-attached when
  // `workspaceIds` changes; the record lives until unmount.
  const degradedIdsRef = useRef(new Set<string>());
  const idsKey = workspaceIds.join("\u0000");

  function degradedNotice(): string {
    return `实时通道持续失败，已切换为轮询（${Math.round(pollIntervalMsRef.current / 1000)} 秒）`;
  }

  // Keep one state entry per current workspace; drop entries for removed ids.
  useEffect(() => {
    const ids = idsKey === "" ? [] : idsKey.split("\u0000");
    setStreams((prev) => {
      const next: Record<string, StreamState> = {};
      for (const id of ids) {
        if (prev[id] !== undefined) {
          next[id] = prev[id];
        } else if (degradedIdsRef.current.has(id)) {
          next[id] = { status: "polling", notice: degradedNotice() };
        } else {
          next[id] = { status: "connecting", notice: null };
        }
      }
      return next;
    });
  }, [idsKey]);

  // Attach new streams, detach removed ones, and mark everything polling when
  // EventSource is unavailable in the environment.
  useEffect(() => {
    const ids = idsKey === "" ? [] : idsKey.split("\u0000");
    const sources = sourcesRef.current;
    const current = new Set(ids);
    const eventSourceAvailable =
      typeof window !== "undefined" && typeof window.EventSource === "function";

    for (const [id, source] of sources) {
      if (!current.has(id)) {
        source.close();
        sources.delete(id);
      }
    }

    if (!eventSourceAvailable) {
      for (const id of ids) {
        if (sources.has(id)) {
          continue;
        }
        setStreams((prev) => {
          const currentState = prev[id];
          if (currentState === undefined) {
            return prev;
          }
          const notice = `实时通道不可用，已切换为轮询（${Math.round(pollIntervalMsRef.current / 1000)} 秒）`;
          if (
            currentState.status === "polling" &&
            currentState.notice === notice
          ) {
            return prev;
          }
          return { ...prev, [id]: { status: "polling", notice } };
        });
      }
      return undefined;
    }

    for (const id of ids) {
      if (degradedIdsRef.current.has(id) || sources.has(id)) {
        continue;
      }
      sources.set(id, attachStream(id));
    }
    return undefined;
  }, [idsKey]);

  // Close every remaining stream on unmount.
  useEffect(() => {
    const sources = sourcesRef.current;
    return () => {
      for (const source of sources.values()) {
        source.close();
      }
      sources.clear();
      degradedIdsRef.current.clear();
    };
  }, []);

  function attachStream(id: string): EventSource {
    const source = new window.EventSource(streamUrl(id));
    let opened = false;
    let failedOpens = 0;

    const update = (patch: StreamState) => {
      setStreams((prev) => {
        const current = prev[id];
        if (current === undefined) {
          return prev;
        }
        if (current.status === patch.status && current.notice === patch.notice) {
          return prev;
        }
        return { ...prev, [id]: patch };
      });
    };

    source.onopen = () => {
      opened = true;
      failedOpens = 0;
      update({ status: "open", notice: null });
    };

    source.onmessage = (message) => {
      let data: unknown = message.data;
      if (typeof message.data === "string") {
        try {
          data = JSON.parse(message.data);
        } catch {
          // Keep the raw string so callers can decide how to surface it.
        }
      }
      onEventRef.current?.(data);
    };

    source.onerror = () => {
      if (!opened) {
        failedOpens += 1;
        update({
          status: "reconnecting",
          notice: `实时连接失败，正在重连（第 ${failedOpens} 次）`,
        });
        if (failedOpens >= maxFailedOpenAttemptsRef.current) {
          source.close();
          sourcesRef.current.delete(id);
          degradedIdsRef.current.add(id);
          update({ status: "polling", notice: degradedNotice() });
        }
        return;
      }
      update({ status: "reconnecting", notice: "连接断开，正在自动重连…" });
    };

    return source;
  }

  const { connectedCount, degraded } = useMemo(() => {
    const values = Object.values(streams);
    return {
      connectedCount: values.filter((state) => state.status === "open").length,
      degraded: values.some((state) => state.status === "polling"),
    };
  }, [streams]);

  return { streams, connectedCount, degraded };
}
