import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App placeholder page", () => {
  it("renders the panel title, three windows, and the status line", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "Novel Editorial 面板" }),
    ).toBeInTheDocument();
    expect(screen.getAllByTestId("panel-window")).toHaveLength(3);
    expect(screen.getByText("事件流")).toBeInTheDocument();
    expect(screen.getByText("穿透查询")).toBeInTheDocument();
    expect(screen.getByText("拍板提醒")).toBeInTheDocument();
    expect(screen.getByTestId("status-line")).toBeInTheDocument();
    expect(screen.getAllByTestId("panel-state-loading")).toHaveLength(3);
    expect(screen.getAllByTestId("panel-state-empty")).toHaveLength(3);
    expect(screen.getAllByTestId("panel-state-error")).toHaveLength(3);
  });
});
