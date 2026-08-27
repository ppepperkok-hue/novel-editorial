import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FakeEventSource } from "../test/fakeEventSource";
import {
  useMultiEventStream,
  type UseMultiEventStreamOptions,
} from "./useMultiEventStream";

function renderMulti(
  workspaceIds: string[],
  options: UseMultiEventStreamOptions = {},
) {
  return renderHook(
    ({ ids }: { ids: string[] }) => useMultiEventStream(ids, options),
    { initialProps: { ids: workspaceIds } },
  );
}

function instanceFor(id: string): FakeEventSource {
  const found = FakeEventSource.instances.find(
    (instance) => instance.url === `/works/${id}/events/stream`,
  );
  if (found === undefined) {
    throw new Error(`no stream subscribed for ${id}`);
  }
  return found;
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

describe("useMultiEventStream", () => {
  it("subscribes one stream per workspace and reports open state", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { result } = renderMulti(["w-a", "w-b"]);

    expect(FakeEventSource.instances).toHaveLength(2);
    expect(result.current.connectedCount).toBe(0);
    expect(result.current.degraded).toBe(false);

    act(() => {
      instanceFor("w-a").emitOpen();
      instanceFor("w-b").emitOpen();
    });
    expect(result.current.streams["w-a"].status).toBe("open");
    expect(result.current.streams["w-b"].status).toBe("open");
    expect(result.current.connectedCount).toBe(2);
  });

  it("forwards parsed event data from any stream via onEvent", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onEvent = vi.fn();
    renderMulti(["w-a", "w-b"], { onEvent });

    act(() => {
      instanceFor("w-b").emitMessage(
        JSON.stringify({ id: "e1", workspace_id: "w-b", type: "draft.created" }),
      );
    });
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ id: "e1", workspace_id: "w-b" }),
    );
  });

  it("shows a reconnect notice after an open drop and keeps the stream", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { result } = renderMulti(["w-a"]);

    act(() => {
      instanceFor("w-a").emitOpen();
    });
    act(() => {
      instanceFor("w-a").emitError();
    });
    expect(result.current.streams["w-a"].status).toBe("reconnecting");
    expect(result.current.streams["w-a"].notice).toContain("自动重连");
    expect(instanceFor("w-a").closed).toBe(false);
  });

  it("degrades one stream to polling after repeated failed opens", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { result } = renderMulti(["w-a", "w-b"], {
      pollIntervalMs: 1000,
      maxFailedOpenAttempts: 2,
    });

    act(() => {
      instanceFor("w-a").emitOpen();
      instanceFor("w-b").emitError();
    });
    act(() => {
      instanceFor("w-b").emitError();
    });

    expect(result.current.streams["w-b"].status).toBe("polling");
    expect(result.current.streams["w-b"].notice).toContain("轮询");
    expect(instanceFor("w-b").closed).toBe(true);
    expect(result.current.streams["w-a"].status).toBe("open");
    expect(result.current.degraded).toBe(true);
    expect(result.current.connectedCount).toBe(1);
  });

  it("marks every stream polling when EventSource is unavailable", () => {
    vi.stubGlobal("EventSource", undefined);
    const { result } = renderMulti(["w-a", "w-b"], { pollIntervalMs: 1000 });

    expect(FakeEventSource.instances).toHaveLength(0);
    expect(result.current.streams["w-a"].status).toBe("polling");
    expect(result.current.streams["w-b"].status).toBe("polling");
    expect(result.current.streams["w-a"].notice).toContain("轮询");
    expect(result.current.degraded).toBe(true);
  });

  it("attaches new streams and closes removed ones when ids change", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { rerender } = renderMulti(["w-a", "w-b"]);
    const firstA = instanceFor("w-a");
    const firstB = instanceFor("w-b");
    act(() => {
      firstA.emitOpen();
    });

    rerender({ ids: ["w-b", "w-c"] });
    expect(firstA.closed).toBe(true);
    expect(firstB.closed).toBe(false);
    expect(FakeEventSource.instances).toHaveLength(3);
    expect(instanceFor("w-c").url).toBe("/works/w-c/events/stream");
  });

  it("does not re-attach a degraded stream when ids grow", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { result, rerender } = renderMulti(["w-a", "w-b"], {
      pollIntervalMs: 1000,
      maxFailedOpenAttempts: 2,
    });

    act(() => {
      instanceFor("w-a").emitOpen();
      instanceFor("w-b").emitError();
      instanceFor("w-b").emitError();
    });
    const firstB = instanceFor("w-b");
    expect(result.current.streams["w-b"].status).toBe("polling");
    expect(result.current.degraded).toBe(true);
    expect(firstB.closed).toBe(true);

    rerender({ ids: ["w-a", "w-b", "w-c"] });

    // Only w-c gets a new EventSource; w-b stays degraded and polling.
    expect(FakeEventSource.instances).toHaveLength(3);
    const wbInstances = FakeEventSource.instances.filter(
      (instance) => instance.url === "/works/w-b/events/stream",
    );
    expect(wbInstances).toHaveLength(1);
    expect(wbInstances[0]).toBe(firstB);
    expect(result.current.streams["w-b"].status).toBe("polling");
    expect(result.current.degraded).toBe(true);
    expect(result.current.streams["w-c"].status).toBe("connecting");
  });

  it("keeps a degraded stream degraded when its id leaves and returns", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { result, rerender } = renderMulti(["w-a", "w-b"], {
      pollIntervalMs: 1000,
      maxFailedOpenAttempts: 2,
    });

    act(() => {
      instanceFor("w-b").emitError();
      instanceFor("w-b").emitError();
    });
    expect(result.current.streams["w-b"].status).toBe("polling");

    rerender({ ids: ["w-a"] });
    expect(result.current.streams["w-b"]).toBeUndefined();

    rerender({ ids: ["w-a", "w-b"] });

    // The persistent degraded record survives id churn: no second EventSource,
    // state is restored as polling instead of flipping back to live.
    expect(FakeEventSource.instances).toHaveLength(2);
    const wbInstances = FakeEventSource.instances.filter(
      (instance) => instance.url === "/works/w-b/events/stream",
    );
    expect(wbInstances).toHaveLength(1);
    expect(wbInstances[0].closed).toBe(true);
    expect(result.current.streams["w-b"].status).toBe("polling");
    expect(result.current.streams["w-b"].notice).toContain("轮询");
    expect(result.current.degraded).toBe(true);
  });

  it("closes every stream on unmount", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { unmount } = renderMulti(["w-a", "w-b"]);
    const instances = [...FakeEventSource.instances];

    unmount();
    expect(instances.every((instance) => instance.closed)).toBe(true);
  });

  it("subscribes nothing when there are no workspaces", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { result } = renderMulti([]);

    expect(FakeEventSource.instances).toHaveLength(0);
    expect(result.current.streams).toEqual({});
    expect(result.current.degraded).toBe(false);
  });
});
