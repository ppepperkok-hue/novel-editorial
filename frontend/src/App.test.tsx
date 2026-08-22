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
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textResponse(body: string): Response {
  return new Response(body, { headers: { "Content-Type": "text/plain" } });
}

type RouteBody = unknown;

function mockFetchRoutes(routes: Record<string, RouteBody>): void {
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
      if (typeof body === "string") {
        return Promise.resolve(textResponse(body));
      }
      return Promise.resolve(jsonResponse(body));
    }
    return Promise.reject(new Error(`未预期的请求：${url}`));
  });
  vi.stubGlobal("fetch", fetchMock);
}

const overviewBody = {
  overviews: [
    {
      workspace_id: "w-a",
      title: "甲书",
      genre: "网文",
      status: "writing",
      pending_count: 1,
      structure: "1/3 章",
      last_activity: "2026-08-22T10:00:00+00:00",
      created_at: "2026-08-01T00:00:00+00:00",
    },
    {
      workspace_id: "w-b",
      title: "乙书",
      genre: "短篇",
      status: "writing",
      pending_count: 1,
      structure: "0/1 章",
      last_activity: "2026-08-22T09:00:00+00:00",
      created_at: "2026-08-02T00:00:00+00:00",
    },
  ],
  total: 2,
  skipped: 0,
};

const eventsBody = {
  events: [
    {
      id: "e2",
      workspace_id: "w-b",
      type: "decision.requested",
      time: "2026-08-22T10:05:00+00:00",
      actor: "系统",
      payload: { draft_id: "d-b", version: 1 },
    },
    {
      id: "e1",
      workspace_id: "w-a",
      type: "draft.created",
      time: "2026-08-22T10:00:00+00:00",
      actor: "写手",
      payload: { draft_id: "d-a" },
    },
  ],
  skipped: 0,
};

const pendingABody = [
  {
    id: "d-a",
    title: "第一章",
    status: "draft",
    current_version: 1,
    updated_at: "2026-08-22T10:00:00+00:00",
  },
];

const pendingBBody = [
  {
    id: "d-b",
    title: "第二章",
    status: "draft",
    current_version: 1,
    updated_at: "2026-08-22T10:05:00+00:00",
  },
];

