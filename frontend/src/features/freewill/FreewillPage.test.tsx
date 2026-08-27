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
import { useNavigate } from "react-router-dom";
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

const motivesText =
  "m1 [总编] [ambition] strength=0.8 source=对话 touched=2026-08-28T10:00:00 带出一本连载\nm2 [写手] [pride] strength=0.6 source=写作 touched=2026-08-28T09:00:00 想写出代表作";
const patienceText =
  "[总编] pool=0.8 patience=0.7 consumed=0.1 rejected=0 overridden=0 conflict=0\n  conflict: 写手: 拖稿 (source=讨论)";
const timelineText =
  "2026-08-28T10:00:00 [impression] 总编 -> 写手: 初印象靠谱 | 无 -> 积极 | source=初次讨论";
const behaviorStateText =
  "[总编] state=active\n[写手] state=cooldown";

const workspaceBodyB = {
  id: "w-b",
  title: "乙书",
  genre: "网文",
  description: "",
  status: "writing",
  created_at: "2026-08-02T00:00:00+00:00",
  band: [],
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

function renderFreewill(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/works/w-a/freewill"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function SwitchWorkspaceButton({ to }: { to: string }) {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(to)}>
      {to}
    </button>
  );
}

function baseRoutes(options: {
  motives?: string;
  patience?: string;
  timeline?: string;
  behaviorState?: string;
} = {}) {
  const {
    motives = motivesText,
    patience = patienceText,
    timeline = timelineText,
    behaviorState = behaviorStateText,
  } = options;
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/works/w-a") {
      return Promise.resolve(jsonResponse(workspaceBody));
    }
    if (
      url.startsWith("/works/w-a/motives/") &&
      init?.method === "DELETE"
    ) {
      return Promise.resolve(textResponse("dropped motive m1"));
    }
    if (url.startsWith("/works/w-a/motives")) {
      return Promise.resolve(textResponse(motives));
    }
    if (url.startsWith("/works/w-a/patience")) {
      return Promise.resolve(textResponse(patience));
    }
    if (url.startsWith("/works/w-a/behavior/timeline")) {
      return Promise.resolve(textResponse(timeline));
    }
    if (url.startsWith("/works/w-a/behavior")) {
      return Promise.resolve(textResponse(behaviorState));
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

describe("freewill visualization", () => {
  it("renders the page, sidebar entry, grouped motives and the text reports", async () => {
    const fetchMock = baseRoutes();
    renderFreewill(fetchMock);

    expect(await screen.findByTestId("freewill-page")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "编辑部" })).toHaveAttribute(
      "href",
      "/works/w-a/freewill",
    );
    const groups = await screen.findByTestId("motive-groups");
    expect(within(groups).getByText("总编")).toBeInTheDocument();
    expect(within(groups).getByText("写手")).toBeInTheDocument();
    expect(within(groups).getByText("强度 0.8")).toBeInTheDocument();
    expect(within(groups).getByText("带出一本连载")).toBeInTheDocument();
    expect(screen.getByTestId("patience-report")).toHaveTextContent(
      "pool=0.8",
    );
    expect(screen.getByTestId("behavior-state-report")).toHaveTextContent(
      "state=cooldown",
    );
    expect(screen.getByTestId("timeline-report")).toHaveTextContent(
      "[impression]",
    );
  });

  it("drops a motive after two-step confirmation and refreshes the list", async () => {
    const fetchMock = baseRoutes();
    renderFreewill(fetchMock);

    const motive = await screen.findByTestId("motive-m1");
    fireEvent.click(within(motive).getByRole("button", { name: "弃置" }));
    expect(
      within(motive).getByRole("button", { name: "确认弃置？" }),
    ).toBeInTheDocument();
    fireEvent.click(
      within(motive).getByRole("button", { name: "确认弃置？" }),
    );

    await waitFor(() => {
      const deleteCall = fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url).startsWith("/works/w-a/motives/m1") &&
          init?.method === "DELETE",
      );
      expect(deleteCall).toBe(true);
    });
    await waitFor(() => {
      const motiveCalls = fetchMock.mock.calls.filter(
        ([url]) =>
          String(url).startsWith("/works/w-a/motives") &&
          !String(url).includes("/m1"),
      );
      expect(motiveCalls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("filters the behavior timeline by agent and kind", async () => {
    const fetchMock = baseRoutes();
    renderFreewill(fetchMock);

    await screen.findByTestId("timeline-report");
    const panel = screen.getByTestId("behavior-timeline");
    fireEvent.change(within(panel).getByLabelText("行为伙伴过滤"), {
      target: { value: "总编" },
    });
    fireEvent.click(
      within(panel).getByRole("checkbox", { name: "冲突" }),
    );
    fireEvent.click(
      within(panel).getByRole("button", { name: "应用过滤" }),
    );

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).startsWith(
            "/works/w-a/behavior/timeline?agent=%E6%80%BB%E7%BC%96&kind=conflict",
          ),
        ),
      ).toBe(true);
    });
  });

  it("links to the talk page for discussion and natural-discussion marks", async () => {
    const fetchMock = baseRoutes();
    renderFreewill(fetchMock);

    expect(await screen.findByTestId("talk-entry-link")).toHaveAttribute(
      "href",
      "/works/w-a/talk",
    );
    expect(screen.getByTestId("talk-entry-link")).toHaveTextContent(
      "讨论与自然讨论标记",
    );
  });

  it("shows empty guidance when the workspace has no motives", async () => {
    const fetchMock = baseRoutes({ motives: "no motives yet" });
    renderFreewill(fetchMock);

    expect(await screen.findByText("还没有动机")).toBeInTheDocument();
    expect(screen.queryByTestId("motive-groups")).not.toBeInTheDocument();
  });

  it("shows an error state when motives fail", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url.startsWith("/works/w-a/motives")) {
        return Promise.reject(new Error("动机读取失败"));
      }
      if (url.startsWith("/works/w-a/patience")) {
        return Promise.resolve(textResponse(patienceText));
      }
      if (url.startsWith("/works/w-a/behavior/timeline")) {
        return Promise.resolve(textResponse(timelineText));
      }
      if (url.startsWith("/works/w-a/behavior")) {
        return Promise.resolve(textResponse(behaviorStateText));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderFreewill(fetchMock);

    const errorState = await screen.findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/works/w-a/motives");
    expect(errorState).toHaveTextContent("动机读取失败");
  });

  it("shows an inline error when dropping a motive fails", async () => {
    const fetchMock = vi.fn(
      (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/works/w-a") {
          return Promise.resolve(jsonResponse(workspaceBody));
        }
        if (
          url.startsWith("/works/w-a/motives/") &&
          init?.method === "DELETE"
        ) {
          return Promise.resolve(
            jsonResponse({ detail: "动机不存在" }, 404),
          );
        }
        if (url.startsWith("/works/w-a/motives")) {
          return Promise.resolve(textResponse(motivesText));
        }
        if (url.startsWith("/works/w-a/patience")) {
          return Promise.resolve(textResponse(patienceText));
        }
        if (url.startsWith("/works/w-a/behavior/timeline")) {
          return Promise.resolve(textResponse(timelineText));
        }
        if (url.startsWith("/works/w-a/behavior")) {
          return Promise.resolve(textResponse(behaviorStateText));
        }
        return Promise.reject(new Error(`未预期的请求：${url}`));
      },
    );
    renderFreewill(fetchMock);

    const motive = await screen.findByTestId("motive-m1");
    fireEvent.click(within(motive).getByRole("button", { name: "弃置" }));
    fireEvent.click(
      within(motive).getByRole("button", { name: "确认弃置？" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("动机不存在");
    expect(screen.getByTestId("motive-groups")).toBeInTheDocument();
  });

  it("resets behavior timeline filters when switching workspaces", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url === "/works/w-b") {
        return Promise.resolve(jsonResponse(workspaceBodyB));
      }
      if (url.startsWith("/works/w-a/motives")) {
        return Promise.resolve(textResponse(motivesText));
      }
      if (url.startsWith("/works/w-a/patience")) {
        return Promise.resolve(textResponse(patienceText));
      }
      if (url.startsWith("/works/w-a/behavior/timeline")) {
        return Promise.resolve(textResponse(timelineText));
      }
      if (url.startsWith("/works/w-a/behavior")) {
        return Promise.resolve(textResponse(behaviorStateText));
      }
      if (url.startsWith("/works/w-b/motives")) {
        return Promise.resolve(textResponse("no motives"));
      }
      if (url.startsWith("/works/w-b/patience")) {
        return Promise.resolve(textResponse("[总编] pool=0.5"));
      }
      if (url.startsWith("/works/w-b/behavior/timeline")) {
        // A partner from another work would be rejected by the backend, so a
        // stale filter must never reach the new workspace.
        if (url.includes("agent=") || url.includes("kind=")) {
          return Promise.resolve(jsonResponse({ detail: "伙伴不存在" }, 422));
        }
        return Promise.resolve(textResponse(timelineText));
      }
      if (url.startsWith("/works/w-b/behavior")) {
        return Promise.resolve(textResponse("[总编] state=active"));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/works/w-a/freewill"]}>
          <App />
          <SwitchWorkspaceButton to="/works/w-b/freewill" />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const panel = await screen.findByTestId("behavior-timeline");
    fireEvent.change(within(panel).getByLabelText("行为伙伴过滤"), {
      target: { value: "总编" },
    });
    fireEvent.click(within(panel).getByRole("checkbox", { name: "冲突" }));
    fireEvent.click(within(panel).getByRole("button", { name: "应用过滤" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).startsWith(
            "/works/w-a/behavior/timeline?agent=%E6%80%BB%E7%BC%96",
          ),
        ),
      ).toBe(true);
    });

    fireEvent.click(
      screen.getByRole("button", { name: "/works/w-b/freewill" }),
    );

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url]) => String(url) === "/works/w-b/behavior/timeline",
        ),
      ).toBe(true);
    });
    expect(await screen.findByTestId("timeline-report")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("behavior-timeline")).getByLabelText(
        "行为伙伴过滤",
      ),
    ).toHaveValue("");
    expect(
      within(screen.getByTestId("behavior-timeline")).getByRole("checkbox", {
        name: "冲突",
      }),
    ).not.toBeChecked();
  });
});
