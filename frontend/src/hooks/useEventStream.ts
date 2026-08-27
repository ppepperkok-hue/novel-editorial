import { useCallback, useEffect, useRef, useState } from "react";
import {
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";

import { usePolling } from "./usePolling";

export type EventStreamStatus =
  | "connecting"
  | "open"
  | "reconnecting"
  | "polling";

export interface UseEventStreamOptions {
  /** Fallback polling interval (ms), used when EventSource is unavailable or keeps failing. */
  pollIntervalMs?: number;
  /** Consecutive failed open attempts before falling back to polling. */
  maxFailedOpenAttempts?: number;
  /**
   * Called with the event payload whenever the stream receives one. The hook
   * stays feature-agnostic: the raw event data is passed through as parsed
   * JSON (or the original string when it is not valid JSON), and callers that
   * only need to refresh queries keep using `invalidateKeys` instead.
   */
  onEvent?: (data: unknown) => void;
  /**
   * Build the query keys to invalidate when an event arrives (or a polling
   * tick fires). The hook stays feature-agnostic: each workbench injects the
   * keys for the queries it actually shows.
   */
  invalidateKeys?: (workspaceId: string) => QueryKey[];
}

export interface UseEventStreamResult {
  status: EventStreamStatus;
  notice: string | null;
}

const DEFAULT_POLL_INTERVAL_MS = 30000;
const DEFAULT_MAX_FAILED_OPEN_ATTEMPTS = 3;

function streamUrl(workspaceId: string): string {
  return `/works/${encodeURIComponent(workspaceId)}/events/stream`;
}

/**
 * Subscribe to GET /works/{id}/events/stream via EventSource and invalidate
 * the injected query keys on every event, so new data appears without manual
 * refresh.
 *
 * - `Last-Event-ID` resume is handled by the browser's EventSource itself.
 * - Connection state is exposed so the UI can show connecting / open /
 *   reconnect notices.
 * - Fallback: when EventSource is missing or never opens after repeated
 *   attempts, the hook degrades to `usePolling` (configurable interval) and
 *   keeps invalidating the same queries instead of silently dropping the
 *   refresh capability. A drop after a successful open is left to
 *   EventSource's built-in auto-reconnect.
 */
export function useEventStream(
  workspaceId: string | undefined,
  options: UseEventStreamOptions = {},
): UseEventStreamResult {
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const maxFailedOpenAttempts =
    options.maxFailedOpenAttempts ?? DEFAULT_MAX_FAILED_OPEN_ATTEMPTS;
  const invalidateKeys = options.invalidateKeys;
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"sse" | "polling">("sse");
  const [status, setStatus] = useState<EventStreamStatus>("connecting");
  const [notice, setNotice] = useState<string | null>(null);

  const workspaceIdRef = useRef(workspaceId);
  workspaceIdRef.current = workspaceId;

  const invalidateKeysRef = useRef(invalidateKeys);
  invalidateKeysRef.current = invalidateKeys;

  const onEventRef = useRef(options.onEvent);
  onEventRef.current = options.onEvent;

  const invalidateWorkspace = useCallback(() => {
    const current = workspaceIdRef.current;
    if (current === undefined || current === "") {
      return;
    }
    const keys = invalidateKeysRef.current?.(current) ?? [];
    for (const key of keys) {
      void queryClient.invalidateQueries({ queryKey: key });
    }
  }, [queryClient]);

  const invalidateRef = useRef(invalidateWorkspace);
  invalidateRef.current = invalidateWorkspace;

  // Polling fallback: runs only while `mode` is "polling"; each tick
  // invalidates the same queries an SSE event would refresh.
  const pollFetcher = useCallback(async () => {
    invalidateRef.current();
    return true;
  }, []);
  usePolling(pollFetcher, pollIntervalMs, mode === "polling");

  useEffect(() => {
    setMode("sse");
    setStatus("connecting");
    setNotice(null);
    const current = workspaceIdRef.current;
    if (current === undefined || current === "") {
      return undefined;
    }
    if (
      typeof window === "undefined" ||
      typeof window.EventSource !== "function"
    ) {
      setMode("polling");
      setStatus("polling");
      setNotice(
        `实时通道不可用，已切换为轮询（${Math.round(pollIntervalMs / 1000)} 秒）`,
      );
      return undefined;
    }

    let disposed = false;
    let opened = false;
    let failedOpens = 0;
    const source = new window.EventSource(streamUrl(current));

    source.onopen = () => {
      if (disposed) {
        return;
      }
      opened = true;
      failedOpens = 0;
      setStatus("open");
      setNotice(null);
    };

    source.onmessage = (message) => {
      if (disposed) {
        return;
      }
      invalidateRef.current();
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
      if (disposed) {
        return;
      }
      if (!opened) {
        failedOpens += 1;
        setStatus("reconnecting");
        setNotice(`实时连接失败，正在重连（第 ${failedOpens} 次）`);
        if (failedOpens >= maxFailedOpenAttempts) {
          source.close();
          setMode("polling");
          setStatus("polling");
          setNotice(
            `实时通道持续失败，已切换为轮询（${Math.round(pollIntervalMs / 1000)} 秒）`,
          );
        }
        return;
      }
      setStatus("reconnecting");
      setNotice("连接断开，正在自动重连…");
    };

    return () => {
      disposed = true;
      source.close();
    };
  }, [maxFailedOpenAttempts, pollIntervalMs, workspaceId]);

  return { status, notice };
}
