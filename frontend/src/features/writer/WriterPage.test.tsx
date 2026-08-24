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

const workspaceBody = {
  id: "w-a",
  title: "甲书",
  genre: "网文",
  description: "",
  status: "writing",
  created_at: "2026-08-01T00:00:00+00:00",
  band: [],
};

const draftSummaryV1 = {
  id: "d1",
  title: "第一章",
  status: "draft",
  current_version: 1,
  updated_at: "2026-08-22T10:00:00+00:00",
};

const draftV1Versions = [
  {
    version: 1,
    actor: "写手",
    reason: "initial",
    created_at: "2026-08-22T10:00:00+00:00",
    content: "初版正文\n\n## 第一节",
  },
];

function draftDetailBody(
  versions: unknown[],
  overrides: Record<string, unknown> = {},
) {
  return {
    id: "d1",
    title: "第一章",
    status: "draft",
    current_version: versions.length,
    created_at: "2026-08-22T09:00:00+00:00",
    updated_at: "2026-08-22T10:00:00+00:00",
    versions,
    ...overrides,
  };
}

const reviewsBody = [
  {
    id: "r1",
    role: "agent",
    actor: "责编",
    content: "钩子再亮一点",
    created_at: "2026-08-22T10:30:00+00:00",
  },
];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textResponse(body: string): Response {
  return new Response(body, { headers: { "Content-Type": "text/plain" } });
}

