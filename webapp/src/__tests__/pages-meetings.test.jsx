import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
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
