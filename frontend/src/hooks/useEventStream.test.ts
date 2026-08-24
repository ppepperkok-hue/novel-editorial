import {
  QueryClient,
  QueryClientProvider,
  type QueryKey,
} from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FakeEventSource } from "../test/fakeEventSource";
import {
  useEventStream,
  type UseEventStreamOptions,
} from "./useEventStream";

function wrapperFor(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  };
}

const talkAndPendingKeys = (workspaceId: string): QueryKey[] => [
  ["works", workspaceId, "talk"],
  ["works", workspaceId, "pending"],
];

const talkOnlyKeys = (workspaceId: string): QueryKey[] => [
  ["works", workspaceId, "talk"],
];

function renderWithClient(
  options: UseEventStreamOptions = {},
  invalidateKeys = talkAndPendingKeys,
) {
  const queryClient = new QueryClient();
  const invalidateSpy = vi
    .spyOn(queryClient, "invalidateQueries")
    .mockResolvedValue(undefined);
  const rendered = renderHook(
    () => useEventStream("w-a", { ...options, invalidateKeys }),
    {
      wrapper: wrapperFor(queryClient),
    },
  );
  return { queryClient, invalidateSpy, ...rendered };
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeEventSource.reset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("useEventStream", () => {
  it("opens the stream and invalidates the injected keys on each event", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { result, invalidateSpy } = renderWithClient();

    expect(result.current.status).toBe("connecting");
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toBe("/works/w-a/events/stream");

    act(() => {
      FakeEventSource.instances[0].emitOpen();
    });
    expect(result.current.status).toBe("open");
    expect(result.current.notice).toBeNull();

    act(() => {
      FakeEventSource.instances[0].emitMessage("{}");
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["works", "w-a", "talk"],
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["works", "w-a", "pending"],
    });
  });

  it("only invalidates the keys the caller injected", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { invalidateSpy } = renderWithClient({}, talkOnlyKeys);

    act(() => {
      FakeEventSource.instances[0].emitOpen();
    });
    act(() => {
      FakeEventSource.instances[0].emitMessage("{}");
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["works", "w-a", "talk"],
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: ["works", "w-a", "pending"],
    });
  });

  it("shows a reconnect notice after an open drop and keeps auto-reconnect", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { result } = renderWithClient();

    act(() => {
      FakeEventSource.instances[0].emitOpen();
    });
    act(() => {
      FakeEventSource.instances[0].emitError();
    });
    expect(result.current.status).toBe("reconnecting");
    expect(result.current.notice).toContain("自动重连");
    expect(FakeEventSource.instances[0].closed).toBe(false);
  });

  it("falls back to polling when EventSource is unavailable", async () => {
    vi.stubGlobal("EventSource", undefined);
    const { result, invalidateSpy } = renderWithClient(
      { pollIntervalMs: 1000 },
      talkOnlyKeys,
    );

    expect(result.current.status).toBe("polling");
    expect(result.current.notice).toContain("轮询");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["works", "w-a", "talk"],
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: ["works", "w-a", "pending"],
    });
  });

  it("falls back to polling after repeated failed open attempts", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { result, invalidateSpy } = renderWithClient({
      pollIntervalMs: 1000,
      maxFailedOpenAttempts: 2,
    });

    act(() => {
      FakeEventSource.instances[0].emitError();
    });
    expect(result.current.status).toBe("reconnecting");

    act(() => {
      FakeEventSource.instances[0].emitError();
    });
    expect(result.current.status).toBe("polling");
    expect(result.current.notice).toContain("轮询");
    expect(FakeEventSource.instances[0].closed).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["works", "w-a", "talk"],
    });
  });

  it("closes the stream on unmount", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { unmount } = renderWithClient();

    const instance = FakeEventSource.instances[0];
    unmount();
    expect(instance.closed).toBe(true);
  });

  it("reconnects to the new workspace when the id changes", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const queryClient = new QueryClient();
    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useEventStream(id),
      {
        initialProps: { id: "w-a" },
        wrapper: wrapperFor(queryClient),
      },
    );

    const first = FakeEventSource.instances[0];
    expect(first.url).toBe("/works/w-a/events/stream");
    act(() => {
      first.emitOpen();
    });
    expect(result.current.status).toBe("open");

    rerender({ id: "w-b" });
    expect(first.closed).toBe(true);
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[1].url).toBe("/works/w-b/events/stream");
    expect(result.current.status).toBe("connecting");
  });

  it("does not subscribe without a workspace id", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const queryClient = new QueryClient();
    const { result } = renderHook(() => useEventStream(undefined), {
      wrapper: wrapperFor(queryClient),
    });

    expect(FakeEventSource.instances).toHaveLength(0);
    expect(result.current.status).toBe("connecting");
  });
});
