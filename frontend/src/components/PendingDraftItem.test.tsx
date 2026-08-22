import "@testing-library/jest-dom/vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PendingDraft } from "../api/client";
import PendingDraftItem from "./PendingDraftItem";

const draft: PendingDraft = {
  id: "d-a",
  title: "第一章",
  status: "draft",
  current_version: 1,
  updated_at: "2026-08-22T10:00:00+00:00",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderItem(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const onOpenWorkspace = vi.fn();
  const onDecided = vi.fn();
  const utils = render(
    <PendingDraftItem
      workspaceId="w-a"
      workspaceTitle="甲书"
      draft={draft}
      onOpenWorkspace={onOpenWorkspace}
      onDecided={onDecided}
    />,
  );
  return { onOpenWorkspace, onDecided, ...utils };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("PendingDraftItem two-step confirmation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("requires a second click before posting the decision", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ id: "d-a", status: "accepted" }, 201));
    const { onDecided } = renderItem(fetchMock);

    fireEvent.click(screen.getByRole("button", { name: "接受" }));
    expect(screen.getByRole("button", { name: "确认接受？" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "确认接受？" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/works/w-a/decisions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ draft_id: "d-a", action: "accept" }),
      }),
    );
    expect(onDecided).toHaveBeenCalledTimes(1);
  });

  it("resets the confirm state after the timeout", () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}, 201));
    renderItem(fetchMock);

    fireEvent.click(screen.getByRole("button", { name: "接受" }));
    expect(screen.getByRole("button", { name: "确认接受？" })).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(3100);
    });
    expect(screen.getByRole("button", { name: "接受" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("switches the confirmation to the newly clicked action", () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}, 201));
    renderItem(fetchMock);

    fireEvent.click(screen.getByRole("button", { name: "接受" }));
    expect(screen.getByRole("button", { name: "确认接受？" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "拒绝" }));
    expect(screen.getByRole("button", { name: "确认拒绝？" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "接受" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the item and note content intact when the decision fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: "模拟失败" }, 500));
    renderItem(fetchMock);

    fireEvent.click(screen.getByRole("button", { name: "指示" }));
    const noteInput = screen.getByLabelText("拍板指示内容");
    fireEvent.change(noteInput, { target: { value: "方向没问题" } });
    fireEvent.click(screen.getByRole("button", { name: "提交指示" }));
    fireEvent.click(screen.getByRole("button", { name: "确认提交？" }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByTestId("pending-error")).toHaveTextContent("模拟失败");
    expect(screen.getByText("第一章")).toBeInTheDocument();
    expect(screen.getByLabelText("拍板指示内容")).toHaveValue("方向没问题");
    expect(screen.getByRole("button", { name: "提交指示" })).toBeInTheDocument();
  });

  it("clears the confirm state on success and reports the new status", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ id: "d-a", status: "rejected" }, 201));
    const { onDecided } = renderItem(fetchMock);

    fireEvent.click(screen.getByRole("button", { name: "拒绝" }));
    fireEvent.click(screen.getByRole("button", { name: "确认拒绝？" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(onDecided).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "拒绝" })).toBeInTheDocument();
  });
});
