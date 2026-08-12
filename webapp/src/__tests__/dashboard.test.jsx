import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "../pages/DashboardPage.jsx";
import { jsonResponse, mockFetchFor } from "./fixtures.js";

describe("DashboardPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
  });

  it("shows idle state with today's published count", async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText("待命")).toBeInTheDocument());
    expect(screen.getByText("章已发布")).toBeInTheDocument();
    expect(screen.getByText("编辑部开工")).toBeInTheDocument();
    expect(screen.getByText("需要您决定")).toBeInTheDocument();
  });

  it("renders open-workday command line controls", async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText("开工")).toBeInTheDocument());
    expect(screen.getByText("写稿")).toBeInTheDocument();
    expect(screen.getByText("整理日")).toBeInTheDocument();
    expect(screen.getByText("开会日")).toBeInTheDocument();
    expect(screen.getByText("自由安排")).toBeInTheDocument();
  });

  it("submits run_now with mode and chapters", async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText("开工")).toBeInTheDocument());
    fireEvent.click(screen.getByText("开工"));
    await waitFor(() => {
      const post = global.fetch.mock.calls.find(
        ([url, opts]) => String(url).includes("/api/control") && opts?.method === "POST",
      );
      expect(post).toBeTruthy();
      const body = JSON.parse(post[1].body);
      expect(body.action).toBe("run_now");
      expect(body.mode).toBe("write");
      expect(body.chapters).toBe(2);
    });
  });

  it("shows awaiting-close decision buttons when workday waits", async () => {
    global.fetch = vi.fn(
      mockFetchFor({
        control: {
          scheduler: {
            enabled: true,
            scheduled_time: "08:00",
            workday: { phase: "awaiting_close", status: "producing", run_id: "run-9" },
          },
          settings: {},
        },
      }),
    );
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText("收工")).toBeInTheDocument());
    expect(screen.getByText("开会（周会）")).toBeInTheDocument();
    expect(screen.getByText("继续补跑")).toBeInTheDocument();
  });

  it("shows error state with retry when backend is offline", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("network down"));
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText("后端连接失败")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  });
});
