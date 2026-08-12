import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AgentsPage from "../pages/AgentsPage.jsx";
import { mockFetchFor } from "./fixtures.js";

describe("AgentsPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(mockFetchFor());
  });

  it("lists agents and shows selected details", async () => {
    render(<AgentsPage />);
    await waitFor(() => expect(screen.getAllByText("主编终审").length).toBeGreaterThan(0));
    expect(screen.getByText("2 位编辑")).toBeInTheDocument();
    expect(screen.getByText("人格档案")).toBeInTheDocument();
  });

  it("switches selection when clicking another agent", async () => {
    render(<AgentsPage />);
    await waitFor(() => expect(screen.getByText("写手")).toBeInTheDocument());
    fireEvent.click(screen.getByText("写手"));
    await waitFor(() => expect(screen.getByText("人格档案")).toBeInTheDocument());
  });

  it("saves persona via postAgents", async () => {
    render(<AgentsPage />);
    await waitFor(() => expect(screen.getAllByText("主编终审").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText("保存并部署"));
    await waitFor(() => {
      const post = global.fetch.mock.calls.find(
        ([url, opts]) => String(url).includes("/api/agents") && opts?.method === "POST",
      );
      expect(post).toBeTruthy();
      expect(JSON.parse(post[1].body).action).toBe("save");
    });
  });
});
