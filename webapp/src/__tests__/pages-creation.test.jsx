import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChaptersPage from "../pages/ChaptersPage.jsx";
import ReaderPage from "../pages/ReaderPage.jsx";
import WorksPage from "../pages/WorksPage.jsx";
import { mockFetchFor } from "./fixtures.js";

describe("WorksPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
  });

  it("lists projects and shows outline tab", async () => {
    render(<WorksPage />);
    await waitFor(() => expect(screen.getAllByText("雾港怪谈").length).toBeGreaterThan(0));
    expect(screen.getByText("大纲")).toBeInTheDocument();
    expect(screen.getByText("主角")).toBeInTheDocument();
  });
});

describe("ChaptersPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
  });

  it("renders chapter table with status filters", async () => {
    render(<ChaptersPage />);
    await waitFor(() => expect(screen.getByText("雾夜来客")).toBeInTheDocument());
    expect(screen.getByText("手账第一页")).toBeInTheDocument();
    fireEvent.click(screen.getByText("草稿"));
    await waitFor(() => expect(screen.getByText("没有符合条件的章节")).toBeInTheDocument());
  });

  it("opens chapter content preview", async () => {
    render(<ChaptersPage />);
    await waitFor(() => expect(screen.getAllByText("查看").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByText("查看")[0]);
    await waitFor(() => expect(screen.getByText(/雾夜，灯塔的光第三次熄灭/)).toBeInTheDocument());
  });
});

describe("ReaderPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
  });

  it("renders reader metrics and chart from stats", async () => {
    render(<ReaderPage />);
    await waitFor(() => expect(screen.getByText("完读率")).toBeInTheDocument());
    expect(screen.getByText("追读率")).toBeInTheDocument();
  });

  it("shows empty state when stats are absent", async () => {
    global.fetch = vi.fn(
      mockFetchFor({ dashboard: { ...mockFetchForFixturesDashboardEmpty() } }),
    );
    render(<ReaderPage />);
    await waitFor(() => expect(screen.getByText("暂无真实阅读数据")).toBeInTheDocument());
  });
});

function mockFetchForFixturesDashboardEmpty() {
  return {
    updated_at: "",
    summary: {},
    executions: [],
    cost_budget: 100,
    novels: [],
    chapters: [],
    publish_logs: [],
    health: { issues: [] },
    reader_stats: { present: false, rows: [] },
    hot_topics: null,
  };
}
