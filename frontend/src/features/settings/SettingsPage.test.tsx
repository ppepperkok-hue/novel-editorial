import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../../App";

const workspaceBody = {
  id: "w-a",
  title: "甲书",
  genre: "网文",
  description: "",
  status: "writing",
  created_at: "2026-08-01T00:00:00+00:00",
  band: [],
};

const settingEntry = {
  id: "s1",
  kind: "character",
  name: "林晚",
  content: "怕黑，酒量差",
  source: "作者",
  current_version: 1,
  created_at: "2026-08-01T00:00:00+00:00",
  updated_at: "2026-08-01T00:00:00+00:00",
};

const inspirationItem = {
  id: "i1",
  workspace_id: "w-a",
  kind: "灵感",
  content: "雨夜路灯下的伞",
  source: "散步",
  created_at: "2026-08-23T10:00:00+00:00",
  updated_at: "2026-08-23T10:00:00+00:00",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textResponse(body: string): Response {
  return new Response(body, { headers: { "Content-Type": "text/plain" } });
}

function renderSettings(
  fetchMock: ReturnType<typeof vi.fn>,
  initialEntries = ["/works/w-a/settings"],
) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function baseRoutes(
  settingsBody: unknown[],
  inspirationsBody: unknown[],
) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/works/w-a") {
      return Promise.resolve(jsonResponse(workspaceBody));
    }
    if (url.startsWith("/works/w-a/settings/check")) {
      return Promise.resolve(
        textResponse("settings: 2 entries (1 revised)；同名冲突：无"),
      );
    }
    if (
      url.startsWith("/works/w-a/settings/s1") &&
      init?.method === undefined
    ) {
      return Promise.resolve(jsonResponse(settingEntry));
    }
    if (url.startsWith("/works/w-a/settings") && init?.method === "POST") {
      const body = JSON.parse(String(init.body)) as {
        kind?: string;
        name?: string;
        content: string;
        setting_id?: string;
        reason?: string;
      };
      const entry = {
        id: body.setting_id ?? "s-new",
        kind: body.setting_id ? "character" : "world",
        name: body.name ?? "林晚",
        content: body.content,
        source: "作者",
        current_version: body.setting_id ? 2 : 1,
        created_at: "2026-08-25T10:00:00+00:00",
        updated_at: "2026-08-25T10:00:00+00:00",
      };
      settingsBody.push(entry);
      return Promise.resolve(
        jsonResponse(entry, body.setting_id ? 200 : 201),
      );
    }
    if (url.startsWith("/works/w-a/settings")) {
      return Promise.resolve(jsonResponse(settingsBody));
    }
    if (
      url.startsWith("/works/w-a/inspirations/i1") &&
      init?.method === undefined
    ) {
      return Promise.resolve(jsonResponse(inspirationItem));
    }
    if (
      url.startsWith("/works/w-a/inspirations/") &&
      init?.method === "DELETE"
    ) {
      inspirationsBody.splice(0, 1);
      return Promise.resolve(jsonResponse({ id: "i1", kind: "灵感" }));
    }
    if (
      url.startsWith("/works/w-a/inspirations") &&
      init?.method === "POST"
    ) {
      const body = JSON.parse(String(init.body)) as {
        content: string;
        kind: string;
        source: string;
      };
      const item = {
        id: "i-new",
        workspace_id: "w-a",
        kind: body.kind,
        content: body.content,
        source: body.source,
        created_at: "2026-08-25T10:00:00+00:00",
        updated_at: "2026-08-25T10:00:00+00:00",
      };
      inspirationsBody.push(item);
      return Promise.resolve(jsonResponse(item, 201));
    }
    if (url.startsWith("/works/w-a/inspirations")) {
      return Promise.resolve(jsonResponse(inspirationsBody));
    }
    if (url.startsWith("/works/w-a/inspect")) {
      return Promise.resolve(textResponse("[设定]\n林晚：怕黑\n[灵感]\n伞"));
    }
    return Promise.reject(new Error(`未预期的请求：${url}`));
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("settings page", () => {
  it("renders settings, inspirations, the sidebar entry and kind labels", async () => {
    const fetchMock = baseRoutes([settingEntry], []);
    renderSettings(fetchMock);

    await screen.findByText("林晚");
    expect(
      within(screen.getByTestId("setting-list")).getByText("人物"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "设定" })).toHaveAttribute(
      "href",
      "/works/w-a/settings",
    );
    expect(screen.getByTestId("inspirations-panel")).toHaveTextContent(
      "还没有灵感素材",
    );
  });

  it("filters settings by the Chinese kind label", async () => {
    const fetchMock = baseRoutes([settingEntry], []);
    renderSettings(fetchMock);

    await screen.findByText("林晚");
    const settingsPanel = screen.getByTestId("settings-panel");
    fireEvent.change(
      within(settingsPanel).getByLabelText("按类型过滤"),
      { target: { value: "人物" } },
    );

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).startsWith("/works/w-a/settings?kind="),
        ),
      ).toBe(true);
    });
  });

  it("adds a setting with kind label, name and content", async () => {
    const settingsBody: unknown[] = [settingEntry];
    const fetchMock = baseRoutes(settingsBody, []);
    renderSettings(fetchMock);

    await screen.findByText("林晚");
    const settingsPanel = screen.getByTestId("settings-panel");
    fireEvent.change(
      within(settingsPanel).getByPlaceholderText("条目名称"),
      { target: { value: "灵潮" } },
    );
    fireEvent.change(
      within(settingsPanel).getByPlaceholderText("设定正文"),
      { target: { value: "灵气如潮汐" } },
    );
    fireEvent.click(within(settingsPanel).getByRole("button", { name: "新增" }));

    await screen.findByText("灵潮");
    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).startsWith("/works/w-a/settings") &&
        init?.method === "POST",
    );
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      kind: "人物",
      name: "灵潮",
      content: "灵气如潮汐",
      source: "作者",
      actor: "作者",
    });
  });

  it("opens one setting detail and shows its content", async () => {
    const fetchMock = baseRoutes([settingEntry], []);
    renderSettings(fetchMock);

    fireEvent.click(await screen.findByTestId("setting-item-s1"));
    expect(
      await within(screen.getByTestId("setting-detail")).findByText(
        "怕黑，酒量差",
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId("setting-detail")).toHaveTextContent("来源：作者");
  });

  it("revises a setting with setting_id and reason", async () => {
    const settingsBody: unknown[] = [settingEntry];
    const fetchMock = baseRoutes(settingsBody, []);
    renderSettings(fetchMock);

    fireEvent.click(await screen.findByTestId("setting-item-s1"));
    fireEvent.click(
      await screen.findByRole("button", { name: "修订此条" }),
    );
    fireEvent.change(screen.getByPlaceholderText("这次为什么改"), {
      target: { value: "情节需要" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修订" }));

    await waitFor(() => {
      const posts = fetchMock.mock.calls.filter(
        ([url, init]) =>
          String(url).startsWith("/works/w-a/settings") &&
          init?.method === "POST",
      );
      expect(posts.length).toBeGreaterThan(0);
    });
    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).startsWith("/works/w-a/settings") &&
        init?.method === "POST",
    );
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      setting_id: "s1",
      content: "怕黑，酒量差",
      reason: "情节需要",
      source: "作者",
      actor: "作者",
    });
  });

  it("runs the check report and shows the plain-text result", async () => {
    const fetchMock = baseRoutes([settingEntry], []);
    renderSettings(fetchMock);

    await screen.findByText("林晚");
    fireEvent.click(screen.getByRole("button", { name: "运行检查" }));

    expect(await screen.findByTestId("settings-check-report")).toHaveTextContent(
      "settings: 2 entries (1 revised)",
    );
  });

  it("adds an inspiration and shows it in the list", async () => {
    const inspirationsBody: unknown[] = [];
    const fetchMock = baseRoutes([], inspirationsBody);
    renderSettings(fetchMock);

    await screen.findByText("还没有灵感素材");
    const panel = screen.getByTestId("inspirations-panel");
    fireEvent.change(
      within(panel).getByPlaceholderText("一句画面、一个点子…"),
      { target: { value: "旧城墙上的一根烟" } },
    );
    fireEvent.click(within(panel).getByRole("button", { name: "新增" }));

    expect(await screen.findByText("旧城墙上的一根烟")).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).startsWith("/works/w-a/inspirations") &&
        init?.method === "POST",
    );
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      content: "旧城墙上的一根烟",
      kind: "灵感",
      source: "",
    });
  });

  it("opens one inspiration detail", async () => {
    const fetchMock = baseRoutes([], [inspirationItem]);
    renderSettings(fetchMock);

    fireEvent.click(await screen.findByTestId("inspiration-item-i1"));
    expect(
      await within(screen.getByTestId("inspiration-detail")).findByText(
        "雨夜路灯下的伞",
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId("inspiration-detail")).toHaveTextContent(
      "来源：散步",
    );
  });

  it("deletes an inspiration after two-step confirmation", async () => {
    const inspirationsBody: unknown[] = [inspirationItem];
    const fetchMock = baseRoutes([], inspirationsBody);
    renderSettings(fetchMock);

    await screen.findByText("雨夜路灯下的伞");
    const panel = screen.getByTestId("inspirations-panel");
    fireEvent.click(
      within(panel).getByRole("button", { name: "删除" }),
    );
    expect(
      within(panel).getByRole("button", { name: "确认删除？" }),
    ).toBeInTheDocument();
    fireEvent.click(
      within(panel).getByRole("button", { name: "确认删除？" }),
    );

    await waitFor(() => {
      expect(screen.queryByText("雨夜路灯下的伞")).not.toBeInTheDocument();
    });
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url).startsWith("/works/w-a/inspirations/i1") &&
          init?.method === "DELETE",
      ),
    ).toBe(true);
  });

  it("runs the inspect search and shows plain text", async () => {
    const fetchMock = baseRoutes([], []);
    renderSettings(fetchMock);

    await screen.findByText("还没有灵感素材");
    fireEvent.change(screen.getByLabelText("检索关键词"), {
      target: { value: "怕黑" },
    });
    fireEvent.click(screen.getByRole("button", { name: "检索" }));

    expect(await screen.findByTestId("inspect-result")).toHaveTextContent(
      "林晚：怕黑",
    );
    expect(fetchMock.mock.calls.some(([url]) =>
      String(url).startsWith("/works/w-a/inspect?keyword="),
    )).toBe(true);
  });

  it("shows an inline error when adding a setting fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url.startsWith("/works/w-a/settings") && init?.method === "POST") {
        return Promise.resolve(jsonResponse({ detail: "模拟失败" }, 500));
      }
      if (url.startsWith("/works/w-a/settings")) {
        return Promise.resolve(jsonResponse([settingEntry]));
      }
      if (url.startsWith("/works/w-a/inspirations")) {
        return Promise.resolve(jsonResponse([]));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderSettings(fetchMock);

    await screen.findByText("林晚");
    const settingsPanel = screen.getByTestId("settings-panel");
    fireEvent.change(
      within(settingsPanel).getByPlaceholderText("条目名称"),
      { target: { value: "灵潮" } },
    );
    fireEvent.change(
      within(settingsPanel).getByPlaceholderText("设定正文"),
      { target: { value: "灵气如潮汐" } },
    );
    fireEvent.click(within(settingsPanel).getByRole("button", { name: "新增" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("模拟失败");
    expect(screen.getByText("林晚")).toBeInTheDocument();
  });

  it("shows an error state when the settings list fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url.startsWith("/works/w-a/settings")) {
        return Promise.reject(new Error("设定读取失败"));
      }
      if (url.startsWith("/works/w-a/inspirations")) {
        return Promise.resolve(jsonResponse([]));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderSettings(fetchMock);

    const errorState = await screen.findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/works/w-a/settings");
    expect(errorState).toHaveTextContent("设定读取失败");
  });
});