function fullRoutes(): Record<string, RouteBody> {
  return {
    "/config": { panel_poll_interval: 3 },
    "/overview": overviewBody,
    "/events": eventsBody,
    "/works/w-a/pending": pendingABody,
    "/works/w-b/pending": pendingBBody,
    "/works/w-a/drafts/d-a": {
      id: "d-a",
      title: "第一章",
      status: "draft",
      current_version: 1,
      created_at: "2026-08-01T00:00:00+00:00",
      updated_at: "2026-08-22T10:00:00+00:00",
      versions: [
        {
          version: 1,
          reason: "initial",
          created_at: "2026-08-01T00:00:00+00:00",
          content: "初版正文",
        },
      ],
    },
    "/works/w-a/drafts": [pendingABody[0]],
    "/works/w-a/reviews?draft_id=d-a": [
      {
        id: "r1",
        role: "agent",
        actor: "责编",
        content: "钩子再亮一点",
        created_at: "2026-08-22T09:00:00+00:00",
      },
    ],
    "/works/w-a/inspect": "[风格]\n冷峻克制\n[版本]\n初版正文",
    "/works/w-a/log": "作品：《甲书》\n== 草稿 ==\n第一章",
    "/works/w-a/style": { description: "冷峻克制", forbidden_words: "宛如" },
    "/works/w-a/structure": [
      {
        id: "n1",
        kind: "volume",
        title: "第一卷",
        parent_id: null,
        sort_order: 1,
        status: "writing",
        draft_id: null,
        created_at: "2026-08-01T00:00:00+00:00",
      },
    ],
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App three-window panel", () => {
  it("renders overview cards with status, pending count, progress and activity", async () => {
    mockFetchRoutes(fullRoutes());
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByTestId("workspace-card")).toHaveLength(2);
    });
    const [first, second] = screen.getAllByTestId("workspace-card");
    expect(first).toHaveTextContent("甲书");
    expect(first).toHaveTextContent("状态：writing");
    expect(first).toHaveTextContent("待拍板：1");
    expect(first).toHaveTextContent("进度：1/3 章");
    expect(first).toHaveTextContent("最近活动：");
    expect(second).toHaveTextContent("乙书");
  });

  it("renders events newest first and clicking one opens that workspace", async () => {
    mockFetchRoutes(fullRoutes());
    render(<App />);

    const eventsPanel = screen.getByTestId("panel-events");
    await waitFor(() => {
      expect(within(eventsPanel).getAllByTestId("event-item-button")).toHaveLength(
        2,
      );
    });
    const buttons = within(eventsPanel).getAllByTestId("event-item-button");
    expect(buttons[0]).toHaveTextContent("待拍板");
    expect(buttons[1]).toHaveTextContent("新草稿");

    fireEvent.click(buttons[0]);
    const drawer = await screen.findByTestId("workspace-drawer");
    expect(within(drawer).getByRole("heading", { name: "乙书" })).toBeInTheDocument();
  });

  it("aggregates pending drafts across workspaces", async () => {
    mockFetchRoutes(fullRoutes());
    render(<App />);

    const pendingPanel = screen.getByTestId("panel-pending");
    expect(await within(pendingPanel).findByText("第一章")).toBeInTheDocument();
    expect(within(pendingPanel).getByText("第二章")).toBeInTheDocument();
    expect(within(pendingPanel).getByText("甲书")).toBeInTheDocument();
    expect(within(pendingPanel).getByText("乙书")).toBeInTheDocument();
  });

  it("drills from an overview card into every drawer layer", async () => {
    mockFetchRoutes(fullRoutes());
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByTestId("workspace-card")).toHaveLength(2);
    });
    fireEvent.click(screen.getAllByTestId("workspace-card")[0]);
    const drawer = await screen.findByTestId("workspace-drawer");
    expect(within(drawer).getByRole("heading", { name: "甲书" })).toBeInTheDocument();

    fireEvent.change(within(drawer).getByLabelText("检索关键词"), {
      target: { value: "冷峻" },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "检索" }));
    expect(await within(drawer).findByTestId("inspect-result")).toHaveTextContent(
      "[风格]",
    );

    fireEvent.click(within(drawer).getByRole("tab", { name: "草稿与版本" }));
    expect(await within(drawer).findByTestId("draft-list")).toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole("button", { name: /第一章/ }));
    expect(await within(drawer).findByTestId("draft-versions")).toHaveTextContent(
      "初版正文",
    );

    fireEvent.click(within(drawer).getByRole("tab", { name: "意见" }));
    expect(await within(drawer).findByTestId("review-list")).toHaveTextContent(
      "钩子再亮一点",
    );

    fireEvent.click(within(drawer).getByRole("tab", { name: "日志" }));
    expect(await within(drawer).findByTestId("workspace-log")).toHaveTextContent(
      "作品：《甲书》",
    );

    fireEvent.click(within(drawer).getByRole("tab", { name: "设定·结构·风格" }));
    expect(await within(drawer).findByTestId("workspace-style")).toHaveTextContent(
      "冷峻克制",
    );
    expect(await within(drawer).findByTestId("structure-list")).toHaveTextContent(
      "第一卷",
    );
  });

  it("shows skeletons while loading and content once resolved", async () => {
    let resolveOverview: ((value: Response) => void) | undefined;
    const overviewPromise = new Promise<Response>((resolve) => {
      resolveOverview = resolve;
    });
    mockFetchRoutes({
      "/config": { panel_poll_interval: 3 },
      "/overview": overviewPromise,
      "/events": eventsBody,
      "/works/w-a/pending": pendingABody,
      "/works/w-b/pending": pendingBBody,
    });
    render(<App />);

    const overviewPanel = screen.getByTestId("panel-overview");
    expect(
      within(overviewPanel).getByTestId("panel-state-loading"),
    ).toBeInTheDocument();

    await act(async () => {
      resolveOverview?.(jsonResponse(overviewBody));
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(screen.getAllByTestId("workspace-card")).toHaveLength(2);
    });
  });

  it("shows empty guidance when every window has no data", async () => {
    mockFetchRoutes({
      "/config": { panel_poll_interval: 3 },
      "/overview": { overviews: [], total: 0, skipped: 0 },
      "/events": { events: [], skipped: 0 },
    });
    render(<App />);

    expect(await screen.findByText("还没有作品")).toBeInTheDocument();
    expect(screen.getByText("暂无事件")).toBeInTheDocument();
    expect(screen.getByText("没有待拍板")).toBeInTheDocument();
  });

  it("shows an error state with source path and recovers via retry", async () => {
    let failing = true;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/config") {
        return Promise.resolve(jsonResponse({ panel_poll_interval: 3 }));
      }
      if (url === "/overview") {
        return Promise.resolve(jsonResponse(overviewBody));
      }
      if (url.startsWith("/works/")) {
        return Promise.resolve(jsonResponse([]));
      }
      if (url === "/events") {
        if (failing) {
          return Promise.reject(new Error("网络断了"));
        }
        return Promise.resolve(jsonResponse(eventsBody));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    const eventsPanel = screen.getByTestId("panel-events");
    const errorState = await within(eventsPanel).findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/events");
    expect(errorState).toHaveTextContent("网络断了");

    failing = false;
    fireEvent.click(within(errorState).getByRole("button", { name: "重试" }));
    await waitFor(() => {
      expect(within(eventsPanel).getAllByTestId("event-item-button")).toHaveLength(
        2,
      );
    });
  });

  it("accepts a pending draft after two-step confirmation and refreshes every window", async () => {
    let overviewCalls = 0;
    let eventsCalls = 0;
    let pendingCalls = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/config") {
        return Promise.resolve(jsonResponse({ panel_poll_interval: 3 }));
      }
      if (url === "/overview") {
        overviewCalls += 1;
        return Promise.resolve(jsonResponse(overviewBody));
      }
      if (url === "/events") {
        eventsCalls += 1;
        return Promise.resolve(jsonResponse(eventsBody));
      }
      if (url === "/works/w-a/pending") {
        pendingCalls += 1;
        return Promise.resolve(jsonResponse(pendingCalls === 1 ? pendingABody : []));
      }
      if (url === "/works/w-b/pending") {
        return Promise.resolve(jsonResponse([]));
      }
      if (url === "/works/w-a/decisions") {
        return Promise.resolve(
          jsonResponse({ id: "d-a", status: "accepted" }, 201),
        );
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    const pendingPanel = screen.getByTestId("panel-pending");
    await waitFor(() => {
      expect(within(pendingPanel).getByText("第一章")).toBeInTheDocument();
    });

    fireEvent.click(within(pendingPanel).getByRole("button", { name: "接受" }));
    expect(
      within(pendingPanel).getByRole("button", { name: "确认接受？" }),
    ).toBeInTheDocument();
    fireEvent.click(
      within(pendingPanel).getByRole("button", { name: "确认接受？" }),
    );

    await waitFor(() => {
      expect(within(pendingPanel).getByText("没有待拍板")).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/works/w-a/decisions",
      expect.objectContaining({ method: "POST" }),
    );
    expect(overviewCalls).toBeGreaterThanOrEqual(2);
    expect(eventsCalls).toBeGreaterThanOrEqual(2);
  });

  it("keeps the pending item with an inline error when the decision fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/config") {
        return Promise.resolve(jsonResponse({ panel_poll_interval: 3 }));
      }
      if (url === "/overview") {
        return Promise.resolve(jsonResponse(overviewBody));
      }
      if (url === "/events") {
        return Promise.resolve(jsonResponse(eventsBody));
      }
      if (url === "/works/w-a/pending") {
        return Promise.resolve(jsonResponse(pendingABody));
      }
      if (url === "/works/w-b/pending") {
        return Promise.resolve(jsonResponse(pendingBBody));
      }
      if (url === "/works/w-a/decisions") {
        return Promise.resolve(jsonResponse({ detail: "模拟失败" }, 500));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    const pendingPanel = screen.getByTestId("panel-pending");
    await waitFor(() => {
      expect(within(pendingPanel).getAllByTestId("pending-item")).toHaveLength(2);
    });
    fireEvent.click(within(pendingPanel).getAllByRole("button", { name: "接受" })[0]);
    fireEvent.click(within(pendingPanel).getByRole("button", { name: "确认接受？" }));

    await waitFor(() => {
      expect(within(pendingPanel).getByTestId("pending-error")).toHaveTextContent(
        "模拟失败",
      );
    });
    expect(within(pendingPanel).getByText("第一章")).toBeInTheDocument();
    expect(within(pendingPanel).getAllByTestId("pending-item")).toHaveLength(2);
    expect(
      within(pendingPanel).getAllByRole("button", { name: "接受" }),
    ).toHaveLength(2);
  });

  it("resets the drawer tab and selection when switching workspaces", async () => {
    const urls: string[] = [];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      urls.push(url);
      if (url === "/config") {
        return Promise.resolve(jsonResponse({ panel_poll_interval: 3 }));
      }
      if (url === "/overview") {
        return Promise.resolve(jsonResponse(overviewBody));
      }
      if (url === "/events") {
        return Promise.resolve(jsonResponse(eventsBody));
      }
      if (url === "/works/w-a/pending") {
        return Promise.resolve(jsonResponse(pendingABody));
      }
      if (url === "/works/w-b/pending") {
        return Promise.resolve(jsonResponse(pendingBBody));
      }
      if (url === "/works/w-a/drafts") {
        return Promise.resolve(jsonResponse([pendingABody[0]]));
      }
      if (url === "/works/w-a/drafts/d-a") {
        return Promise.resolve(
          jsonResponse({
            id: "d-a",
            title: "第一章",
            status: "draft",
            current_version: 1,
            created_at: "2026-08-01T00:00:00+00:00",
            updated_at: "2026-08-22T10:00:00+00:00",
            versions: [
              {
                version: 1,
                reason: "initial",
                created_at: "2026-08-01T00:00:00+00:00",
                content: "初版正文",
              },
            ],
          }),
        );
      }
      if (url === "/works/w-b/drafts") {
        return Promise.resolve(jsonResponse([]));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByTestId("workspace-card")).toHaveLength(2);
    });
    fireEvent.click(screen.getAllByTestId("workspace-card")[0]);
    let drawer = await screen.findByTestId("workspace-drawer");
    fireEvent.click(within(drawer).getByRole("tab", { name: "草稿与版本" }));
    await waitFor(() => {
      expect(within(drawer).getByTestId("draft-list")).toBeInTheDocument();
    });
    fireEvent.click(within(drawer).getByRole("button", { name: /第一章/ }));
    await waitFor(() => {
      expect(within(drawer).getByTestId("draft-versions")).toHaveTextContent(
        "初版正文",
      );
    });

    fireEvent.click(within(drawer).getByRole("button", { name: "关闭抽屉" }));
    fireEvent.click(screen.getAllByTestId("workspace-card")[1]);
    drawer = await screen.findByTestId("workspace-drawer");

    expect(within(drawer).getByRole("heading", { name: "乙书" })).toBeInTheDocument();
    expect(within(drawer).getByRole("tab", { name: "检索" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(
      within(drawer).getByRole("tab", { name: "草稿与版本" }),
    ).toHaveAttribute("aria-selected", "false");
    expect(urls.some((url) => url.startsWith("/works/w-b/drafts/d-"))).toBe(false);
  });

  it("does not render stale draft versions while the next draft is loading", async () => {
    const draftTwoPending = new Promise<Response>(() => undefined);
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/config") {
        return Promise.resolve(jsonResponse({ panel_poll_interval: 3 }));
      }
      if (url === "/overview") {
        return Promise.resolve(jsonResponse(overviewBody));
      }
      if (url === "/events") {
        return Promise.resolve(jsonResponse(eventsBody));
      }
      if (url === "/works/w-a/pending" || url === "/works/w-b/pending") {
        return Promise.resolve(jsonResponse([]));
      }
      if (url === "/works/w-a/drafts") {
        return Promise.resolve(
          jsonResponse([
            pendingABody[0],
            {
              id: "d-a2",
              title: "第二章",
              status: "draft",
              current_version: 1,
              updated_at: "2026-08-22T11:00:00+00:00",
            },
          ]),
        );
      }
      if (url === "/works/w-a/drafts/d-a") {
        return Promise.resolve(
          jsonResponse({
            id: "d-a",
            title: "第一章",
            status: "draft",
            current_version: 1,
            created_at: "2026-08-01T00:00:00+00:00",
            updated_at: "2026-08-22T10:00:00+00:00",
            versions: [
              {
                version: 1,
                reason: "initial",
                created_at: "2026-08-01T00:00:00+00:00",
                content: "初版正文",
              },
            ],
          }),
        );
      }
      if (url === "/works/w-a/drafts/d-a2") {
        return draftTwoPending;
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByTestId("workspace-card")).toHaveLength(2);
    });
    fireEvent.click(screen.getAllByTestId("workspace-card")[0]);
    const drawer = await screen.findByTestId("workspace-drawer");
    fireEvent.click(within(drawer).getByRole("tab", { name: "草稿与版本" }));
    fireEvent.click(within(drawer).getByRole("button", { name: /第一章/ }));
    expect(await within(drawer).findByTestId("draft-versions")).toHaveTextContent(
      "初版正文",
    );

    fireEvent.click(within(drawer).getByRole("button", { name: /第二章/ }));
    await waitFor(() => {
      expect(
        within(drawer).getByRole("button", { name: /第二章/ }),
      ).toHaveClass("draft-list-item--selected");
    });
    expect(within(drawer).queryByTestId("draft-versions")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("初版正文")).not.toBeInTheDocument();
  });

  it("shows the draft error and no stale versions when switching to a failing draft", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/config") {
        return Promise.resolve(jsonResponse({ panel_poll_interval: 3 }));
      }
      if (url === "/overview") {
        return Promise.resolve(jsonResponse(overviewBody));
      }
      if (url === "/events") {
        return Promise.resolve(jsonResponse(eventsBody));
      }
      if (url === "/works/w-a/pending" || url === "/works/w-b/pending") {
        return Promise.resolve(jsonResponse([]));
      }
      if (url === "/works/w-a/drafts") {
        return Promise.resolve(
          jsonResponse([
            pendingABody[0],
            {
              id: "d-a2",
              title: "第二章",
              status: "draft",
              current_version: 1,
              updated_at: "2026-08-22T11:00:00+00:00",
            },
          ]),
        );
      }
      if (url === "/works/w-a/drafts/d-a") {
        return Promise.resolve(
          jsonResponse({
            id: "d-a",
            title: "第一章",
            status: "draft",
            current_version: 1,
            created_at: "2026-08-01T00:00:00+00:00",
            updated_at: "2026-08-22T10:00:00+00:00",
            versions: [
              {
                version: 1,
                reason: "initial",
                created_at: "2026-08-01T00:00:00+00:00",
                content: "初版正文",
              },
            ],
          }),
        );
      }
      if (url === "/works/w-a/drafts/d-a2") {
        return Promise.reject(new Error("草稿详情读取失败"));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByTestId("workspace-card")).toHaveLength(2);
    });
    fireEvent.click(screen.getAllByTestId("workspace-card")[0]);
    const drawer = await screen.findByTestId("workspace-drawer");
    fireEvent.click(within(drawer).getByRole("tab", { name: "草稿与版本" }));
    fireEvent.click(within(drawer).getByRole("button", { name: /第一章/ }));
    expect(await within(drawer).findByTestId("draft-versions")).toHaveTextContent(
      "初版正文",
    );

    fireEvent.click(within(drawer).getByRole("button", { name: /第二章/ }));
    const errorState = await within(drawer).findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/works/w-a/drafts/d-a2");
    expect(errorState).toHaveTextContent("草稿详情读取失败");
    expect(within(drawer).queryByTestId("draft-versions")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("初版正文")).not.toBeInTheDocument();
  });
});
