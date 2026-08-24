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

const templatesBody = [
  { name: "网文", description: "节奏快、钩子密" },
  { name: "正统", description: "结构完整、留白克制" },
];

const createdBody = {
  id: "w-new",
  title: "乙书",
  genre: "同人",
  description: "一部短篇",
  status: "writing",
  created_at: "2026-08-25T00:00:00+00:00",
};

const detailBody = {
  ...createdBody,
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
      created_at: "2026-08-25T00:00:00+00:00",
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
      created_at: "2026-08-25T00:00:00+00:00",
    },
  ],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderCreatePage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/works/new"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function createRoutes() {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/templates") {
      return Promise.resolve(jsonResponse(templatesBody));
    }
    if (url === "/works") {
      return Promise.resolve(jsonResponse(createdBody, 201));
    }
    if (url === "/works/w-new") {
      return Promise.resolve(jsonResponse(detailBody));
    }
    return Promise.reject(new Error(`未预期的请求：${url}`));
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("works create page", () => {
  it("renders the form with templates as selectable references", async () => {
    renderCreatePage(createRoutes());

    expect(
      screen.getByRole("heading", { name: "创建作品" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("网文")).toBeInTheDocument();
    expect(screen.getByText("节奏快、钩子密")).toBeInTheDocument();
    expect(screen.getByText("正统")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/网文/));
    expect(screen.getByLabelText(/网文/)).toBeChecked();
    expect(screen.getByLabelText(/不使用模板/)).not.toBeChecked();
  });

  it("shows a template error inline and keeps the form usable", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/templates") {
        return Promise.reject(new Error("模板读取失败"));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderCreatePage(fetchMock);

    const errorState = await screen.findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/templates");
    expect(errorState).toHaveTextContent("模板读取失败");
    expect(screen.getByTestId("works-title-input")).toBeInTheDocument();
  });

  it("disables submit until a title is typed", async () => {
    renderCreatePage(createRoutes());
    await screen.findByText("网文");

    expect(screen.getByTestId("works-submit-button")).toBeDisabled();
    fireEvent.change(screen.getByTestId("works-title-input"), {
      target: { value: "乙书" },
    });
    expect(screen.getByTestId("works-submit-button")).toBeEnabled();
  });

  it("creates the workspace and lands on its detail page with the shell selection set", async () => {
    const fetchMock = createRoutes();
    renderCreatePage(fetchMock);
    await screen.findByText("网文");

    fireEvent.change(screen.getByTestId("works-title-input"), {
      target: { value: "乙书" },
    });
    fireEvent.change(screen.getByLabelText("作品类型"), {
      target: { value: "同人" },
    });
    fireEvent.change(screen.getByLabelText("作品简介"), {
      target: { value: "一部短篇" },
    });
    fireEvent.click(screen.getByTestId("works-submit-button"));

    const detailPage = await screen.findByTestId("works-detail-page");
    await screen.findByRole("heading", { name: "乙书" });
    expect(detailPage).toHaveTextContent("乙书");
    const agents = within(detailPage).getAllByTestId("agent-card");
    expect(agents).toHaveLength(2);
    await waitFor(() => {
      expect(screen.getByTestId("header-workspace")).toHaveTextContent(
        "当前作品：乙书",
      );
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/works",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          title: "乙书",
          genre: "同人",
          description: "一部短篇",
        }),
      }),
    );
  });

  it("renders the full band from the detail fetch when the POST response has no band", async () => {
    let resolveDetail!: (value: Response) => void;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/templates") {
        return Promise.resolve(jsonResponse(templatesBody));
      }
      if (url === "/works") {
        return Promise.resolve(jsonResponse(createdBody, 201));
      }
      if (url === "/works/w-new") {
        return new Promise<Response>((resolve) => {
          resolveDetail = resolve;
        });
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderCreatePage(fetchMock);
    await screen.findByText("网文");

    fireEvent.change(screen.getByTestId("works-title-input"), {
      target: { value: "乙书" },
    });
    fireEvent.click(screen.getByTestId("works-submit-button"));

    const detailPage = await screen.findByTestId("works-detail-page");
    expect(screen.getByTestId("panel-state-loading")).toBeInTheDocument();

    resolveDetail(jsonResponse(detailBody));

    const agents = await within(detailPage).findAllByTestId("agent-card");
    expect(agents).toHaveLength(2);
    expect(agents[0]).toHaveTextContent("总编");
    expect(agents[0]).toHaveTextContent("网感敏锐");
    expect(agents[1]).toHaveTextContent("审稿");
  });

  it("keeps the form and shows an inline error when creation fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/templates") {
        return Promise.resolve(jsonResponse(templatesBody));
      }
      if (url === "/works") {
        return Promise.resolve(jsonResponse({ detail: "模拟创建失败" }, 500));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderCreatePage(fetchMock);
    await screen.findByText("网文");

    fireEvent.change(screen.getByTestId("works-title-input"), {
      target: { value: "乙书" },
    });
    fireEvent.click(screen.getByTestId("works-submit-button"));

    const errorBox = await screen.findByTestId("works-create-error");
    expect(errorBox).toHaveTextContent("模拟创建失败");
    expect(screen.getByTestId("works-title-input")).toHaveValue("乙书");
    expect(screen.getByTestId("works-submit-button")).toBeEnabled();
  });
});