function renderWriter(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/works/w-a/writer"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function writerRoutes(extra: {
  drafts?: unknown;
  detail?: unknown;
  reviews?: unknown;
  diff?: unknown;
} = {}) {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/works/w-a") {
      return Promise.resolve(jsonResponse(workspaceBody));
    }
    if (url === "/works/w-a/drafts") {
      return Promise.resolve(jsonResponse(extra.drafts ?? [draftSummaryV1]));
    }
    if (url === "/works/w-a/drafts/d1") {
      return Promise.resolve(
        jsonResponse(extra.detail ?? draftDetailBody(draftV1Versions)),
      );
    }
    if (url === "/works/w-a/reviews?draft_id=d1") {
      return Promise.resolve(jsonResponse(extra.reviews ?? reviewsBody));
    }
    if (url.startsWith("/works/w-a/drafts/d1/diff?")) {
      if (extra.diff instanceof Error) {
        return Promise.reject(extra.diff);
      }
      if (extra.diff && typeof (extra.diff as { then?: unknown }).then === "function") {
        return extra.diff as Promise<Response>;
      }
      return Promise.resolve(
        textResponse(String(extra.diff ?? "--- v1\n+++ v2\n-旧\n+新")),
      );
    }
    return Promise.reject(new Error(`未预期的请求：${url}`));
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("writer page", () => {
  it("shows a skeleton while drafts are loading", () => {
    const fetchMock = vi
      .fn()
      .mockReturnValue(new Promise<Response>(() => undefined));
    renderWriter(fetchMock);

    expect(
      within(screen.getByTestId("draft-list-panel")).getByTestId(
        "panel-state-loading",
      ),
    ).toBeInTheDocument();
  });

  it("guides when the workspace has no drafts yet", async () => {
    renderWriter(writerRoutes({ drafts: [] }));

    expect(await screen.findByText("还没有草稿")).toBeInTheDocument();
    expect(screen.getByText("先创建一篇草稿")).toBeInTheDocument();
  });

  it("shows an inline error when the draft list fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/drafts") {
        return Promise.reject(new Error("草稿列表读取失败"));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderWriter(fetchMock);

    const errorState = await screen.findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/works/w-a/drafts");
    expect(errorState).toHaveTextContent("草稿列表读取失败");
  });

  it("selects the first draft and shows editor, versions, status and reviews", async () => {
    renderWriter(writerRoutes());

    await screen.findByRole("heading", { name: "第一章" });
    expect(screen.getByTestId("draft-status")).toHaveTextContent(
      "待拍板 · 质量门通过",
    );
    expect(screen.getByTestId("editor-textarea")).toHaveValue(
      "初版正文\n\n## 第一节",
    );
    const versions = within(
      screen.getByTestId("draft-versions-panel"),
    ).getAllByTestId("version-item");
    expect(versions).toHaveLength(1);
    expect(versions[0]).toHaveTextContent("v1");
    expect(versions[0]).toHaveTextContent("写手");
    expect(versions[0]).toHaveTextContent("initial");
    expect(screen.getByTestId("review-list")).toHaveTextContent("钩子再亮一点");
    expect(screen.getByTestId("diff-disabled-hint")).toHaveTextContent(
      "至少需要两个版本",
    );
  });

  it("shows the v0 empty state and disables save for an empty author draft", async () => {
    const emptySummary = {
      id: "d0",
      title: "空稿",
      status: "draft",
      current_version: 0,
      updated_at: "2026-08-22T10:00:00+00:00",
    };
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/drafts") {
        return Promise.resolve(jsonResponse([emptySummary]));
      }
      if (url === "/works/w-a/drafts/d0") {
        return Promise.resolve(
          jsonResponse({
            id: "d0",
            title: "空稿",
            status: "draft",
            current_version: 0,
            created_at: "2026-08-22T09:00:00+00:00",
            updated_at: "2026-08-22T10:00:00+00:00",
            versions: [],
          }),
        );
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderWriter(fetchMock);

    await screen.findByRole("heading", { name: "空稿" });
    expect(screen.getByTestId("draft-empty-v0")).toHaveTextContent("暂无内容");
    expect(screen.getByTestId("draft-status")).toHaveTextContent(
      "空稿（尚无内容）",
    );
    expect(screen.getByTestId("save-content-button")).toBeDisabled();
    expect(screen.getByTestId("revise-button")).toBeDisabled();
    expect(screen.getByTestId("revise-empty-hint")).toHaveTextContent(
      "先保存第一版",
    );
    expect(screen.getByTestId("draft-versions-panel")).toHaveTextContent(
      "暂无版本",
    );
  });

  it("requires a non-blank title for a new author draft and selects it after creation", async () => {
    const created = {
      id: "d9",
      title: "第三章",
      status: "draft",
      current_version: 0,
      updated_at: "2026-08-22T11:00:00+00:00",
      awaiting_decision: true,
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/drafts/new") {
        return Promise.resolve(jsonResponse(created, 201));
      }
      if (url === "/works/w-a/drafts" && init?.method === "POST") {
        return Promise.resolve(jsonResponse(created, 201));
      }
      if (url === "/works/w-a/drafts") {
        return Promise.resolve(jsonResponse([draftSummaryV1]));
      }
      if (url === "/works/w-a/drafts/d9") {
        return Promise.resolve(
          jsonResponse({
            id: "d9",
            title: "第三章",
            status: "draft",
            current_version: 0,
            created_at: "2026-08-22T11:00:00+00:00",
            updated_at: "2026-08-22T11:00:00+00:00",
            versions: [],
          }),
        );
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderWriter(fetchMock);

    await screen.findByText("第一章");
    expect(screen.getByTestId("new-draft-submit")).toBeDisabled();
    fireEvent.change(screen.getByTestId("new-draft-title"), {
      target: { value: "第三章" },
    });
    expect(screen.getByTestId("new-draft-submit")).toBeEnabled();
    fireEvent.click(screen.getByTestId("new-draft-submit"));

    await screen.findByRole("heading", { name: "第三章" });
    expect(screen.getByTestId("draft-empty-v0")).toHaveTextContent("暂无内容");
    await waitFor(() => {
      expect(screen.getByTestId("new-draft-title")).toHaveValue("");
    });
    const posts = fetchMock.mock.calls.filter(
      ([, init]) => init?.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(posts[0][0]).toBe("/works/w-a/drafts/new");
    expect(JSON.parse(posts[0][1]?.body as string)).toEqual({ title: "第三章" });
  });

  it("generates a draft via the LLM with the default title and selects it", async () => {
    const generated = {
      id: "d10",
      title: "未命名章节",
      status: "draft",
      current_version: 1,
      updated_at: "2026-08-22T11:00:00+00:00",
      awaiting_decision: true,
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/drafts" && init?.method === "POST") {
        return Promise.resolve(jsonResponse(generated, 201));
      }
      if (url === "/works/w-a/drafts") {
        return Promise.resolve(jsonResponse([draftSummaryV1]));
      }
      if (url === "/works/w-a/drafts/d10") {
        return Promise.resolve(
          jsonResponse(
            draftDetailBody(
              [
                {
                  version: 1,
                  actor: "写手",
                  reason: "initial",
                  created_at: "2026-08-22T11:00:00+00:00",
                  content: "AI 生成的第一版",
                },
              ],
              { id: "d10", title: "未命名章节" },
            ),
          ),
        );
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderWriter(fetchMock);

    await screen.findByText("第一章");
    fireEvent.click(screen.getByTestId("generate-draft-submit"));

    await screen.findByRole("heading", { name: "未命名章节" });
    expect(screen.getByTestId("editor-textarea")).toHaveValue("AI 生成的第一版");
    const posts = fetchMock.mock.calls.filter(
      ([, init]) => init?.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(posts[0][0]).toBe("/works/w-a/drafts");
    expect(JSON.parse(posts[0][1]?.body as string)).toEqual({
      title: "未命名章节",
    });
  });

  it("saves content with the default reason and refreshes the detail", async () => {
    let versions = [...draftV1Versions];
    let currentVersion = 1;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/drafts") {
        return Promise.resolve(jsonResponse([draftSummaryV1]));
      }
      if (url === "/works/w-a/drafts/d1") {
        return Promise.resolve(
          jsonResponse(
            draftDetailBody(versions, { current_version: currentVersion }),
          ),
        );
      }
      if (url === "/works/w-a/drafts/d1/content" && init?.method === "PUT") {
        const body = JSON.parse(init?.body as string) as {
          content: string;
          reason: string;
        };
        currentVersion += 1;
        versions = [
          ...versions,
          {
            version: currentVersion,
            actor: "作者",
            reason: body.reason,
            created_at: "2026-08-22T12:00:00+00:00",
            content: body.content,
          },
        ];
        return Promise.resolve(
          jsonResponse(
            {
              id: "d1",
              title: "第一章",
              status: "draft",
              current_version: currentVersion,
              updated_at: "2026-08-22T12:00:00+00:00",
              awaiting_decision: true,
            },
            200,
          ),
        );
      }
      if (url === "/works/w-a/reviews?draft_id=d1") {
        return Promise.resolve(jsonResponse(reviewsBody));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderWriter(fetchMock);

    await screen.findByRole("heading", { name: "第一章" });
    const editor = screen.getByTestId("editor-textarea");
    fireEvent.change(editor, {
      target: { value: "新正文：结尾反转" },
    });
    fireEvent.click(screen.getByTestId("save-content-button"));

    const result = await screen.findByTestId("save-result");
    expect(result).toHaveTextContent("已保存 · 质量门通过，等待拍板");
    expect(screen.getByTestId("editor-textarea")).toHaveValue(
      "新正文：结尾反转",
    );
    await waitFor(() => {
      expect(
        within(screen.getByTestId("draft-versions-panel")).getAllByTestId(
          "version-item",
        ),
      ).toHaveLength(2);
    });
    const versionItems = within(
      screen.getByTestId("draft-versions-panel"),
    ).getAllByTestId("version-item");
    expect(versionItems[1]).toHaveTextContent("作者");

    const puts = fetchMock.mock.calls.filter(
      ([, init]) => init?.method === "PUT",
    );
    expect(puts).toHaveLength(1);
    expect(JSON.parse(puts[0][1]?.body as string)).toEqual({
      content: "新正文：结尾反转",
      reason: "作者修改",
    });
  });

  it("sends a custom save reason when one is typed", async () => {
    let versions = [...draftV1Versions];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/drafts") {
        return Promise.resolve(jsonResponse([draftSummaryV1]));
      }
      if (url === "/works/w-a/drafts/d1") {
        return Promise.resolve(
          jsonResponse(draftDetailBody(versions, { current_version: 2 })),
        );
      }
      if (url === "/works/w-a/drafts/d1/content" && init?.method === "PUT") {
        versions = [
          ...versions,
          {
            version: 2,
            actor: "作者",
            reason: "微调结尾",
            created_at: "2026-08-22T12:00:00+00:00",
            content: "微调后的正文",
          },
        ];
        return Promise.resolve(
          jsonResponse({
            id: "d1",
            title: "第一章",
            status: "draft",
            current_version: 2,
            updated_at: "2026-08-22T12:00:00+00:00",
            awaiting_decision: true,
          }),
        );
      }
      if (url === "/works/w-a/reviews?draft_id=d1") {
        return Promise.resolve(jsonResponse([]));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderWriter(fetchMock);

    await screen.findByRole("heading", { name: "第一章" });
    fireEvent.change(screen.getByTestId("editor-textarea"), {
      target: { value: "微调后的正文" },
    });
    fireEvent.change(screen.getByTestId("save-reason-input"), {
      target: { value: "微调结尾" },
    });
    fireEvent.click(screen.getByTestId("save-content-button"));

    await screen.findByTestId("save-result");
    const puts = fetchMock.mock.calls.filter(
      ([, init]) => init?.method === "PUT",
    );
    expect(JSON.parse(puts[0][1]?.body as string)).toEqual({
      content: "微调后的正文",
      reason: "微调结尾",
    });
  });

  it("revises the draft with the typed reason and refreshes the detail", async () => {
    let versions = [...draftV1Versions];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/drafts") {
        return Promise.resolve(jsonResponse([draftSummaryV1]));
      }
      if (url === "/works/w-a/drafts/d1") {
        return Promise.resolve(
          jsonResponse(draftDetailBody(versions, { current_version: 2 })),
        );
      }
      if (url === "/works/w-a/drafts/d1/revise" && init?.method === "POST") {
        versions = [
          ...versions,
          {
            version: 2,
            actor: "写手",
            reason: "按意见重写",
            created_at: "2026-08-22T12:00:00+00:00",
            content: "修订后的正文",
          },
        ];
        return Promise.resolve(
          jsonResponse({
            id: "d1",
            title: "第一章",
            status: "draft",
            current_version: 2,
            updated_at: "2026-08-22T12:00:00+00:00",
            awaiting_decision: true,
          }),
        );
      }
      if (url === "/works/w-a/reviews?draft_id=d1") {
        return Promise.resolve(jsonResponse(reviewsBody));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderWriter(fetchMock);

    await screen.findByRole("heading", { name: "第一章" });
    expect(screen.getByTestId("revise-button")).toBeDisabled();
    fireEvent.change(screen.getByTestId("revise-reason-input"), {
      target: { value: "按意见重写" },
    });
    expect(screen.getByTestId("revise-button")).toBeEnabled();
    fireEvent.click(screen.getByTestId("revise-button"));

    const result = await screen.findByTestId("revise-result");
    expect(result).toHaveTextContent("修订完成 · 质量门通过，等待拍板");
    await waitFor(() => {
      expect(
        within(screen.getByTestId("draft-versions-panel")).getAllByTestId(
          "version-item",
        ),
      ).toHaveLength(2);
    });
    await waitFor(() => {
      expect(screen.getByTestId("editor-textarea")).toHaveValue(
        "修订后的正文",
      );
    });
    const posts = fetchMock.mock.calls.filter(
      ([url, init]) =>
        String(url).endsWith("/revise") && init?.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0][1]?.body as string)).toEqual({
      reason: "按意见重写",
    });
  });

  it("keeps unsaved editor input when a new version arrives from a refresh", async () => {
    let versions = [...draftV1Versions];
    let currentVersion = 1;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/drafts") {
        return Promise.resolve(jsonResponse([draftSummaryV1]));
      }
      if (url === "/works/w-a/drafts/d1") {
        return Promise.resolve(
          jsonResponse(
            draftDetailBody(versions, { current_version: currentVersion }),
          ),
        );
      }
      if (url === "/works/w-a/drafts/d1/revise" && init?.method === "POST") {
        currentVersion = 2;
        versions = [
          ...versions,
          {
            version: 2,
            actor: "写手",
            reason: "按意见重写",
            created_at: "2026-08-22T12:00:00+00:00",
            content: "修订后的正文",
          },
        ];
        return Promise.resolve(
          jsonResponse({
            id: "d1",
            title: "第一章",
            status: "draft",
            current_version: 2,
            updated_at: "2026-08-22T12:00:00+00:00",
            awaiting_decision: true,
          }),
        );
      }
      if (url === "/works/w-a/reviews?draft_id=d1") {
        return Promise.resolve(jsonResponse(reviewsBody));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderWriter(fetchMock);

    await screen.findByRole("heading", { name: "第一章" });
    const editor = screen.getByTestId("editor-textarea");
    fireEvent.change(editor, {
      target: { value: "我的未保存修改" },
    });
    fireEvent.change(screen.getByTestId("revise-reason-input"), {
      target: { value: "按意见重写" },
    });
    fireEvent.click(screen.getByTestId("revise-button"));

    await screen.findByTestId("revise-result");
    await waitFor(() => {
      expect(screen.getByTestId("editor-sync-notice")).toHaveTextContent(
        "检测到新版本",
      );
    });
    expect(screen.getByTestId("editor-textarea")).toHaveValue(
      "我的未保存修改",
    );
  });

  it("toggles between the textarea and the Markdown preview", async () => {
    renderWriter(writerRoutes());

    await screen.findByRole("heading", { name: "第一章" });
    fireEvent.click(screen.getByRole("tab", { name: "预览" }));

    const preview = screen.getByTestId("markdown-preview");
    expect(
      within(preview).getByRole("heading", { name: "第一节" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("editor-textarea")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "编辑" }));
    expect(screen.getByTestId("editor-textarea")).toHaveValue(
      "初版正文\n\n## 第一节",
    );
  });

  it("shows any version's content on demand", async () => {
    const versions = [
      ...draftV1Versions,
      {
        version: 2,
        actor: "作者",
        reason: "作者修改",
        created_at: "2026-08-22T12:00:00+00:00",
        content: "第二版正文\n\n## 第二节",
      },
    ];
    renderWriter(
      writerRoutes({
        detail: draftDetailBody(versions, { current_version: 2 }),
      }),
    );

    await screen.findByRole("heading", { name: "第一章" });
    expect(screen.getByTestId("version-content")).toHaveTextContent("第二节");

    const versionItems = within(
      screen.getByTestId("draft-versions-panel"),
    ).getAllByTestId("version-item");
    fireEvent.click(versionItems[0]);
    expect(screen.getByTestId("version-content")).toHaveTextContent("第一节");
    expect(screen.getByTestId("version-content")).toHaveTextContent(
      "v1 正文 · 写手",
    );
  });

  it("shows an inline error for a failing draft detail", async () => {
    const badSummary = {
      id: "d-bad",
      title: "坏稿",
      status: "draft",
      current_version: 1,
      updated_at: "2026-08-22T10:00:00+00:00",
    };
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/drafts") {
        return Promise.resolve(jsonResponse([badSummary]));
      }
      if (url === "/works/w-a/drafts/d-bad") {
        return Promise.reject(new Error("草稿详情读取失败"));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderWriter(fetchMock);

    const errorState = await screen.findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/works/w-a/drafts/d-bad");
    expect(errorState).toHaveTextContent("草稿详情读取失败");
  });

  it("shows the quality gate result honestly for a failing draft", async () => {
    renderWriter(
      writerRoutes({
        detail: draftDetailBody(draftV1Versions, {
          status: "quality_failed",
        }),
      }),
    );

    await screen.findByRole("heading", { name: "第一章" });
    expect(screen.getByTestId("draft-status")).toHaveTextContent(
      "质量门未通过",
    );
  });

  it("shows the default diff between the latest and previous versions", async () => {
    const versions = [
      ...draftV1Versions,
      {
        version: 2,
        actor: "作者",
        reason: "作者修改",
        created_at: "2026-08-22T12:00:00+00:00",
        content: "第二版正文",
      },
    ];
    const fetchMock = writerRoutes({
      detail: draftDetailBody(versions, { current_version: 2 }),
      diff: "--- v1\n+++ v2\n-旧句\n+新句",
    });
    renderWriter(fetchMock);

    await screen.findByRole("heading", { name: "第一章" });
    const diffOutput = await screen.findByTestId("diff-output");
    expect(diffOutput).toHaveTextContent("-旧句");
    expect(diffOutput).toHaveTextContent("+新句");
    expect(screen.getByTestId("diff-version-a")).toHaveValue("1");
    expect(screen.getByTestId("diff-version-b")).toHaveValue("2");
    const diffCalls = fetchMock.mock.calls.filter(([url]) =>
      String(url).startsWith("/works/w-a/drafts/d1/diff?"),
    );
    expect(diffCalls).toHaveLength(1);
    expect(diffCalls[0][0]).toBe(
      "/works/w-a/drafts/d1/diff?version_a=1&version_b=2",
    );
  });

  it("shows no differences when the server reports identical versions", async () => {
    const versions = [
      ...draftV1Versions,
      {
        version: 2,
        actor: "作者",
        reason: "作者修改",
        created_at: "2026-08-22T12:00:00+00:00",
        content: "初版正文",
      },
    ];
    renderWriter(
      writerRoutes({
        detail: draftDetailBody(versions, { current_version: 2 }),
        diff: "no differences",
      }),
    );

    await screen.findByRole("heading", { name: "第一章" });
    expect(await screen.findByTestId("diff-output")).toHaveTextContent(
      "no differences",
    );
  });

  it("shows an inline error for a failing diff and recovers via retry", async () => {
    const versions = [
      ...draftV1Versions,
      {
        version: 2,
        actor: "作者",
        reason: "作者修改",
        created_at: "2026-08-22T12:00:00+00:00",
        content: "第二版正文",
      },
    ];
    const extra: {
      detail?: unknown;
      diff?: unknown;
    } = {
      detail: draftDetailBody(versions, { current_version: 2 }),
      diff: new Error("差异读取失败"),
    };
    renderWriter(writerRoutes(extra));

    const errorState = await screen.findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/works/w-a/drafts/d1/diff");
    expect(errorState).toHaveTextContent("差异读取失败");

    extra.diff = "--- v1\n+++ v2\n-旧句\n+新句";
    fireEvent.click(within(errorState).getByRole("button", { name: "重试" }));
    expect(await screen.findByTestId("diff-output")).toHaveTextContent(
      "+新句",
    );
  });

  it("refetches the diff when the selected versions change", async () => {
    const versions = [
      ...draftV1Versions,
      {
        version: 2,
        actor: "作者",
        reason: "作者修改",
        created_at: "2026-08-22T12:00:00+00:00",
        content: "第二版正文",
      },
      {
        version: 3,
        actor: "写手",
        reason: "按意见重写",
        created_at: "2026-08-22T13:00:00+00:00",
        content: "第三版正文",
      },
    ];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/drafts") {
        return Promise.resolve(
          jsonResponse([{ ...draftSummaryV1, current_version: 3 }]),
        );
      }
      if (url === "/works/w-a/drafts/d1") {
        return Promise.resolve(
          jsonResponse(draftDetailBody(versions, { current_version: 3 })),
        );
      }
      if (url === "/works/w-a/reviews?draft_id=d1") {
        return Promise.resolve(jsonResponse(reviewsBody));
      }
      if (url.startsWith("/works/w-a/drafts/d1/diff?")) {
        const params = new URLSearchParams(url.split("?")[1]);
        return Promise.resolve(
          textResponse(
            `diff ${params.get("version_a")} -> ${params.get("version_b")}`,
          ),
        );
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderWriter(fetchMock);

    await screen.findByRole("heading", { name: "第一章" });
    expect(await screen.findByTestId("diff-output")).toHaveTextContent(
      "diff 2 -> 3",
    );

    fireEvent.change(screen.getByTestId("diff-version-a"), {
      target: { value: "1" },
    });
    expect(await screen.findByText("diff 1 -> 3")).toBeInTheDocument();
  });
});
