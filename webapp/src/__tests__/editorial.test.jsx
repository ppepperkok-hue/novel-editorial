import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EditorialPage from "../components/EditorialPage.jsx";

function jsonResponse(data) {
  return { ok: true, json: async () => data };
}

describe("EditorialPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes("/api/editorial/overview")) {
        return jsonResponse({
          updated_at: "2026-08-11 12:00:00",
          agents: [{ file: "writer.md", name: "墨白" }],
          relations: [{ id: 1, agent: "reviewer", other: "writer", familiarity: 0.2, trust: 0.3, friction: 0.4 }],
          unread: { writer: 2 },
          actions: [{ id: 1, task: "把规则台账模板定死", status: "pending", assignee: "writer", claimed_by: "", due_at: "2026-08-20" }],
          today_activity: [{ id: 1, agent: "writer", activity_type: "chapter", title: "写了第二章" }],
        });
      }
      if (String(url).includes("/api/agents/mailbox")) {
        return jsonResponse({
          ok: true,
          messages: [
            { id: 1, from_agent: "reviewer", to_agent: "writer", kind: "review_feedback", subject: "审稿打回", body: "逻辑承接生硬", status: "unread", created_at: "2026-08-11 11:00:00" },
          ],
        });
      }
      return jsonResponse({});
    });
  });

  it("renders the editorial board sections", async () => {
    render(<EditorialPage />);
    await waitFor(() => expect(screen.getByText("任务板")).toBeInTheDocument());
    expect(screen.getByText("消息流")).toBeInTheDocument();
    expect(screen.getByText("关系网")).toBeInTheDocument();
    expect(screen.getByText("每人今日")).toBeInTheDocument();
    expect(screen.getByText("把规则台账模板定死")).toBeInTheDocument();
    expect(screen.getByText("审稿打回")).toBeInTheDocument();
    expect(screen.getByText("写了第二章")).toBeInTheDocument();
    expect(screen.getAllByText("未读消息").length).toBeGreaterThan(0);
  });

  it("shows empty states", async () => {
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes("/api/editorial/overview")) {
        return jsonResponse({
          updated_at: "2026-08-11 12:00:00",
          agents: [],
          relations: [],
          unread: {},
          actions: [],
          today_activity: [],
        });
      }
      return jsonResponse({ ok: true, messages: [] });
    });
    render(<EditorialPage />);
    await waitFor(() => expect(screen.getByText("收件箱是空的，agent 之间还没说过话。")).toBeInTheDocument());
    expect(screen.getByText("今天还没有活动记录。")).toBeInTheDocument();
  });

  it("claims a pending action", async () => {
    render(<EditorialPage />);
    await waitFor(() => expect(screen.getByText("把规则台账模板定死")).toBeInTheDocument());
    fireEvent.click(screen.getByText("认领"));
    await waitFor(() => {
      const post = global.fetch.mock.calls.find(
        ([url, opts]) => String(url).includes("/api/agent_actions/claim") && opts?.method === "POST",
      );
      expect(post).toBeTruthy();
    });
  });
});
