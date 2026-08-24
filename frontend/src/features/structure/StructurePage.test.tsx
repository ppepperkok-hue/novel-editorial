import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
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

const volumeNode = {
  id: "n1",
  kind: "volume",
  title: "第一卷",
  parent_id: null,
  sort_order: 1,
  status: "writing",
  draft_id: null,
  created_at: "2026-08-01T00:00:00+00:00",
};

const chapterNode = {
  id: "n2",
  kind: "chapter",
  title: "第一章",
  parent_id: "n1" as string | null,
  sort_order: 1,
  status: "completed",
  draft_id: null,
  created_at: "2026-08-02T00:00:00+00:00",
};

function NavigateButton({ to, label }: { to: string; label: string }) {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(to)}>
      {label}
    </button>
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderStructure(
  fetchMock: ReturnType<typeof vi.fn>,
  initialEntries = ["/works/w-a/structure"],
  navButtons: Array<{ to: string; label: string }> = [],
) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        {navButtons.map((button) => (
          <NavigateButton
            key={button.label}
            to={button.to}
            label={button.label}
          />
        ))}
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function baseRoutes(
  structureBody: unknown[],
  outlineBody: unknown = null,
) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/works/w-a") {
      return Promise.resolve(jsonResponse(workspaceBody));
    }
    if (url === "/works/w-a/structure" && init?.method === "POST") {
      const body = JSON.parse(String(init.body)) as {
        kind: string;
        title: string;
        parent?: string;
      };
      const node = {
        id: `n-${structureBody.length + 1}`,
        kind:
          body.kind === "卷"
            ? "volume"
            : body.kind === "章"
              ? "chapter"
              : "section",
        title: body.title,
        parent_id: body.parent ?? null,
        sort_order: structureBody.length + 1,
        status: "writing",
        draft_id: null,
        created_at: "2026-08-25T10:00:00+00:00",
      };
      structureBody.push(node);
      return Promise.resolve(jsonResponse(node, 201));
    }
    if (url === "/works/w-a/structure") {
      return Promise.resolve(jsonResponse(structureBody));
    }
    if (url === "/works/w-a/outline" && init?.method === "POST") {
      const body = JSON.parse(String(init.body)) as {
        content: string;
        reason?: string;
      };
      const outline = {
        id: "o1",
        workspace_id: "w-a",
        version: outlineBody === null ? 1 : 2,
        content: body.content,
        reason: body.reason ?? null,
        actor: "作者",
        created_at: "2026-08-25T10:00:00+00:00",
      };
      return Promise.resolve(jsonResponse(outline));
    }
    if (url === "/works/w-a/outline") {
      return Promise.resolve(jsonResponse(outlineBody));
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

describe("structure page", () => {
  it("renders the tree with kind labels, progress and the sidebar entry", async () => {
    const fetchMock = baseRoutes([volumeNode, chapterNode]);
    renderStructure(fetchMock);

    await screen.findByText("第一卷");
    expect(screen.getByText("第一章")).toBeInTheDocument();
    expect(screen.getByTestId("structure-progress")).toHaveTextContent(
      "已完成 1/2 节点 · 完成章 1",
    );
    expect(screen.getByRole("link", { name: "结构" })).toHaveAttribute(
      "href",
      "/works/w-a/structure",
    );
    expect(screen.getByTestId("structure-node-n1")).toContainElement(
      screen.getByTestId("structure-node-n2"),
    );
  });

  it("adds a node with a Chinese kind label and refreshes the tree", async () => {
    const structureBody: unknown[] = [volumeNode];
    const fetchMock = baseRoutes(structureBody);
    renderStructure(fetchMock);

    await screen.findByText("第一卷");
    fireEvent.change(screen.getByLabelText("类型"), {
      target: { value: "章" },
    });
    fireEvent.change(screen.getByPlaceholderText("节点标题"), {
      target: { value: "新一章" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));

    await screen.findByText("新一章");
    const createCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === "/works/w-a/structure" && init?.method === "POST",
    );
    expect(createCall).toBeDefined();
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      kind: "章",
      title: "新一章",
    });
  });

  it("filters add-form parents by the selected kind", async () => {
    const fetchMock = baseRoutes([volumeNode, chapterNode]);
    renderStructure(fetchMock);

    await screen.findByText("第一卷");
    const type = screen.getByLabelText("类型");
    const parent = screen.getByLabelText("父节点");

    expect(within(parent).getAllByRole("option")).toHaveLength(1);
    expect(
      within(parent).getByRole("option", { name: "根部" }),
    ).toBeInTheDocument();

    fireEvent.change(type, { target: { value: "章" } });
    expect(
      within(parent).getByRole("option", { name: "卷 · 第一卷" }),
    ).toBeInTheDocument();
    expect(
      within(parent).queryByRole("option", { name: "章 · 第一章" }),
    ).not.toBeInTheDocument();

    fireEvent.change(type, { target: { value: "篇目" } });
    expect(
      within(parent).getByRole("option", { name: "章 · 第一章" }),
    ).toBeInTheDocument();
    expect(
      within(parent).queryByRole("option", { name: "卷 · 第一卷" }),
    ).not.toBeInTheDocument();

    fireEvent.change(type, { target: { value: "章" } });
    fireEvent.change(parent, { target: { value: "n1" } });
    fireEvent.change(type, { target: { value: "卷" } });
    expect(parent).toHaveValue("");
    fireEvent.change(screen.getByPlaceholderText("节点标题"), {
      target: { value: "新卷" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));

    await screen.findByText("新卷");
    const createCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === "/works/w-a/structure" && init?.method === "POST",
    );
    expect(createCall).toBeDefined();
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      kind: "卷",
      title: "新卷",
    });
  });

  it("renames a node via PATCH", async () => {
    const localVolume = { ...volumeNode };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/structure/n1" && init?.method === "PATCH") {
        localVolume.title = JSON.parse(String(init.body)).title as string;
        return Promise.resolve(jsonResponse(localVolume));
      }
      if (url === "/works/w-a/structure") {
        return Promise.resolve(jsonResponse([localVolume, chapterNode]));
      }
      if (url === "/works/w-a/outline") {
        return Promise.resolve(jsonResponse(null));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderStructure(fetchMock);

    await screen.findByText("第一卷");
    const node = screen.getByTestId("structure-node-n1");
    fireEvent.click(
      within(node).getAllByRole("button", { name: "改名" })[0],
    );
    fireEvent.change(screen.getByLabelText("第一卷 新标题"), {
      target: { value: "开篇卷" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await screen.findByText("开篇卷");
    const patch = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === "/works/w-a/structure/n1" && init?.method === "PATCH",
    );
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ title: "开篇卷" });
  });

  it("sets a node status via PATCH with the Chinese label", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/structure/n1" && init?.method === "PATCH") {
        volumeNode.status = "completed";
        return Promise.resolve(jsonResponse(volumeNode));
      }
      if (url === "/works/w-a/structure") {
        return Promise.resolve(jsonResponse([volumeNode, chapterNode]));
      }
      if (url === "/works/w-a/outline") {
        return Promise.resolve(jsonResponse(null));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderStructure(fetchMock);

    await screen.findByText("第一卷");
    fireEvent.change(screen.getByLabelText("第一卷 状态"), {
      target: { value: "completed" },
    });

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            url === "/works/w-a/structure/n1" && init?.method === "PATCH",
        ),
      ).toBe(true);
    });
    const patch = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === "/works/w-a/structure/n1" && init?.method === "PATCH",
    );
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      status: "已完成",
    });
  });

  it("moves a node to the root via POST move", async () => {
    let moveBody: unknown;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/structure/n2/move") {
        moveBody = init?.body;
        chapterNode.parent_id = null;
        return Promise.resolve(jsonResponse(chapterNode));
      }
      if (url === "/works/w-a/structure") {
        return Promise.resolve(jsonResponse([volumeNode, chapterNode]));
      }
      if (url === "/works/w-a/outline") {
        return Promise.resolve(jsonResponse(null));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderStructure(fetchMock);

    await screen.findByText("第一章");
    const node = screen.getByTestId("structure-node-n2");
    fireEvent.click(within(node).getByRole("button", { name: "移动" }));
    fireEvent.change(within(node).getByLabelText("第一章 移动目标"), {
      target: { value: "root" },
    });
    fireEvent.click(within(node).getByRole("button", { name: "确认移动" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          url.toString().endsWith("/structure/n2/move"),
        ),
      ).toBe(true);
    });
    expect(JSON.parse(String(moveBody))).toEqual({ root: true });
  });

  it("filters move parents by the node kind", async () => {
    const sectionNode = {
      id: "n3",
      kind: "section",
      title: "第一篇",
      parent_id: "n2" as string | null,
      sort_order: 1,
      status: "writing",
      draft_id: null,
      created_at: "2026-08-03T00:00:00+00:00",
    };
    const fetchMock = baseRoutes([volumeNode, chapterNode, sectionNode]);
    renderStructure(fetchMock);

    await screen.findByText("第一卷");

    fireEvent.click(
      within(screen.getByTestId("structure-node-n1")).getAllByRole("button", {
        name: "移动",
      })[0],
    );
    const volumeMove = screen.getByLabelText("第一卷 移动目标");
    expect(within(volumeMove).getAllByRole("option")).toHaveLength(1);
    expect(
      within(volumeMove).getByRole("option", { name: "根部" }),
    ).toBeInTheDocument();

    fireEvent.click(
      within(screen.getByTestId("structure-node-n2")).getAllByRole("button", {
        name: "移动",
      })[0],
    );
    const chapterMove = screen.getByLabelText("第一章 移动目标");
    expect(
      within(chapterMove).getByRole("option", { name: "卷 · 第一卷" }),
    ).toBeInTheDocument();
    expect(
      within(chapterMove).queryByRole("option", {
        name: "篇目 · 第一篇",
      }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      within(screen.getByTestId("structure-node-n3")).getByRole("button", {
        name: "移动",
      }),
    );
    const sectionMove = screen.getByLabelText("第一篇 移动目标");
    expect(
      within(sectionMove).getByRole("option", { name: "章 · 第一章" }),
    ).toBeInTheDocument();
    expect(
      within(sectionMove).queryByRole("option", { name: "卷 · 第一卷" }),
    ).not.toBeInTheDocument();
  });

  it("deletes a node after two-step confirmation", async () => {
    const structureBody: unknown[] = [volumeNode, chapterNode];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/structure/n2" && init?.method === "DELETE") {
        structureBody.splice(1, 1);
        return Promise.resolve(jsonResponse({ removed: 1 }));
      }
      if (url === "/works/w-a/structure") {
        return Promise.resolve(jsonResponse(structureBody));
      }
      if (url === "/works/w-a/outline") {
        return Promise.resolve(jsonResponse(null));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderStructure(fetchMock);

    await screen.findByText("第一章");
    const node = screen.getByTestId("structure-node-n2");
    fireEvent.click(within(node).getByRole("button", { name: "删除" }));
    expect(
      within(node).getByRole("button", { name: "确认删除？" }),
    ).toBeInTheDocument();
    fireEvent.click(within(node).getByRole("button", { name: "确认删除？" }));

    await waitFor(() => {
      expect(screen.queryByText("第一章")).not.toBeInTheDocument();
    });
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          url === "/works/w-a/structure/n2" && init?.method === "DELETE",
      ),
    ).toBe(true);
  });

  it("guides outline creation from null and posts without a reason", async () => {
    let outlineBody: unknown = null;
    const fetchMock = baseRoutes([volumeNode], outlineBody);
    fetchMock.mockImplementation(
      (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/works/w-a/outline" && init?.method === "POST") {
          const body = JSON.parse(String(init.body)) as { content: string };
          outlineBody = {
            id: "o1",
            workspace_id: "w-a",
            version: 1,
            content: body.content,
            reason: null,
            actor: "作者",
            created_at: "2026-08-25T10:00:00+00:00",
          };
          return Promise.resolve(jsonResponse(outlineBody, 201));
        }
        if (url === "/works/w-a") {
          return Promise.resolve(jsonResponse(workspaceBody));
        }
        if (url === "/works/w-a/structure") {
          return Promise.resolve(jsonResponse([volumeNode]));
        }
        if (url === "/works/w-a/outline") {
          return Promise.resolve(jsonResponse(outlineBody));
        }
        return Promise.reject(new Error(`未预期的请求：${url}`));
      },
    );
    renderStructure(fetchMock);

    await screen.findByText("还没有大纲");
    fireEvent.change(screen.getByPlaceholderText("大纲正文，支持多行"), {
      target: { value: "三幕结构" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建大纲" }));

    expect(await screen.findByTestId("outline-content")).toHaveTextContent(
      "三幕结构",
    );
    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === "/works/w-a/outline" && init?.method === "POST",
    );
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      content: "三幕结构",
      actor: "作者",
    });
  });

  it("requires a reason when revising the outline", async () => {
    const outlineBody = {
      id: "o1",
      workspace_id: "w-a",
      version: 1,
      content: "三幕结构",
      reason: null,
      actor: "作者",
      created_at: "2026-08-25T10:00:00+00:00",
    };
    const fetchMock = baseRoutes([volumeNode], outlineBody);
    renderStructure(fetchMock);

    expect(await screen.findByText("三幕结构")).toBeInTheDocument();
    const reviseButton = screen.getByRole("button", { name: "保存修订" });
    expect(reviseButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("这次为什么改"), {
      target: { value: "加个尾声" },
    });
    expect(reviseButton).toBeEnabled();
    fireEvent.click(reviseButton);

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            url === "/works/w-a/outline" && init?.method === "POST",
        ),
      ).toBe(true);
    });
    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === "/works/w-a/outline" && init?.method === "POST",
    );
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      content: "三幕结构",
      reason: "加个尾声",
      actor: "作者",
    });
  });

  it("keeps unsaved outline edits when a refetch lands after save", async () => {
    const outlineV1 = {
      id: "o1",
      workspace_id: "w-a",
      version: 1,
      content: "三幕结构",
      reason: null,
      actor: "作者",
      created_at: "2026-08-25T10:00:00+00:00",
    };
    let outlineGetCount = 0;
    let saveStarted = false;
    let resolveSave: (value: Response) => void = () => {};
    let resolveRefetch: (value: Response) => void = () => {};
    const fetchMock = vi.fn(
      (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/works/w-a") {
          return Promise.resolve(jsonResponse(workspaceBody));
        }
        if (url === "/works/w-a/structure") {
          return Promise.resolve(jsonResponse([volumeNode]));
        }
        if (url === "/works/w-a/outline" && init?.method === "POST") {
          saveStarted = true;
          return new Promise<Response>((resolve) => {
            resolveSave = resolve;
          });
        }
        if (url === "/works/w-a/outline") {
          outlineGetCount += 1;
          if (outlineGetCount === 1) {
            return Promise.resolve(jsonResponse(outlineV1));
          }
          return new Promise<Response>((resolve) => {
            resolveRefetch = resolve;
          });
        }
        return Promise.reject(new Error(`未预期的请求：${url}`));
      },
    );
    renderStructure(fetchMock);

    await screen.findByText("三幕结构");
    const textarea = screen.getByPlaceholderText("大纲正文，支持多行");
    fireEvent.change(textarea, { target: { value: "我的手改" } });
    fireEvent.change(screen.getByPlaceholderText("这次为什么改"), {
      target: { value: "补个尾声" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修订" }));

    await waitFor(() => expect(saveStarted).toBe(true));
    await act(async () => {
      resolveSave(
        jsonResponse({
          ...outlineV1,
          version: 2,
          content: "我的手改",
          reason: "补个尾声",
          created_at: "2026-08-25T10:01:00+00:00",
        }),
      );
    });

    fireEvent.change(textarea, { target: { value: "我的手改，继续写" } });
    await waitFor(() => expect(outlineGetCount).toBe(2));
    await act(async () => {
      resolveRefetch(
        jsonResponse({
          ...outlineV1,
          version: 3,
          content: "远端版本",
          created_at: "2026-08-25T10:02:00+00:00",
        }),
      );
    });

    expect(textarea).toHaveValue("我的手改，继续写");
    await waitFor(() =>
      expect(screen.getByTestId("outline-content")).toHaveTextContent(
        "远端版本",
      ),
    );
  });

  it("resets the outline editor when switching workspaces", async () => {
    const outlineA = {
      id: "o1",
      workspace_id: "w-a",
      version: 1,
      content: "甲书大纲",
      reason: null,
      actor: "作者",
      created_at: "2026-08-25T10:00:00+00:00",
    };
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-b") {
        return Promise.resolve(
          jsonResponse({ ...workspaceBody, id: "w-b", title: "乙书" }),
        );
      }
      if (url === "/works/w-a/structure") {
        return Promise.resolve(jsonResponse([volumeNode]));
      }
      if (url === "/works/w-b/structure") {
        return Promise.resolve(jsonResponse([]));
      }
      if (url === "/works/w-a/outline") {
        return Promise.resolve(jsonResponse(outlineA));
      }
      if (url === "/works/w-b/outline") {
        return Promise.resolve(jsonResponse(null));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderStructure(fetchMock, ["/works/w-a/structure"], [
      { to: "/works/w-b/structure", label: "切到乙书" },
      { to: "/works/w-a/structure", label: "切回甲书" },
    ]);

    await screen.findByText("甲书大纲");
    const textarea = screen.getByPlaceholderText("大纲正文，支持多行");
    fireEvent.change(textarea, { target: { value: "手改残留" } });

    fireEvent.click(screen.getByRole("button", { name: "切到乙书" }));
    await screen.findByText("还没有大纲");
    await waitFor(() => expect(textarea).toHaveValue(""));

    fireEvent.click(screen.getByRole("button", { name: "切回甲书" }));
    await waitFor(() => expect(textarea).toHaveValue("甲书大纲"));
  });

  it("shows an error state when the structure list fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/structure") {
        return Promise.reject(new Error("结构读取失败"));
      }
      if (url === "/works/w-a/outline") {
        return Promise.resolve(jsonResponse(null));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderStructure(fetchMock);

    const errorState = await screen.findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/works/w-a/structure");
    expect(errorState).toHaveTextContent("结构读取失败");
  });

  it("keeps the node with an inline error when an add fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/structure" && init?.method === "POST") {
        return Promise.resolve(jsonResponse({ detail: "模拟失败" }, 500));
      }
      if (url === "/works/w-a/structure") {
        return Promise.resolve(jsonResponse([volumeNode]));
      }
      if (url === "/works/w-a/outline") {
        return Promise.resolve(jsonResponse(null));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderStructure(fetchMock);

    await screen.findByText("第一卷");
    fireEvent.change(screen.getByPlaceholderText("节点标题"), {
      target: { value: "失败的一章" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("模拟失败");
    expect(screen.getByText("第一卷")).toBeInTheDocument();
  });
});
