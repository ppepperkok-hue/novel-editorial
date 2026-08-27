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

const workspaceBodyB = {
  id: "w-b",
  title: "乙书",
  genre: "网文",
  description: "",
  status: "writing",
  created_at: "2026-08-02T00:00:00+00:00",
  band: [],
};

const draftsBody = [
  {
    id: "d1",
    title: "第一章",
    status: "draft",
    current_version: 2,
    updated_at: "2026-08-22T10:00:00+00:00",
  },
];

const checkText =
  "score: 8 (threshold 6)\nverdict: pass\nstyle hits: 2/3";
const explainText =
  "第一章 (v2)\n[AI 味定位]\n宛如：3 处\n[改写建议]\n句 1：把「宛如」换成更具体的比喻\n[好句]\n保留：夜风把路灯揉成光斑";
const consistencyText =
  "settings checked: 2 / threads checked: 1\nno consistency issues found";
const driftText =
  "chapters: 3\nbaseline: 第一章\nverdict: stable";
const learnText =
  "samples: 3\navg sentence length: 12.0 字\nsuggested description: 冷峻克制";
const calibrateText =
  "samples: 10\ndistribution: min 3 median 6 p90 8 max 9\nsuggested threshold: 7\napply: quality_threshold = 7\nconfig updated: C:/config.toml";
const feedbackText =
  "samples: 10\nbad: 2 / good: 8\nagreement at threshold 6: 80%";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textResponse(body: string): Response {
  return new Response(body, { headers: { "Content-Type": "text/plain" } });
}

