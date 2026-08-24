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
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../../App";

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
    genre: "同人",
    description: "",
    status: "writing",
    created_at: "2026-08-02T00:00:00+00:00",
  },
];

const detailBody = {
  ...worksBody[0],
  band: [
    {
      id: "a1",
      name: "总编",
      role: "editor_in_chief",
      personality: "网感敏锐",
      stance: "留存优先",
      values: "更新稳定",
      aesthetic: "高信息密度",
      emotion_baseline: "稳定",
      mood: "干劲十足",
      work_habits: "盯钩子",
      weaknesses: "铺垫薄",
      relationship_presets: "盯写手",
      private_motive: "带出一本连载",
      created_at: "2026-08-01T00:00:00+00:00",
    },
  ],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderApp(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/works"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("works list page", () => {
  it("shows a skeleton while the list is loading", async () => {
    const fetchMock = vi
      .fn()
      .mockReturnValue(new Promise<Response>(() => undefined));
    renderApp(fetchMock);

    expect(screen.getByTestId("panel-state-loading")).toBeInTheDocument();
  });

  it("guides to creation when there are no works", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    renderApp(fetchMock);

    expect(await screen.findByText("还没有作品")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "创建作品" })).toHaveAttribute(
      "href",
      "/works/new",
    );
  });

  it("shows an inline error and recovers via retry", async () => {
    let failing = true;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works") {
        if (failing) {
          return Promise.reject(new Error("列表读取失败"));
        }
        return Promise.resolve(jsonResponse(worksBody));
      }
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(detailBody));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderApp(fetchMock);

    const errorState = await screen.findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/works");
    expect(errorState).toHaveTextContent("列表读取失败");

    failing = false;
    fireEvent.click(within(errorState).getByRole("button", { name: "重试" }));
    await waitFor(() => {
      expect(screen.getAllByTestId("works-card")).toHaveLength(2);
    });
  });

  it("renders works and opens the detail page on click", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works") {
        return Promise.resolve(jsonResponse(worksBody));
      }
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(detailBody));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderApp(fetchMock);

    await waitFor(() => {
      expect(screen.getAllByTestId("works-card")).toHaveLength(2);
    });
    const [first, second] = screen.getAllByTestId("works-card");
    expect(first).toHaveTextContent("甲书");
    expect(first).toHaveTextContent("网文");
    expect(first).toHaveTextContent("writing");
    expect(second).toHaveTextContent("乙书");

    fireEvent.click(first);
    await screen.findByRole("heading", { name: "甲书" });
    const detailPage = screen.getByTestId("works-detail-page");
    expect(within(detailPage).getByTestId("agent-card")).toHaveTextContent("总编");
  });
});
