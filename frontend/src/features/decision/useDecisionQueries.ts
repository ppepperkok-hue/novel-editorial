import { useQuery } from "@tanstack/react-query";

import { getPending } from "../../api/client";

export const decisionQueryKeys = {
  pending: (workspaceId: string) =>
    ["works", workspaceId, "pending"] as const,
};

/** Drafts awaiting the author's decision (GET /works/{id}/pending). */
export function usePending(workspaceId: string | undefined) {
  return useQuery({
    queryKey: decisionQueryKeys.pending(workspaceId ?? ""),
    queryFn: () => getPending(workspaceId as string),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}
