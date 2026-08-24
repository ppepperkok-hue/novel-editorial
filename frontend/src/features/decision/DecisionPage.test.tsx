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

const pendingDraft = {
  id: "d-a",
  title: "第一章",
  status: "draft",
  current_version: 2,
  updated_at: "2026-08-22T10:00:00+00:00",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderDecisions(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("EventSource", FakeEventSource);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/works/w-a/decisions"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { queryClient, ...utils };
}

function baseRoutes(pendingBody: unknown[], decisionStatus = "accepted") {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/works/w-a") {
      return Promise.resolve(jsonResponse(workspaceBody));
    }
    if (url === "/works/w-a/pending") {
      return Promise.resolve(jsonResponse(pendingBody));
    }
    if (url === "/works/w-a/decisions" && init?.method === "POST") {
      return Promise.resolve(
        jsonResponse({ id: "d-a", status: decisionStatus }, 201),
      );
    }
    return Promise.reject(new Error(`未预期的请求：${url}`));
  });
}

beforeEach(() => {
  FakeEventSource.reset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("decision page", () => {
  it("renders the pending list, the sidebar entry and the live connection status", async () => {
    const fetchMock = baseRoutes([pendingDraft]);
    renderDecisions(fetchMock);

    await screen.findByText("第一章");
    expect(screen.getByTestId("decision-pending-list")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "拍板" })).toHaveAttribute(
      "href",
      "/works/w-a/decisions",
    );

    act(() => {
      FakeEventSource.instances[0].emitOpen();
    });
    expect(screen.getByTestId("event-stream-status")).toHaveTextContent(
      "实时连接：已连接",
    );
  });

  it("accepts a pending draft after two-step confirmation and refreshes the list", async () => {
    const pendingBody: unknown[] = [pendingDraft];
    const fetchMock = baseRoutes(pendingBody);
    renderDecisions(fetchMock);

    await screen.findByText("第一章");
    fireEvent.click(screen.getByRole("button", { name: "接受" }));
    expect(
      screen.getByRole("button", { name: "确认接受？" }),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/works/w-a/decisions",
      expect.anything(),
    );

    pendingBody.length = 0;
    fireEvent.click(screen.getByRole("button", { name: "确认接受？" }));

    await screen.findByText("没有待拍板");
    const posts = fetchMock.mock.calls.filter(
      ([, init]) => init?.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0][1]?.body as string)).toEqual({
      draft_id: "d-a",
      action: "accept",
    });
  });

  it("rejects a pending draft after two-step confirmation", async () => {
    const pendingBody: unknown[] = [pendingDraft];
    const fetchMock = baseRoutes(pendingBody, "rejected");
    renderDecisions(fetchMock);

    await screen.findByText("第一章");
    fireEvent.click(screen.getByRole("button", { name: "拒绝" }));
    pendingBody.length = 0;
    fireEvent.click(screen.getByRole("button", { name: "确认拒绝？" }));

    await screen.findByText("没有待拍板");
    const posts = fetchMock.mock.calls.filter(
      ([, init]) => init?.method === "POST",
    );
    expect(JSON.parse(posts[0][1]?.body as string)).toEqual({
      draft_id: "d-a",
      action: "reject",
    });
  });

  it("keeps the note submit disabled for blank content and posts a trimmed note", async () => {
    const pendingBody: unknown[] = [pendingDraft];
    const fetchMock = baseRoutes(pendingBody);
    renderDecisions(fetchMock);

    await screen.findByText("第一章");
    fireEvent.click(screen.getByRole("button", { name: "指示" }));
    const noteInput = screen.getByLabelText("拍板指示内容");
    expect(screen.getByRole("button", { name: "提交指示" })).toBeDisabled();

    fireEvent.change(noteInput, { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "提交指示" })).toBeDisabled();

    fireEvent.change(noteInput, { target: { value: "方向没问题" } });
    expect(screen.getByRole("button", { name: "提交指示" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "提交指示" }));
    expect(
      screen.getByRole("button", { name: "确认提交？" }),
    ).toBeInTheDocument();

    pendingBody.length = 0;
    fireEvent.click(screen.getByRole("button", { name: "确认提交？" }));

    await screen.findByText("没有待拍板");
    const posts = fetchMock.mock.calls.filter(
      ([, init]) => init?.method === "POST",
    );
    expect(JSON.parse(posts[0][1]?.body as string)).toEqual({
      draft_id: "d-a",
      action: "note",
      content: "方向没问题",
    });
  });

  it("shows an inline error and keeps the item when the decision fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/pending") {
        return Promise.resolve(jsonResponse([pendingDraft]));
      }
      if (url === "/works/w-a/decisions" && init?.method === "POST") {
        return Promise.resolve(jsonResponse({ detail: "模拟失败" }, 500));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderDecisions(fetchMock);

    await screen.findByText("第一章");
    fireEvent.click(screen.getByRole("button", { name: "接受" }));
    fireEvent.click(screen.getByRole("button", { name: "确认接受？" }));

    await waitFor(() => {
      expect(screen.getByTestId("pending-error")).toHaveTextContent("模拟失败");
    });
    expect(screen.getByText("第一章")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "接受" })).toBeInTheDocument();
  });

  it("shows empty guidance when nothing is pending", async () => {
    renderDecisions(baseRoutes([]));

    expect(await screen.findByText("没有待拍板")).toBeInTheDocument();
  });

  it("shows an error state when the pending list fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-a/pending") {
        return Promise.reject(new Error("待拍板读取失败"));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderDecisions(fetchMock);

    const errorState = await screen.findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/works/w-a/pending");
    expect(errorState).toHaveTextContent("待拍板读取失败");
  });

  it("shows a newly pending draft when an SSE event arrives", async () => {
    const pendingBody: unknown[] = [];
    const fetchMock = baseRoutes(pendingBody);
    renderDecisions(fetchMock);

    await screen.findByText("没有待拍板");
    act(() => {
      pendingBody.push(pendingDraft);
      FakeEventSource.instances[0].emitMessage("{}");
    });

    expect(await screen.findByText("第一章")).toBeInTheDocument();
    expect(within(screen.getByTestId("decision-pending-list")).getByRole(
      "button",
      { name: "接受" },
    )).toBeInTheDocument();
  });
});
