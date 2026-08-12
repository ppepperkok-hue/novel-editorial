import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useApi } from "../lib/use-api.js";

describe("useApi", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("loads data and clears error", async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: 1 });
    const { result } = renderHook(() => useApi(fetcher));
    expect(result.current.loading).toBe(true);
    await act(async () => {});
    expect(result.current.data).toEqual({ ok: 1 });
    expect(result.current.error).toBe("");
    expect(result.current.loading).toBe(false);
  });

  it("surfaces fetch errors explicitly", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("backend offline"));
    const { result } = renderHook(() => useApi(fetcher));
    await act(async () => {});
    expect(result.current.error).toContain("backend offline");
    expect(result.current.data).toBeNull();
  });

  it("polls on the configured interval", async () => {
    const fetcher = vi.fn().mockResolvedValue({ tick: 1 });
    renderHook(() => useApi(fetcher, { interval: 5000 }));
    await act(async () => {});
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("refresh can be triggered manually", async () => {
    let n = 0;
    const fetcher = vi.fn(async () => ({ n: ++n }));
    const { result } = renderHook(() => useApi(fetcher));
    await act(async () => {});
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.data).toEqual({ n: 2 });
  });
});
