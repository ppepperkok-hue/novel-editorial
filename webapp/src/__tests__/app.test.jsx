import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App.jsx";

const dashboard = {
  updated_at: "2026-08-10 00:00:00",
  cost_budget: 100,
  summary: {
    novels: 1,
    chapters_total: 2,
    chapters_published: 1,
    chapters_ready: 0,
    chapters_draft: 1,
    quality_total: 2,
    quality_passed: 2,
    publish_failed: 0,
    monthly_cost: 0,
  },
  novels: [],
  chapters: [],
  publish_logs: [],
  health: { issues: [], log_tail: [] },
  reader_stats: { present: false },
  hot_topics: { present: false },
};

const control = {
  settings: {
    daily_enabled: "true",
    monthly_budget: "100",
    target_words: "2000",
    style_tweak: "",
    daily_run_time: "08:00",
  },
  workflows: {
    daily: { online: true, active: true, last: null },
    weekly: { online: true, active: true, last: null },
  },
};

function jsonResponse(data) {
  return {
    ok: true,
    json: async () => data,
  };
}

describe("App", () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes("/api/dashboard")) return jsonResponse(dashboard);
      if (String(url).includes("/api/control")) return jsonResponse(control);
      if (String(url).includes("/api/executions")) return jsonResponse({ executions: [] });
      if (String(url).includes("/api/cost")) return jsonResponse({ by_day: [], by_node: [] });
      if (String(url).includes("/api/agents")) return jsonResponse({ agents: [] });
      return jsonResponse({});
    });
  });

  it("renders the dashboard shell", async () => {
    render(<App />);
    expect(await screen.findByText("流水线实时总览：作品、质量、成本、健康与热点")).toBeInTheDocument();
    expect(screen.getByText("小说流水线")).toBeInTheDocument();
    expect(screen.getByText("连载作品")).toBeInTheDocument();
  });

  it("opens the command palette with Ctrl+K and filters commands", async () => {
    render(<App />);
    await screen.findByText("连载作品");
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(await screen.findByPlaceholderText(/搜索命令/)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/搜索命令/), { target: { value: "成本" } });
    expect(screen.getByText("打开成本中心")).toBeInTheDocument();
    expect(screen.queryByText("打开作品库")).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByPlaceholderText(/搜索命令/), { key: "Escape" });
    await waitFor(() => expect(screen.queryByPlaceholderText(/搜索命令/)).not.toBeInTheDocument());
  });

  it("navigates pages from the sidebar", async () => {
    render(<App />);
    await screen.findByText("连载作品");
    fireEvent.click(screen.getByText("Agent 管理"));
    expect(await screen.findByText("写作智能体")).toBeInTheDocument();
  });
});
