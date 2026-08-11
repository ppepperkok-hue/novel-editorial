import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ExecutionsPage from "../components/ExecutionsPage.jsx";

function jsonResponse(data) {
  return { ok: true, json: async () => data };
}

function makeExec(id, status) {
  return {
    workflow: "日更",
    id,
    status,
    started_at: "2026-08-11T05:00:00.000Z",
    stopped_at: "2026-08-11T05:30:00.000Z",
  };
}

describe("ExecutionsPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes("/api/executions")) {
        const rows = Array.from({ length: 30 }, (_, i) => makeExec(200 - i, "success"));
        return jsonResponse({ executions: rows });
      }
      return jsonResponse({});
    });
  });

  it("shows all rows returned by the API", async () => {
    render(<ExecutionsPage snapshot={{ executions: [makeExec(999, "running")] }} />);
    await waitFor(() => expect(screen.getAllByText("日更").length).toBe(30));
    expect(screen.queryByText("999")).not.toBeInTheDocument();
  });
});
