import { beforeEach, describe, expect, it } from "vitest";
import {
  exportCustomAgents,
  importCustomAgents,
  saveCustomAgent,
} from "../lib/agent-custom.js";

describe("agent-custom import/export", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("exports saved custom agents as JSON", () => {
    saveCustomAgent("eic.md", {
      displayName: "大主编",
      avatarText: "掌",
      avatarColor: "#5B8DB8",
    });
    const parsed = JSON.parse(exportCustomAgents());
    expect(parsed["eic.md"].displayName).toBe("大主编");
  });

  it("imports valid JSON and reports count", () => {
    const result = importCustomAgents(
      JSON.stringify({
        "writer.md": {
          displayName: "墨白",
          avatarText: "墨",
          avatarColor: "#5B9B8C",
        },
      }),
    );
    expect(result.ok).toBe(true);
    expect(result.count).toBe(1);
    expect(JSON.parse(localStorage.getItem("agent_custom_v1"))["writer.md"].displayName).toBe("墨白");
  });

  it("rejects invalid JSON explicitly", () => {
    const result = importCustomAgents("{not-json");
    expect(result.ok).toBe(false);
    expect(result.error).toContain("JSON");
  });

  it("skips malformed entries and fails when nothing is valid", () => {
    const result = importCustomAgents(
      JSON.stringify({
        "bad.md": { displayName: 42 },
      }),
    );
    expect(result.ok).toBe(false);
    expect(result.error).toContain("有效条目");
  });

  it("keeps avatar images through export and import", () => {
    saveCustomAgent("eic.md", {
      displayName: "大主编",
      avatarText: "掌",
      avatarColor: "#5B8DB8",
      avatarImage: "data:image/jpeg;base64,abc",
    });
    const exported = exportCustomAgents();
    expect(exported).toContain("data:image/jpeg;base64,abc");
    localStorage.clear();
    const result = importCustomAgents(exported);
    expect(result.ok).toBe(true);
    expect(JSON.parse(localStorage.getItem("agent_custom_v1"))["eic.md"].avatarImage).toBe(
      "data:image/jpeg;base64,abc",
    );
  });
});
