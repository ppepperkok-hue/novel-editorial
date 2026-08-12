import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FreeLive } from "../components/features/meetings/free-live.jsx";
import MeetingsPage from "../pages/MeetingsPage.jsx";
import { mockFetchFor } from "./fixtures.js";

describe("MeetingsPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
  });

  it("renders start form and history list", async () => {
    render(<MeetingsPage />);
    await waitFor(() => expect(screen.getByText("发起会议")).toBeInTheDocument());
    expect(screen.getByPlaceholderText("会议主题，如：讨论下一卷的剧情走向")).toBeInTheDocument();
    expect(screen.getByText("#17")).toBeInTheDocument();
  });

  it("starts a meeting with the typed topic", async () => {
    render(<MeetingsPage />);
    const input = screen.getByPlaceholderText("会议主题，如：讨论下一卷的剧情走向");
    fireEvent.change(input, { target: { value: "讨论主角成长线" } });
    fireEvent.click(screen.getByText("发起"));
    await waitFor(() => {
      const post = global.fetch.mock.calls.find(([, opts]) => opts?.method === "POST");
      expect(post).toBeTruthy();
      const body = JSON.parse(post[1].body);
      expect(body.topic).toBe("讨论主角成长线");
    });
  });

  it("shows empty history when no meetings", async () => {
    global.fetch = vi.fn(mockFetchFor({ meetings: { meetings: [] } }));
    render(<MeetingsPage />);
    await waitFor(() => expect(screen.getByText("还没有会议记录")).toBeInTheDocument());
  });
});

describe("FreeLive", () => {
  let eventSource;

  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
    global.EventSource = vi.fn(function MockEventSource(url) {
      eventSource = this;
      this.url = url;
      this.onmessage = null;
      this.onerror = null;
      this.close = vi.fn();
    });
  });

  function renderFree() {
    return render(
      <FreeLive
        session={{ id: 5, topic: "测试会议", attendees: ["planner", "reviewer"], mode: "free" }}
        onEnded={() => {}}
      />,
    );
  }

  it("renders live messages from SSE events", async () => {
    renderFree();
    await waitFor(() => expect(eventSource).toBeTruthy());
    eventSource.onmessage({
      data: JSON.stringify({ type: "message", message_id: 7, agent: "planner", speech: "先抛方向" }),
    });
    await waitFor(() => expect(screen.getByText("先抛方向")).toBeInTheDocument());
  });

  it("shows approval dialog on approval event and resolves it", async () => {
    renderFree();
    await waitFor(() => expect(eventSource).toBeTruthy());
    eventSource.onmessage({
      data: JSON.stringify({
        type: "approval",
        interaction: {
          id: 3,
          agent: "eic",
          question: "采纳经验卡草案？",
          choices: ["同意", "拒绝"],
          expires_at: "",
          status: "pending",
        },
      }),
    });
    await waitFor(() => expect(screen.getByText("需要您决定")).toBeInTheDocument());
    fireEvent.click(screen.getByText("同意"));
    await waitFor(() => {
      const post = global.fetch.mock.calls.find(
        ([url, opts]) => String(url).includes("/api/meetings/interactions/respond") && opts?.method === "POST",
      );
      expect(post).toBeTruthy();
      expect(JSON.parse(post[1].body).resolution).toBe("同意");
    });
  });

  it("inserts mention candidates into the input", async () => {
    renderFree();
    const input = screen.getByPlaceholderText("发言或 @某位编辑…");
    fireEvent.change(input, { target: { value: "请 @守" } });
    await waitFor(() => expect(screen.getByText("守正")).toBeInTheDocument());
    fireEvent.click(screen.getByText("守正"));
    expect(input.value).toContain("@守正");
  });

  it("shows summary anchor and compression state", async () => {
    global.fetch = vi.fn(
      mockFetchFor({
        session: { status: "running", transcript: [], meeting_summary: "决定先定方向" },
      }),
    );
    renderFree();
    await waitFor(() => expect(screen.getByText("会议摘要锚点")).toBeInTheDocument());
    expect(screen.getByText("决定先定方向")).toBeInTheDocument();
    eventSource.onmessage({
      data: JSON.stringify({ type: "compress", status: "compressing" }),
    });
    await waitFor(() => expect(screen.getByText(/正在压缩长历史/)).toBeInTheDocument());
  });
});
