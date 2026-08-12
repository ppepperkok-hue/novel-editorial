import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AuditPage from "../pages/AuditPage.jsx";
import SettingsPage from "../pages/SettingsPage.jsx";
import { mockFetchFor } from "./fixtures.js";

describe("SettingsPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
  });

  it("loads settings from control payload", async () => {
    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByDisplayValue("08:00")).toBeInTheDocument());
    fireEvent.click(screen.getByText("预算与目标"));
    await waitFor(() => expect(screen.getByDisplayValue("100")).toBeInTheDocument());
    expect(screen.getByText("运行")).toBeInTheDocument();
  });

  it("saves settings with form values", async () => {
    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByText("保存")).toBeInTheDocument());
    fireEvent.click(screen.getByText("保存"));
    await waitFor(() => {
      const post = global.fetch.mock.calls.find(([, opts]) => opts?.method === "POST");
      expect(post).toBeTruthy();
      expect(JSON.parse(post[1].body).action).toBe("save_settings");
    });
  });
});

describe("AuditPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
  });

  it("renders audit log table with category filters", async () => {
    render(<AuditPage />);
    await waitFor(() => expect(screen.getByText("publish")).toBeInTheDocument());
    expect(screen.getByText("留痕档案")).toBeInTheDocument();
  });

  it("shows empty state when no logs", async () => {
    global.fetch = vi.fn(mockFetchFor({ audit: { logs: [] } }));
    render(<AuditPage />);
    await waitFor(() => expect(screen.getByText("暂无留痕记录")).toBeInTheDocument());
  });
});
