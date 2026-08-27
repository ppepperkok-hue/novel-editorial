import "@testing-library/jest-dom/vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OverviewPage from "./OverviewPage";
import { FakeEventSource } from "../../test/fakeEventSource";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetchRoutes(routes: Record<string, unknown>): void {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    for (const [prefix, body] of Object.entries(routes)) {
      if (!url.startsWith(prefix)) {
        continue;
      }
      if (body instanceof Error) {
        return Promise.reject(body);
      }
      if (body && typeof (body as { then?: unknown }).then === "function") {
        return body as Promise<Response>;
      }
      return Promise.resolve(jsonResponse(body));
    }
    return Promise.reject(new Error(`未预期的请求：${url}`));
  });
  vi.stubGlobal("fetch", fetchMock);
}

const worksBody = [
  {
    id: "w-a",
    title: "甲书",
    genre: "网文",
    description: "",
    status: "writing",
    created_at: "2026-08-01T00:00:00+00:00",
  },
  {
    id: "w-b",
    title: "乙书",
    genre: "短篇",
    description: "",
    status: "writing",
    created_at: "2026-08-02T00:00:00+00:00",
  },
];

const overviewBody = {
  overviews: [
    {
      workspace_id: "w-a",
      title: "甲书",
      genre: "网文",
      status: "writing",
      pending_count: 0,
      structure: "1/3 章",
      last_activity: "2026-08-22T10:00:00+00:00",
      created_at: "2026-08-01T00:00:00+00:00",
    },
    {
      workspace_id: "w-b",
      title: "乙书",
      genre: "短篇",
      status: "writing",
      pending_count: 0,
      structure: "0/1 章",
      last_activity: "2026-08-22T09:00:00+00:00",
      created_at: "2026-08-02T00:00:00+00:00",
    },
  ],
  total: 2,
  skipped: 0,
};

function baseRoutes(): Record<string, unknown> {
  return {
    "/config": { panel_poll_interval: 3 },
    "/overview": overviewBody,
    "/works/w-a/pending": [],
    "/works/w-b/pending": [],
    "/works": worksBody,
  };
}

