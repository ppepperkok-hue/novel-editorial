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
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../../App";
import { FakeEventSource } from "../../test/fakeEventSource";

const workspaceBody = {
  id: "w-a",
  title: "甲书",
  genre: "网文",
  description: "",
  status: "writing",
  created_at: "2026-08-01T00:00:00+00:00",
  band: [],
};

const plainAuthor = {
  id: "m1",
  role: "author",
  actor: "作者",
  content: "这章钩子不够，谁来想想",
  payload: {},
  created_at: "2026-08-22T10:00:00+00:00",
  mark: null,
  line: "[author] 作者: 这章钩子不够，谁来想想",
};

const disagreementAgent = {
  id: "m2",
  role: "agent",
  actor: "责编",
  content: "我先加个反转钩子",
  payload: { disagreement: { mark: "开篇节奏" } },
  created_at: "2026-08-22T10:01:00+00:00",
  mark: "agent·分歧·开篇节奏",
  line: "[agent·分歧·开篇节奏] 责编: 我先加个反转钩子",
};

const discussionAgent = {
  id: "m3",
  role: "agent",
  actor: "审稿",
  content: "设定前后要一致",
  payload: { discussion: { mark: "设定细节" } },
  created_at: "2026-08-22T10:02:00+00:00",
  mark: "审稿·讨论·设定细节",
  line: "[审稿·讨论·设定细节] 审稿: 设定前后要一致",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderTalk(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/works/w-a/talk"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function baseRoutes(talkBody: unknown) {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/works/w-a") {
      return Promise.resolve(jsonResponse(workspaceBody));
    }
    if (url === "/works/w-a/talk") {
      return Promise.resolve(jsonResponse(talkBody));
    }
    return Promise.reject(new Error(`未预期的请求：${url}`));
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("talk page", () => {
  beforeEach(() => {
    FakeEventSource.reset();
  });

  it("shows a skeleton while the conversation is loading", () => {
    const fetchMock = vi
      .fn()
      .mockReturnValue(new Promise<Response>(() => undefined));
    renderTalk(fetchMock);

    expect(screen.getByTestId("panel-state-loading")).toBeInTheDocument();
  });

  it("shows an inline error with a retry that recovers", async () => {
    let failing = true;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/talk") {
        if (failing) {
          return Promise.reject(new Error("对话读取失败"));
        }
        return Promise.resolve(jsonResponse([plainAuthor]));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderTalk(fetchMock);

    const errorState = await screen.findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/works/w-a/talk");
    expect(errorState).toHaveTextContent("对话读取失败");

    failing = false;
    fireEvent.click(within(errorState).getByRole("button", { name: "重试" }));
    expect(await screen.findByText("这章钩子不够，谁来想想")).toBeInTheDocument();
  });

  it("guides with an empty state and keeps send disabled until text is typed", async () => {
    renderTalk(baseRoutes([]));

    expect(await screen.findByText("还没有对话")).toBeInTheDocument();
    expect(screen.getByTestId("talk-send-button")).toBeDisabled();

    const input = screen.getByTestId("talk-message-input");
    fireEvent.change(input, { target: { value: "   " } });
    expect(screen.getByTestId("talk-send-button")).toBeDisabled();

    fireEvent.change(input, { target: { value: "大家辛苦了" } });
    expect(screen.getByTestId("talk-send-button")).toBeEnabled();
  });

  it("renders author, agent and system messages with visible marks", async () => {
    const system = {
      id: "m4",
      role: "system",
      actor: "系统",
      content: "新章已生成",
      payload: {},
      created_at: "2026-08-22T10:03:00+00:00",
      mark: null,
      line: "[system] 系统: 新章已生成",
    };
    renderTalk(baseRoutes([plainAuthor, disagreementAgent, discussionAgent, system]));

    const items = await screen.findAllByTestId("talk-item");
    expect(items).toHaveLength(4);
    expect(items[0]).toHaveClass("talk-item--author");
    expect(items[0]).toHaveTextContent("作者");
    expect(items[1]).toHaveClass("talk-item--agent");
    expect(items[2]).toHaveClass("talk-item--agent");
    expect(items[3]).toHaveClass("talk-item--system");

    const marks = screen.getAllByTestId("talk-mark");
    expect(marks).toHaveLength(2);
    expect(marks[0]).toHaveTextContent("agent·分歧·开篇节奏");
    expect(marks[0]).toHaveClass("talk-mark--disagreement");
    expect(marks[1]).toHaveTextContent("审稿·讨论·设定细节");
    expect(marks[1]).toHaveClass("talk-mark--discussion");
  });

  it("sends a message, clears the input and refreshes the conversation", async () => {
    const talkBody: unknown[] = [plainAuthor];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/talk" && init?.method === "POST") {
        return Promise.resolve(
          jsonResponse(
            {
              messages: [
                {
                  id: "m9",
                  role: "author",
                  actor: "作者",
                  content: "把结局改圆一点",
                  payload: {},
                  created_at: "2026-08-22T11:00:00+00:00",
                },
              ],
            },
            201,
          ),
        );
      }
      if (url === "/works/w-a/talk") {
        return Promise.resolve(
          jsonResponse([
            ...talkBody,
            {
              id: "m9",
              role: "author",
              actor: "作者",
              content: "把结局改圆一点",
              payload: {},
              created_at: "2026-08-22T11:00:00+00:00",
              mark: null,
              line: "[author] 作者: 把结局改圆一点",
            },
          ]),
        );
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderTalk(fetchMock);

    const input = screen.getByTestId("talk-message-input");
    await screen.findByText("这章钩子不够，谁来想想");
    fireEvent.change(input, { target: { value: "把结局改圆一点" } });
    fireEvent.click(screen.getByTestId("talk-send-button"));

    expect(await screen.findByText("把结局改圆一点")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("talk-message-input")).toHaveValue("");
    });
    const posts = fetchMock.mock.calls.filter(
      ([, init]) => init?.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0][1]?.body as string)).toEqual({
      message: "把结局改圆一点",
    });
  });

  it("keeps the typed message and shows an inline error when sending fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/talk" && init?.method === "POST") {
        return Promise.resolve(jsonResponse({ detail: "模拟发送失败" }, 500));
      }
      if (url === "/works/w-a/talk") {
        return Promise.resolve(jsonResponse([]));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderTalk(fetchMock);

    const input = screen.getByTestId("talk-message-input");
    await screen.findByText("还没有对话");
    fireEvent.change(input, { target: { value: "发不出去的话" } });
    fireEvent.click(screen.getByTestId("talk-send-button"));

    const errorBox = await screen.findByTestId("talk-send-error");
    expect(errorBox).toHaveTextContent("模拟发送失败");
    expect(screen.getByTestId("talk-message-input")).toHaveValue("发不出去的话");
    expect(screen.getByTestId("talk-send-button")).toBeEnabled();
  });

  it("shows the workspace context in the shell once the workspace resolves", async () => {
    renderTalk(baseRoutes([plainAuthor]));

    await waitFor(() => {
      expect(screen.getByTestId("header-workspace")).toHaveTextContent(
        "当前作品：甲书",
      );
    });
    const talkLink = screen.getByRole("link", { name: "对话" });
    expect(talkLink).toHaveAttribute("href", "/works/w-a/talk");
    expect(screen.getByRole("link", { name: "写作" })).toHaveAttribute(
      "href",
      "/works/w-a/writer",
    );
  });

  it("refreshes the conversation when a new message arrives over SSE", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const talkBody: unknown[] = [plainAuthor];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/talk") {
        return Promise.resolve(jsonResponse(talkBody));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderTalk(fetchMock);

    await screen.findByText("这章钩子不够，谁来想想");
    act(() => {
      talkBody.push(disagreementAgent);
      FakeEventSource.instances[0].emitMessage("{}");
    });

    expect(await screen.findByText("我先加个反转钩子")).toBeInTheDocument();
    const items = screen.getAllByTestId("talk-item");
    expect(items).toHaveLength(2);
  });
});
