import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CostPage from "../pages/CostPage.jsx";
import ExecutionsPage from "../pages/ExecutionsPage.jsx";
import FlowPage from "../pages/FlowPage.jsx";
import { mockFetchFor } from "./fixtures.js";

describe("CostPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
  });

  it("renders budget metrics and node table", async () => {
    render(<CostPage />);
    await waitFor(() => expect(screen.getByText("本月已用")).toBeInTheDocument());
    expect(screen.getByText("预算使用率")).toBeInTheDocument();
    expect(screen.getByText("写稿A")).toBeInTheDocument();
  });
});

describe("ExecutionsPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
  });

  it("renders workflow executions and daily run trace", async () => {
    render(<ExecutionsPage />);
    await waitFor(() => expect(screen.getByText("工作流执行")).toBeInTheDocument());
    expect(screen.getByText("日更运行留痕")).toBeInTheDocument();
    expect(screen.getByText("部分成功")).toBeInTheDocument();
  });
});

describe("FlowPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
  });

  it("renders flow canvas with status legend", async () => {
    render(<FlowPage />);
    await waitFor(() => expect(screen.getByText("上次成功")).toBeInTheDocument());
    expect(screen.getByText("导出 HTML 报告")).toBeInTheDocument();
  });
});
