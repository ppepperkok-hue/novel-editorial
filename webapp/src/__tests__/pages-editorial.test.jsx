import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EditorialPage from "../pages/EditorialPage.jsx";
import { jsonResponse, mockFetchFor } from "./fixtures.js";

describe("EditorialPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
  });

  it("renders inbox messages with unread badge", async () => {
    render(<EditorialPage />);
    await waitFor(() => expect(screen.getByText("审稿打回 · 第 42 章")).toBeInTheDocument());
    expect(screen.getByText("1 条未读")).toBeInTheDocument();
    expect(screen.getByText("整理规则台账模板")).toBeInTheDocument();
  });

  it("shows empty state when no messages", async () => {
    global.fetch = vi.fn(
      mockFetchFor({
        mailbox: { ok: true, messages: [] },
        editorial: { updated_at: "", agents: [], relations: [], unread: {}, actions: [], today_activity: [] },
      }),
    );
    render(<EditorialPage />);
    await waitFor(() => expect(screen.getByText("收件箱是空的")).toBeInTheDocument());
  });

  it("shows explicit error when mailbox fails", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("offline"));
    render(<EditorialPage />);
    await waitFor(() => expect(screen.getByText("消息加载失败")).toBeInTheDocument());
  });
});
