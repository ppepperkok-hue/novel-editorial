import { describe, beforeEach, expect, it } from "vitest";

import { useWorkspaceStore } from "./workspaceStore";

const { getState, setState } = useWorkspaceStore;

describe("workspaceStore", () => {
  beforeEach(() => {
    setState({ currentWorkspace: null });
  });

  it("starts with no current workspace", () => {
    expect(getState().currentWorkspace).toBeNull();
  });

  it("setCurrentWorkspace stores only client-side selection metadata", () => {
    getState().setCurrentWorkspace({ id: "w1", title: "甲书" });

    expect(getState().currentWorkspace).toEqual({ id: "w1", title: "甲书" });
  });

  it("clearCurrentWorkspace resets the selection", () => {
    getState().setCurrentWorkspace({ id: "w1", title: "甲书" });
    getState().clearCurrentWorkspace();

    expect(getState().currentWorkspace).toBeNull();
  });
});
