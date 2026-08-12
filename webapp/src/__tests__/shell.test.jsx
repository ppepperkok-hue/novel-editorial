import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../app/App.jsx";
import { mockFetchFor } from "./fixtures.js";

describe("App shell", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
    localStorage.clear();
    window.location.hash = "";
  });

  it("renders five-section navigation with dashboard active", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("仪表盘")).toBeInTheDocument());
    expect(screen.getByText("总览")).toBeInTheDocument();
    expect(screen.getByText("编辑部")).toBeInTheDocument();
    expect(screen.getByText("创作")).toBeInTheDocument();
    expect(screen.getByText("运营")).toBeInTheDocument();
    expect(screen.getByText("系统")).toBeInTheDocument();
  });

  it("navigates to Agent page via sidebar", async () => {
    render(<App />);
    fireEvent.click(screen.getByText("Agent 管理"));
    await waitFor(() => expect(screen.getByText("编辑名录")).toBeInTheDocument());
  });

  it("toggles theme and persists preference", async () => {
    render(<App />);
    const button = screen.getByLabelText("切换主题");
    fireEvent.click(button);
    expect(localStorage.getItem("panel_theme")).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("opens command palette with Ctrl+K", async () => {
    render(<App />);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    await waitFor(() => expect(screen.getByPlaceholderText("输入命令或搜索页面…")).toBeInTheDocument());
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    await waitFor(() =>
      expect(screen.queryByPlaceholderText("输入命令或搜索页面…")).not.toBeInTheDocument(),
    );
  });
});
