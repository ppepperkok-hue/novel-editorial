import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../../App";

const detailBody = {
  id: "w-a",
  title: "甲书",
  genre: "网文",
  description: "一部关于约定的小说",
  status: "writing",
  created_at: "2026-08-01T00:00:00+00:00",
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
    {
      id: "a2",
      name: "审稿",
      role: "reviewer",
      personality: "冷静较真",
      stance: "设定不打架",
      values: "伏笔回收",
      aesthetic: "只看逻辑",
      emotion_baseline: "冷",
      mood: "冷静",
      work_habits: "每十章核对",
      weaknesses: "对爽点容忍低",
      relationship_presets: "与总编互相印证",
      private_motive: "守护不崩的长篇",
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

function renderDetail(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/works/w-a"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("works detail page", () => {
  it("shows a skeleton while the detail is loading", async () => {
    const fetchMock = vi
      .fn()
      .mockReturnValue(new Promise<Response>(() => undefined));
    renderDetail(fetchMock);

    expect(screen.getByTestId("panel-state-loading")).toBeInTheDocument();
  });

  it("shows an inline error for a missing workspace", async () => {
    const fetchMock = vi.fn().mockRejectedValue(
      new Error("请求失败：404 /works/w-a：workspace not found: w-a"),
    );
    renderDetail(fetchMock);

    const errorState = await screen.findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/works/w-a");
    expect(errorState).toHaveTextContent("workspace not found");
  });

  it("renders the workspace overview and full band profiles", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(detailBody));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderDetail(fetchMock);

    await screen.findByRole("heading", { name: "甲书" });
    const detailPage = screen.getByTestId("works-detail-page");
    expect(detailPage).toHaveTextContent("一部关于约定的小说");

    const agents = within(detailPage).getAllByTestId("agent-card");
    expect(agents).toHaveLength(2);
    expect(agents[0]).toHaveTextContent("总编");
    expect(agents[0]).toHaveTextContent("总编");
    expect(agents[0]).toHaveTextContent("网感敏锐");
    expect(agents[0]).toHaveTextContent("留存优先");
    expect(agents[1]).toHaveTextContent("审稿");
    expect(agents[1]).toHaveTextContent("审稿");
    expect(agents[1]).toHaveTextContent("伏笔回收");

    await screen.findByTestId("header-workspace");
    expect(screen.getByTestId("header-workspace")).toHaveTextContent(
      "当前作品：甲书",
    );
  });

  it("guides when the band is empty", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(
          jsonResponse({ ...detailBody, band: [] }),
        );
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderDetail(fetchMock);

    expect(await screen.findByText("班子还没有成员")).toBeInTheDocument();
    expect(screen.queryByTestId("agent-card")).not.toBeInTheDocument();
  });
});
