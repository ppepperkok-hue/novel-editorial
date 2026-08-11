import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AuditPage from "../components/AuditPage.jsx";

function jsonResponse(data) {
  return { ok: true, json: async () => data };
}

describe("AuditPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes("/api/audit")) {
        return jsonResponse({
          logs: [
            {
              id: 1,
              created_at: "2026-08-11 10:00:00",
              category: "operation",
              action: "daily_run",
              target_type: "novel",
              target_id: 1,
              detail: { status: "completed" },
              source: "scheduler",
            },
          ],
        });
      }
      return jsonResponse({});
    });
  });

  it("renders audit rows, date filters and export", async () => {
    render(<AuditPage />);
    await waitFor(() => expect(screen.getByText("daily_run")).toBeInTheDocument());
    expect(screen.getAllByText("操作").length).toBeGreaterThan(0);
    expect(screen.getByText("导出 JSON")).toBeInTheDocument();
    expect(screen.getByTitle("开始日期")).toBeInTheDocument();
    expect(screen.getByTitle("结束日期")).toBeInTheDocument();
    expect(screen.getByText("共 1 条")).toBeInTheDocument();
  });
});
