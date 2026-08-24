import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import EventStreamStatus from "./EventStreamStatus";

afterEach(() => {
  cleanup();
});

describe("EventStreamStatus", () => {
  it("shows the label for each status without a notice", () => {
    render(<EventStreamStatus status="open" notice={null} />);
    expect(screen.getByTestId("event-stream-status")).toHaveTextContent(
      "实时连接：已连接",
    );
    expect(screen.getByTestId("event-stream-status")).toHaveClass(
      "event-stream-status--open",
    );
  });

  it("shows the connecting state while the handshake is pending", () => {
    render(<EventStreamStatus status="connecting" notice={null} />);
    expect(screen.getByTestId("event-stream-status")).toHaveTextContent(
      "连接中…",
    );
  });

  it("prefers the reconnect notice over the generic label", () => {
    render(
      <EventStreamStatus
        status="reconnecting"
        notice="连接断开，正在自动重连…"
      />,
    );
    expect(screen.getByTestId("event-stream-status")).toHaveTextContent(
      "连接断开，正在自动重连…",
    );
    expect(screen.getByTestId("event-stream-status")).toHaveClass(
      "event-stream-status--reconnecting",
    );
  });

  it("marks the polling fallback visibly with the interval notice", () => {
    render(
      <EventStreamStatus
        status="polling"
        notice="实时通道持续失败，已切换为轮询（30 秒）"
      />,
    );
    expect(screen.getByTestId("event-stream-status")).toHaveTextContent(
      "轮询（30 秒）",
    );
    expect(screen.getByTestId("event-stream-status")).toHaveClass(
      "event-stream-status--polling",
    );
  });
});
