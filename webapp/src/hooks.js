import { useCallback, useEffect, useRef, useState } from "react";

export function usePolling(fn, intervalMs, deps = []) {
  const [error, setError] = useState("");
  const [tickId, setTickId] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        await fnRef.current();
        if (alive) setError("");
      } catch (e) {
        if (alive) setError(String(e));
      }
    };
    tick();
    const t = setInterval(tick, intervalMs);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [intervalMs, tickId, ...deps]);

  const refresh = useCallback(() => setTickId((n) => n + 1), []);
  return [error, refresh];
}
