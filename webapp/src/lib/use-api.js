import { useCallback, useEffect, useRef, useState } from "react";

/**
 * 统一数据获取 hook：loading / error / 轮询 / 手动刷新。
 * fetcher 变化不触发重建（用 ref 持有最新引用），deps 显式控制。
 * @stable
 */
export function useApi(fetcher, { interval = 0, enabled = true, deps = [] } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  const aliveRef = useRef(true);
  const timerRef = useRef(null);
  fetcherRef.current = fetcher;

  const refresh = useCallback(async () => {
    if (!enabled) return;
    try {
      const result = await fetcherRef.current();
      if (aliveRef.current) {
        setData(result);
        setError("");
      }
    } catch (err) {
      if (aliveRef.current) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (aliveRef.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  useEffect(() => {
    aliveRef.current = true;
    setLoading(true);
    refresh();
    if (interval > 0) {
      timerRef.current = setInterval(refresh, interval);
    }
    return () => {
      aliveRef.current = false;
      clearInterval(timerRef.current);
    };
  }, [refresh, interval]);

  return { data, error, loading, refresh };
}
