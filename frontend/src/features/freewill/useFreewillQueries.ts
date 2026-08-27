import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  dropMotive,
  getBehaviorState,
  getBehaviorTimeline,
  getPatience,
  listMotives,
  type BehaviorTimelineQuery,
} from "../../api/client";

export const freewillQueryKeys = {
  motives: (workspaceId: string) =>
    ["works", workspaceId, "motives"] as const,
  patience: (workspaceId: string) =>
    ["works", workspaceId, "patience"] as const,
  timeline: (workspaceId: string, query: BehaviorTimelineQuery) =>
    [
      "works",
      workspaceId,
      "behavior",
      "timeline",
      query?.agent ?? "",
      (query?.kind ?? []).join(","),
      query?.limit ?? 0,
    ] as const,
  state: (workspaceId: string) =>
    ["works", workspaceId, "behavior", "state"] as const,
};

/** Partner motives as CLI-aligned text (GET /works/{id}/motives). */
export function useMotives(workspaceId: string | undefined) {
  return useQuery({
    queryKey: freewillQueryKeys.motives(workspaceId ?? ""),
    queryFn: () => listMotives(workspaceId as string),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}

/** Drop one motive and refresh motives + the behavior timeline. */
export function useDropMotive(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (motiveId: string) =>
      dropMotive(workspaceId as string, motiveId),
    onSuccess: () => {
      if (workspaceId !== undefined) {
        void queryClient.invalidateQueries({
          queryKey: ["works", workspaceId, "motives"],
        });
        void queryClient.invalidateQueries({
          queryKey: ["works", workspaceId, "behavior"],
        });
      }
    },
  });
}

/** Every partner's patience pool and state breakdowns (GET .../patience). */
export function usePatience(workspaceId: string | undefined) {
  return useQuery({
    queryKey: freewillQueryKeys.patience(workspaceId ?? ""),
    queryFn: () => getPatience(workspaceId as string),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}

/** Behavior traces oldest first, filtered by agent / kinds (GET .../timeline). */
export function useBehaviorTimeline(
  workspaceId: string | undefined,
  query: BehaviorTimelineQuery,
) {
  return useQuery({
    queryKey: freewillQueryKeys.timeline(workspaceId ?? "", query),
    queryFn: () => getBehaviorTimeline(workspaceId as string, query),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}

/** Each partner's current behavior state (GET /works/{id}/behavior). */
export function useBehaviorState(workspaceId: string | undefined) {
  return useQuery({
    queryKey: freewillQueryKeys.state(workspaceId ?? ""),
    queryFn: () => getBehaviorState(workspaceId as string),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}
