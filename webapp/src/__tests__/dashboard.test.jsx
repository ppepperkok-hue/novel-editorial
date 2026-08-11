import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage, { localToday } from "../components/DashboardPage.jsx";

function jsonResponse(data) {
  return { ok: true, json: async () => data };
}

function renderDashboard() {
  return render(
    <DashboardPage
      data={{
        summary: {},
        cost_budget: 100,
        health: { issues: [] },
        chapters: [],
        publish_logs: [],
        reader_stats: null,
        hot_topics: null,
      }}
      error=""
      onRefresh={() => {}}
      pushToast={() => {}}
      snapshot={{}}
    />,
  );
}

describe("DashboardPage helpers", () => {
  it("localToday returns the local date in YYYY-MM-DD", () => {
    const d = new Date();
    const expected = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    expect(localToday()).toBe(expected);
    expect(localToday()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("DashboardPage rendering", () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes("/api/control")) {
        return jsonResponse({ scheduler: { enabled: true, scheduled_time: "08:00" } });
      }
      if (String(url).includes("/api/meetings")) {
        return jsonResponse({ meetings: [] });
      }
      return jsonResponse({});
    });
  });

  it("renders without throwing and shows key sections", async () => {
    renderDashboard();
    expect(screen.getByText("流程状态与补更")).toBeInTheDocument();
    expect(screen.getByText("月度预算")).toBeInTheDocument();
    expect(screen.getByText("健康检查")).toBeInTheDocument();
    expect(screen.getByText("热点选题")).toBeInTheDocument();
    await screen.findByText("● 已开启");
  });
});
