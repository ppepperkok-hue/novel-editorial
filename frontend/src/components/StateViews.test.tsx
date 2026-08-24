import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  EmptyState,
  ErrorState,
  PanelWindow,
  SkeletonRows,
} from "./StateViews";

afterEach(() => {
  cleanup();
});

describe("three-state baseline", () => {
  it("SkeletonRows renders the requested row count with a loading marker", () => {
    render(<SkeletonRows count={4} />);

    expect(screen.getByTestId("panel-state-loading")).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(
      screen.getByTestId("panel-state-loading").querySelectorAll(".skeleton-row"),
    ).toHaveLength(4);
  });

  it("EmptyState renders title and hint", () => {
    render(<EmptyState title="还没有作品" hint="创建第一部作品" />);

    expect(screen.getByTestId("panel-state-empty")).toHaveTextContent(
      "还没有作品",
    );
    expect(screen.getByTestId("panel-state-empty")).toHaveTextContent(
      "创建第一部作品",
    );
  });

  it("ErrorState renders source, message and triggers retry", () => {
    const onRetry = vi.fn();
    render(
      <ErrorState
        source="/works"
        message="模拟失败"
        onRetry={onRetry}
      />,
    );

    const state = screen.getByTestId("panel-state-error");
    expect(state).toHaveTextContent("/works");
    expect(state).toHaveTextContent("模拟失败");
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("PanelWindow renders exactly one state at a time", () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <PanelWindow
        title="窗口"
        state="loading"
        source="/works"
        onRetry={onRetry}
      >
        <p>就绪内容</p>
      </PanelWindow>,
    );
    expect(screen.getByTestId("panel-state-loading")).toBeInTheDocument();
    expect(screen.queryByText("就绪内容")).not.toBeInTheDocument();

    rerender(
      <PanelWindow
        title="窗口"
        state="empty"
        source="/works"
        onRetry={onRetry}
        emptyTitle="空"
        emptyHint="引导"
      >
        <p>就绪内容</p>
      </PanelWindow>,
    );
    expect(screen.getByTestId("panel-state-empty")).toHaveTextContent("空");

    rerender(
      <PanelWindow
        title="窗口"
        state="error"
        source="/works"
        message="boom"
        onRetry={onRetry}
      >
        <p>就绪内容</p>
      </PanelWindow>,
    );
    expect(screen.getByTestId("panel-state-error")).toHaveTextContent("boom");

    rerender(
      <PanelWindow
        title="窗口"
        state="ready"
        source="/works"
        onRetry={onRetry}
      >
        <p>就绪内容</p>
      </PanelWindow>,
    );
    expect(screen.getByText("就绪内容")).toBeInTheDocument();
  });
});
