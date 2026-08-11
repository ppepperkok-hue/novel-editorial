import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WorksPage from "../components/WorksPage.jsx";

function jsonResponse(data) {
  return { ok: true, json: async () => data };
}

const data = {
  updated_at: "2026-08-11 12:00:00",
  summary: { novels: 2, chapters_total: 80, chapters_published: 78 },
  novels: [
    {
      id: 1,
      title: "收尾书",
      status: "finishing",
      genre: "都市",
      platform: "fanqie",
      chapters: 80,
      published: 78,
      outline: {
        bible: {
          characters: [{ name: "林舟", role: "主角", personality: "冷静" }],
        },
      },
    },
    {
      id: 2,
      title: "完结书",
      status: "finished",
      genre: "玄幻",
      platform: "fanqie",
      chapters: 200,
      published: 200,
    },
    {
      id: 3,
      title: "连载书",
      status: "publishing",
      genre: "悬疑",
      platform: "fanqie",
      chapters: 12,
      published: 12,
    },
  ],
  publish_logs: [],
};

describe("WorksPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes("/api/ending/status")) {
        return jsonResponse({
          novels: [
            { id: 1, title: "收尾书", status: "finishing", finish_remaining: 5, finish_note: "主线进入终局" },
            { id: 2, title: "完结书", status: "finished" },
          ],
        });
      }
      return jsonResponse({});
    });
  });

  it("shows finishing state with remaining chapters and reason", async () => {
    render(<WorksPage data={data} pushToast={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getAllByText("收尾中").length).toBeGreaterThan(0),
    );
    expect(screen.getByText(/还剩 5 章收尾/)).toBeInTheDocument();
    expect(screen.getByText(/评估理由：主线进入终局/)).toBeInTheDocument();
    expect(screen.getByText("已完结")).toBeInTheDocument();
  });

  it("localizes status chips", async () => {
    render(<WorksPage data={data} pushToast={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getAllByText("连载中").length).toBeGreaterThan(0),
    );
    expect(screen.getAllByText("收尾中").length).toBeGreaterThan(0);
    expect(screen.getByText("已完结")).toBeInTheDocument();
  });

  it("shows weekly character evolution in the timeline", async () => {
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes("/api/ending/status")) {
        return jsonResponse({ novels: [] });
      }
      if (String(url).includes("/api/characters/evolution")) {
        return jsonResponse({
          evolution: [{ name: "林舟", chapter_id: 0, change_log: "周会固化", arc: "觉醒" }],
        });
      }
      return jsonResponse({ items: [] });
    });
    render(<WorksPage data={data} pushToast={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("收尾书")).toBeInTheDocument());
    fireEvent.click(screen.getByText("收尾书"));
    await waitFor(() =>
      expect(screen.getByText(/周会：周会固化/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/\[觉醒\]/)).toBeInTheDocument();
  });
});
