import { useCallback, useEffect, useRef, useState } from "react";

export interface UsePollingResult<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
}

/**
 * Poll a fetcher every `intervalMs` while `enabled` is true.
 *
 * - The first poll starts immediately; later polls repeat on the interval.
 * - Unmounting cancels the timer and invalidates in-flight responses.
 * - A failed poll sets `error` but never stops the schedule: the next tick
 *   retries and a later success clears the error.
 * - `loading` is true only while there is no data yet, so refreshes keep the
 *   previous data visible instead of flashing the skeleton.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  enabled = true,
): UsePollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<Error | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const dataRef = useRef<T | null>(null);
  const sequenceRef = useRef(0);

  const run = useCallback(async () => {
    const requestId = ++sequenceRef.current;
    try {
      const result = await fetcherRef.current();
      if (requestId !== sequenceRef.current) {
        return;
      }
      dataRef.current = result;
      setData(result);
      setError(null);
      setLoading(false);
    } catch (err) {
      if (requestId !== sequenceRef.current) {
        return;
      }
      setError(err instanceof Error ? err : new Error(String(err)));
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return undefined;
    }
    setLoading(dataRef.current === null);
    void run();
    const timer = window.setInterval(() => {
      void run();
    }, intervalMs);
    return () => {
      sequenceRef.current += 1;
      window.clearInterval(timer);
    };
  }, [enabled, intervalMs, run]);

  const reload = useCallback(() => {
    void run();
  }, [run]);

  return { data, loading, error, reload };
}
