import { useEffect } from "react";

import { useWorkspace } from "../features/works/useWorksQueries";
import { useWorkspaceStore } from "../stores/workspaceStore";

/**
 * Fetch the workspace detail and record the current selection in the shell
 * store, so the sidebar and header stay in the workspace context. Returns the
 * same TanStack Query result as `useWorkspace`.
 */
export function useWorkspaceSelection(workspaceId: string | undefined) {
  const workspace = useWorkspace(workspaceId);
  const setCurrentWorkspace = useWorkspaceStore(
    (state) => state.setCurrentWorkspace,
  );

  useEffect(() => {
    if (workspace.data !== undefined) {
      setCurrentWorkspace({
        id: workspace.data.id,
        title: workspace.data.title,
      });
    }
  }, [setCurrentWorkspace, workspace.data]);

  return workspace;
}