function renderQuality(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/works/w-a/quality"]}>
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
  drafts?: unknown[];
  check?: string;
  explain?: string;
  consistency?: string;
  drift?: string;
  calibrate?: string;
  feedback?: string;
  learn?: string;
} = {}) {
  const {
    drafts = draftsBody,
    check = checkText,
    explain = explainText,
    consistency = consistencyText,
    drift = driftText,
    calibrate = calibrateText,
    feedback = feedbackText,
    learn = learnText,
  } = options;
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/works/w-a") {
      return Promise.resolve(jsonResponse(workspaceBody));
    }
    if (
      url.startsWith("/works/w-a/drafts/d1/quality/check") &&
      init?.method === undefined
    ) {
      return Promise.resolve(textResponse(check));
    }
    if (
      url.startsWith("/works/w-a/drafts/d1/quality/explain") &&
      init?.method === undefined
    ) {
      return Promise.resolve(textResponse(explain));
    }
    if (
      url.startsWith("/works/w-a/drafts/d1/consistency") &&
      init?.method === undefined
    ) {
      return Promise.resolve(textResponse(consistency));
    }
    if (url.startsWith("/works/w-a/drafts")) {
      return Promise.resolve(jsonResponse(drafts));
    }
    if (url.startsWith("/works/w-a/style/drift")) {
      return Promise.resolve(textResponse(drift));
    }
    if (url === "/quality/calibrate" && init?.method === "POST") {
      return Promise.resolve(textResponse(calibrate));
    }
    if (url === "/quality/feedback" && init?.method === "POST") {
      return Promise.resolve(textResponse(feedback));
    }
    if (url.startsWith("/works/w-a/style/learn") && init?.method === "POST") {
      return Promise.resolve(textResponse(learn));
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

describe("quality workbench", () => {
  it("renders the page, sidebar entry, drift report and empty report guidance", async () => {
    const fetchMock = baseRoutes();
    renderQuality(fetchMock);

    expect(await screen.findByTestId("quality-page")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "质量" })).toHaveAttribute(
      "href",
      "/works/w-a/quality",
    );
    expect(await screen.findByTestId("style-drift-report")).toHaveTextContent(
      "verdict: stable",
    );
    expect(screen.getAllByText("先选一篇草稿")).toHaveLength(3);
  });

  it("selecting a draft runs check / explain / consistency and keeps the plain-text format", async () => {
    const fetchMock = baseRoutes();
    renderQuality(fetchMock);

    fireEvent.click(await screen.findByTestId("quality-draft-d1"));

    const checkReport = await screen.findByTestId("quality-check-report");
    expect(checkReport).toHaveTextContent("score: 8 (threshold 6)");
    expect(checkReport).toHaveClass("plain-output");
    expect(screen.getByTestId("quality-explain-report")).toHaveTextContent(
      "把「宛如」换成更具体的比喻",
    );
    expect(screen.getByTestId("quality-explain-report")).toHaveTextContent(
      "保留：夜风把路灯揉成光斑",
    );
    expect(screen.getByTestId("quality-consistency-report")).toHaveTextContent(
      "no consistency issues found",
    );
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).startsWith("/works/w-a/drafts/d1/quality/check"),
      ),
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).startsWith("/works/w-a/drafts/d1/quality/explain"),
      ),
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).startsWith("/works/w-a/drafts/d1/consistency"),
      ),
    ).toBe(true);
  });

  it("learns the style from a local corpus path with the apply flag", async () => {
    const fetchMock = baseRoutes();
    renderQuality(fetchMock);

    const tool = screen.getByTestId("style-learn");
    fireEvent.change(
      within(tool).getByLabelText("文风学习（style learn） 语料路径"),
      { target: { value: "data/refs.txt" } },
    );
    fireEvent.click(
      within(tool).getByLabelText("文风学习（style learn） apply"),
    );
    fireEvent.click(
      within(tool).getByRole("button", { name: "学习并生成描述" }),
    );

    expect(await within(tool).findByTestId("style-learn-report")).toHaveTextContent(
      "suggested description: 冷峻克制",
    );
    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).startsWith("/works/w-a/style/learn") &&
        init?.method === "POST",
    );
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      path: "data/refs.txt",
      apply: true,
    });
  });

  it("calibrates with apply and shows the restart note", async () => {
    const fetchMock = baseRoutes();
    renderQuality(fetchMock);

    const tool = screen.getByTestId("quality-calibrate");
    fireEvent.change(
      within(tool).getByLabelText("语料校准（quality calibrate） 语料路径"),
      { target: { value: "data/corpus.txt" } },
    );
    fireEvent.click(
      within(tool).getByLabelText("语料校准（quality calibrate） apply"),
    );
    fireEvent.click(within(tool).getByRole("button", { name: "运行校准" }));

    expect(await within(tool).findByTestId("quality-calibrate-report")).toHaveTextContent(
      "suggested threshold: 7",
    );
    expect(within(tool).getByTestId("quality-calibrate-apply-note")).toHaveTextContent(
      "重启服务后生效",
    );
    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url) === "/quality/calibrate" && init?.method === "POST",
    );
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      path: "data/corpus.txt",
      apply: true,
    });
  });

  it("analyzes trial-reader feedback with the apply flag", async () => {
    const fetchMock = baseRoutes();
    renderQuality(fetchMock);

    const tool = screen.getByTestId("quality-feedback");
    fireEvent.change(
      within(tool).getByLabelText("试读反馈（quality feedback） 语料路径"),
      { target: { value: "data/feedback.txt" } },
    );
    fireEvent.click(
      within(tool).getByLabelText("试读反馈（quality feedback） apply"),
    );
    fireEvent.click(within(tool).getByRole("button", { name: "分析反馈" }));

    expect(await within(tool).findByTestId("quality-feedback-report")).toHaveTextContent(
      "agreement at threshold 6: 80%",
    );
    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url) === "/quality/feedback" && init?.method === "POST",
    );
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      path: "data/feedback.txt",
      apply: true,
    });
  });

  it("shows an inline error when calibration fails", async () => {
    const fetchMock = vi.fn(
      (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/works/w-a") {
          return Promise.resolve(jsonResponse(workspaceBody));
        }
        if (url.startsWith("/works/w-a/drafts")) {
          return Promise.resolve(jsonResponse(draftsBody));
        }
        if (url.startsWith("/works/w-a/style/drift")) {
          return Promise.resolve(textResponse(driftText));
        }
        if (url === "/quality/calibrate" && init?.method === "POST") {
          return Promise.resolve(jsonResponse({ detail: "语料不存在" }, 422));
        }
        return Promise.reject(new Error(`未预期的请求：${url}`));
      },
    );
    renderQuality(fetchMock);

    const tool = await screen.findByTestId("quality-calibrate");
    fireEvent.change(
      within(tool).getByLabelText("语料校准（quality calibrate） 语料路径"),
      { target: { value: "data/missing.txt" } },
    );
    fireEvent.click(within(tool).getByRole("button", { name: "运行校准" }));

    expect(await within(tool).findByRole("alert")).toHaveTextContent(
      "语料不存在",
    );
  });

  it("shows an error state when the draft list fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/works/w-a") {
        return Promise.resolve(jsonResponse(workspaceBody));
      }
      if (url.startsWith("/works/w-a/drafts")) {
        return Promise.reject(new Error("草稿读取失败"));
      }
      if (url.startsWith("/works/w-a/style/drift")) {
        return Promise.resolve(textResponse(driftText));
      }
      return Promise.reject(new Error(`未预期的请求：${url}`));
    });
    renderQuality(fetchMock);

    const errorState = await screen.findByTestId("panel-state-error");
    expect(errorState).toHaveTextContent("/works/w-a/drafts");
    expect(errorState).toHaveTextContent("草稿读取失败");
  });

  it("shows empty guidance when the workspace has no drafts", async () => {
    const fetchMock = baseRoutes({ drafts: [] });
    renderQuality(fetchMock);

    expect(await screen.findByText("还没有草稿")).toBeInTheDocument();
  });

  it("resets corpus paths and apply flags when switching workspaces", async () => {
    const fetchMock = vi.fn(
      (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/works/w-a") {
          return Promise.resolve(jsonResponse(workspaceBody));
        }
        if (url === "/works/w-b") {
          return Promise.resolve(jsonResponse(workspaceBodyB));
        }
        if (url.startsWith("/works/w-a/drafts")) {
          return Promise.resolve(jsonResponse(draftsBody));
        }
        if (url.startsWith("/works/w-b/drafts")) {
          return Promise.resolve(jsonResponse([]));
        }
        if (url.startsWith("/works/w-a/style/drift")) {
          return Promise.resolve(textResponse(driftText));
        }
        if (url.startsWith("/works/w-b/style/drift")) {
          return Promise.resolve(textResponse(driftText));
        }
        if (
          url.startsWith("/works/w-a/style/learn") &&
          init?.method === "POST"
        ) {
          return Promise.resolve(textResponse(learnText));
        }
        if (url === "/quality/calibrate" && init?.method === "POST") {
          return Promise.resolve(textResponse(calibrateText));
        }
        return Promise.reject(new Error(`未预期的请求：${url}`));
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/works/w-a/quality"]}>
          <App />
          <SwitchWorkspaceButton to="/works/w-b/quality" />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const learnTool = await screen.findByTestId("style-learn");
    fireEvent.change(
      within(learnTool).getByLabelText(
        "文风学习（style learn） 语料路径",
      ),
      { target: { value: "data/refs.txt" } },
    );
    fireEvent.click(
      within(learnTool).getByLabelText("文风学习（style learn） apply"),
    );
    fireEvent.click(
      within(learnTool).getByRole("button", { name: "学习并生成描述" }),
    );
    await within(learnTool).findByTestId("style-learn-report");

    const calibrateTool = screen.getByTestId("quality-calibrate");
    fireEvent.change(
      within(calibrateTool).getByLabelText(
        "语料校准（quality calibrate） 语料路径",
      ),
      { target: { value: "data/corpus.txt" } },
    );
    fireEvent.click(
      within(calibrateTool).getByLabelText(
        "语料校准（quality calibrate） apply",
      ),
    );
    fireEvent.click(
      within(calibrateTool).getByRole("button", { name: "运行校准" }),
    );
    await within(calibrateTool).findByTestId("quality-calibrate-report");
    expect(
      within(calibrateTool).getByTestId("quality-calibrate-apply-note"),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "/works/w-b/quality" }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("quality-page")).toHaveAttribute(
        "data-workspace",
        "w-b",
      );
    });
    const learnAfter = screen.getByTestId("style-learn");
    expect(
      within(learnAfter).getByLabelText(
        "文风学习（style learn） 语料路径",
      ),
    ).toHaveValue("");
    expect(
      within(learnAfter).getByLabelText("文风学习（style learn） apply"),
    ).not.toBeChecked();
    expect(
      within(learnAfter).queryByTestId("style-learn-report"),
    ).not.toBeInTheDocument();

    const calibrateAfter = screen.getByTestId("quality-calibrate");
    expect(
      within(calibrateAfter).getByLabelText(
        "语料校准（quality calibrate） 语料路径",
      ),
    ).toHaveValue("");
    expect(
      within(calibrateAfter).getByLabelText(
        "语料校准（quality calibrate） apply",
      ),
    ).not.toBeChecked();
    expect(
      within(calibrateAfter).queryByTestId("quality-calibrate-report"),
    ).not.toBeInTheDocument();
  });
});
