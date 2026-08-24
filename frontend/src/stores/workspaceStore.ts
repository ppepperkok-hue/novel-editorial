import { create } from "zustand";

/**
 * Client-side workspace selection state (Zustand).
 *
 * Only client-only UI state lives here: which workspace is currently open in
 * the shell. Server data such as the workspace list and band profiles is kept
 * in the TanStack Query cache, never duplicated into this store.
 */
export interface CurrentWorkspace {
  id: string;
  title: string;
}

interface WorkspaceState {
  currentWorkspace: CurrentWorkspace | null;
  setCurrentWorkspace: (workspace: CurrentWorkspace) => void;
  clearCurrentWorkspace: () => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  currentWorkspace: null,
  setCurrentWorkspace: (workspace) => set({ currentWorkspace: workspace }),
  clearCurrentWorkspace: () => set({ currentWorkspace: null }),
}));
