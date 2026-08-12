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
    await waitFor(() => expect(screen.getAllByText("掌印").length).toBeGreaterThan(0));
    expect(screen.getByText("2 位编辑")).toBeInTheDocument();
    expect(screen.getByText("人格档案")).toBeInTheDocument();
  });

  it("switches selection when clicking another agent", async () => {
    render(<AgentsPage />);
    await waitFor(() => expect(screen.getByText("墨白")).toBeInTheDocument());
    fireEvent.click(screen.getByText("墨白"));
    await waitFor(() => expect(screen.getByText("人格档案")).toBeInTheDocument());
  });

  it("saves persona via postAgents", async () => {
    render(<AgentsPage />);
    await waitFor(() => expect(screen.getAllByText("掌印").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText("保存并部署"));
    await waitFor(() => {
      const post = global.fetch.mock.calls.find(
        ([url, opts]) => String(url).includes("/api/agents") && opts?.method === "POST",
      );
      expect(post).toBeTruthy();
      expect(JSON.parse(post[1].body).action).toBe("save");
    });
  });

  it("saves custom display name and avatar to localStorage", async () => {
    localStorage.clear();
    render(<AgentsPage />);
    await waitFor(() => expect(screen.getAllByText("掌印").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText("编辑资料"));
    const nameInput = screen.getByPlaceholderText("如：掌印");
    fireEvent.change(nameInput, { target: { value: "大主编" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(screen.getAllByText("大主编").length).toBeGreaterThan(0));
    const stored = JSON.parse(localStorage.getItem("agent_custom_v1"));
    expect(stored["eic.md"].displayName).toBe("大主编");
  });
});