function eventBody(
  id: string,
  workspaceId: string,
  type: string,
  actor: string,
  time: string,
) {
  return {
    id,
    workspace_id: workspaceId,
    type,
    time,
    actor,
    payload: {},
  };
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
  FakeEventSource.reset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("OverviewPage realtime events window", () => {
  it("merges events from every workspace newest-first and dedupes by id", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    mockFetchRoutes(baseRoutes());
    render(<OverviewPage />);

    await waitFor(() => {
      expect(FakeEventSource.instances).toHaveLength(2);
    });
    act(() => {
      instanceFor("w-a").emitOpen();
      instanceFor("w-b").emitOpen();
    });

    // Out-of-order arrivals: older event first, newer second, then a duplicate.
    act(() => {
      instanceFor("w-a").emitMessage(
        JSON.stringify(
          eventBody("e1", "w-a", "draft.created", "写手", "2026-08-27T10:00:00+00:00"),
        ),
      );
    });
    act(() => {
      instanceFor("w-b").emitMessage(
        JSON.stringify(
          eventBody("e2", "w-b", "decision.requested", "系统", "2026-08-27T10:05:00+00:00"),
        ),
      );
    });
    act(() => {
      instanceFor("w-a").emitMessage(
        JSON.stringify(
          eventBody("e1", "w-a", "draft.created", "写手", "2026-08-27T10:00:00+00:00"),
        ),
      );
    });

    const eventsPanel = screen.getByTestId("panel-events");
    const buttons = within(eventsPanel).getAllByTestId("event-item-button");
    expect(buttons).toHaveLength(2);
    expect(buttons[0]).toHaveTextContent("待拍板");
    expect(buttons[1]).toHaveTextContent("新草稿");
    expect(within(eventsPanel).getByTestId("event-stream-status")).toHaveTextContent(
      "2/2 部作品已连接",
    );
  });

  it("shows a reconnect notice when a live stream drops", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    mockFetchRoutes(baseRoutes());
    render(<OverviewPage />);

    await waitFor(() => {
      expect(FakeEventSource.instances).toHaveLength(2);
    });
    act(() => {
      instanceFor("w-a").emitOpen();
      instanceFor("w-b").emitOpen();
    });
    act(() => {
      instanceFor("w-a").emitError();
    });

    const eventsPanel = screen.getByTestId("panel-events");
    expect(within(eventsPanel).getByTestId("event-stream-status")).toHaveTextContent(
      "自动重连",
    );
    expect(within(eventsPanel).getByTestId("event-stream-status")).toHaveClass(
      "event-stream-status--reconnecting",
    );
  });

  it("falls back to global polling when EventSource is unavailable", async () => {
    mockFetchRoutes({
      ...baseRoutes(),
      "/events": {
        events: [
          eventBody("e1", "w-a", "draft.created", "写手", "2026-08-27T10:00:00+00:00"),
        ],
        skipped: 1,
      },
    });
    render(<OverviewPage />);

    const eventsPanel = screen.getByTestId("panel-events");
    await waitFor(() => {
      expect(within(eventsPanel).getAllByTestId("event-item-button")).toHaveLength(1);
    });
    expect(within(eventsPanel).getByTestId("event-stream-status")).toHaveTextContent(
      "轮询",
    );
    expect(within(eventsPanel).getByText("有 1 部作品的事件读取失败（已跳过）")).toBeInTheDocument();
  });

  it("shows the loading skeleton while the workspace list is pending", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    mockFetchRoutes({
      "/config": { panel_poll_interval: 3 },
      "/overview": overviewBody,
      "/works": new Promise<Response>(() => undefined),
    });
    render(<OverviewPage />);

    const eventsPanel = screen.getByTestId("panel-events");
    expect(within(eventsPanel).getByTestId("panel-state-loading")).toBeInTheDocument();
  });

  it("shows empty guidance when there are no events", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    mockFetchRoutes({
      ...baseRoutes(),
      "/works": [],
    });
    render(<OverviewPage />);

    const eventsPanel = screen.getByTestId("panel-events");
    expect(await within(eventsPanel).findByText("暂无事件")).toBeInTheDocument();
    expect(within(eventsPanel).queryByTestId("event-item-button")).not.toBeInTheDocument();
  });

  it("shows an error with the source path when the workspace list fails", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    mockFetchRoutes({
      "/config": { panel_poll_interval: 3 },
      "/overview": overviewBody,
      "/works": new Error("作品列表读取失败"),
    });
    render(<OverviewPage />);

    const eventsPanel = screen.getByTestId("panel-events");
    const errorState = await within(eventsPanel).findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/works");
    expect(errorState).toHaveTextContent("作品列表读取失败");
  });

  it("keeps live events visible when a /works poll transiently fails", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    let worksFailureCount = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/config") {
        return Promise.resolve(jsonResponse({ panel_poll_interval: 0.05 }));
      }
      if (url === "/overview") {
        return Promise.resolve(jsonResponse(overviewBody));
      }
      if (url === "/works") {
        if (worksFailureCount > 0) {
          worksFailureCount += 1;
          return Promise.reject(new Error("作品列表瞬时失败"));
        }
        return Promise.resolve(jsonResponse(worksBody));
      }
      if (url === "/works/w-a/pending" || url === "/works/w-b/pending") {
        return Promise.resolve(jsonResponse([]));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<OverviewPage />);

    await waitFor(() => {
      expect(FakeEventSource.instances).toHaveLength(2);
    });
    act(() => {
      instanceFor("w-a").emitOpen();
      instanceFor("w-b").emitOpen();
      instanceFor("w-a").emitMessage(
        JSON.stringify(
          eventBody("e1", "w-a", "draft.created", "写手", "2026-08-27T10:00:00+00:00"),
        ),
      );
    });

    const eventsPanel = screen.getByTestId("panel-events");
    expect(within(eventsPanel).getAllByTestId("event-item-button")).toHaveLength(1);

    // Let the next /works poll fail once the feed already has live events.
    worksFailureCount = 1;
    await waitFor(() => {
      expect(worksFailureCount).toBeGreaterThan(1);
    });
    expect(within(eventsPanel).getAllByTestId("event-item-button")).toHaveLength(1);
    expect(within(eventsPanel).queryByTestId("panel-state-error")).not.toBeInTheDocument();
    expect(within(eventsPanel).getByTestId("event-stream-status")).toHaveTextContent(
      "2/2 部作品已连接",
    );
  });

  it("shows an error and recovers via retry when fallback polling fails", async () => {
    let failing = true;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/config") {
        return Promise.resolve(jsonResponse({ panel_poll_interval: 3 }));
      }
      if (url === "/overview") {
        return Promise.resolve(jsonResponse(overviewBody));
      }
      if (url === "/works") {
        return Promise.resolve(jsonResponse(worksBody));
      }
      if (url === "/works/w-a/pending" || url === "/works/w-b/pending") {
        return Promise.resolve(jsonResponse([]));
      }
      if (url === "/events") {
        if (failing) {
          return Promise.reject(new Error("网络断了"));
        }
        return Promise.resolve(
          jsonResponse({
            events: [
              eventBody("e1", "w-a", "draft.created", "写手", "2026-08-27T10:00:00+00:00"),
            ],
            skipped: 0,
          }),
        );
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<OverviewPage />);

    const eventsPanel = screen.getByTestId("panel-events");
    const errorState = await within(eventsPanel).findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/events");
    expect(errorState).toHaveTextContent("网络断了");

    failing = false;
    fireEvent.click(within(errorState).getByRole("button", { name: "重试" }));
    await waitFor(() => {
      expect(within(eventsPanel).getAllByTestId("event-item-button")).toHaveLength(1);
    });
  });

  it("keeps the drill-down drawer and pending aggregation working", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    mockFetchRoutes({
      ...baseRoutes(),
      "/works/w-a/pending": [
        {
          id: "d-a",
          title: "第一章",
          status: "draft",
          current_version: 1,
          updated_at: "2026-08-27T10:00:00+00:00",
        },
      ],
    });
    render(<OverviewPage />);

    const pendingPanel = screen.getByTestId("panel-pending");
    expect(await within(pendingPanel).findByText("第一章")).toBeInTheDocument();

    await waitFor(() => {
      expect(FakeEventSource.instances).toHaveLength(2);
    });
    act(() => {
      instanceFor("w-a").emitOpen();
      instanceFor("w-b").emitOpen();
      instanceFor("w-a").emitMessage(
        JSON.stringify(
          eventBody("e1", "w-a", "draft.created", "写手", "2026-08-27T10:00:00+00:00"),
        ),
      );
    });

    const eventsPanel = screen.getByTestId("panel-events");
    fireEvent.click(within(eventsPanel).getByTestId("event-item-button"));
    expect(await screen.findByTestId("workspace-drawer")).toHaveTextContent("甲书");
  });
});
