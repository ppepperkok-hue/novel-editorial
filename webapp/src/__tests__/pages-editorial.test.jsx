import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EditorialPage from "../pages/EditorialPage.jsx";
import { jsonResponse, mockFetchFor } from "./fixtures.js";

describe("EditorialPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
  });

  it("renders inbox messages with unread badge", async () => {
    render(<EditorialPage />);
    await waitFor(() =>
      expect(screen.getAllByText("审稿打回 · 第 42 章").length).toBeGreaterThan(0),
    );
    expect(screen.getAllByText("议题：下一卷方向").length).toBeGreaterThan(0);
    expect(screen.getByText("2 条未读")).toBeInTheDocument();
    expect(screen.getByText("整理规则台账模板")).toBeInTheDocument();
  });

  it("groups replies into the same thread", async () => {
    render(<EditorialPage />);
    await waitFor(() => expect(screen.getAllByText("议题：下一卷方向").length).toBeGreaterThan(0));
    await waitFor(() =>
      expect(screen.getAllByText("审稿打回 · 第 42 章").length).toBeGreaterThan(0),
    );
    fireEvent.click(screen.getAllByText("审稿打回 · 第 42 章")[0]);
    await waitFor(() =>
      expect(screen.getAllByText("已重写过渡段，回传再审。").length).toBeGreaterThan(0),
    );
  });

  it("shows empty state when no messages", async () => {
    global.fetch = vi.fn(
      mockFetchFor({
        mailbox: { ok: true, messages: [] },
        editorial: { updated_at: "", agents: [], relations: [], unread: {}, actions: [], today_activity: [] },
      }),
    );
    render(<EditorialPage />);
    await waitFor(() => expect(screen.getByText("没有符合条件的消息")).toBeInTheDocument());
  });

  it("shows explicit error when mailbox fails", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("offline"));
    render(<EditorialPage />);
    await waitFor(() => expect(screen.getByText("消息加载失败")).toBeInTheDocument());
  });
});
