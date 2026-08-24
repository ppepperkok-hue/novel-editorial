import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  checkSettings,
  createInspiration,
  deleteInspiration,
  getInspiration,
  getSetting,
  listInspirations,
  listSettings,
  writeSetting,
  type InspirationAddBody,
  type SettingWriteBody,
} from "../../api/client";

export const settingsQueryKeys = {
  settings: (workspaceId: string, kind?: string) =>
    ["works", workspaceId, "settings", kind ?? "all"] as const,
  setting: (workspaceId: string, settingId: string) =>
    ["works", workspaceId, "settings", settingId] as const,
  check: (workspaceId: string) =>
    ["works", workspaceId, "settings", "check"] as const,
  inspirations: (workspaceId: string, kind?: string, keyword?: string) =>
    [
      "works",
      workspaceId,
      "inspirations",
      kind ?? "all",
      keyword ?? "",
    ] as const,
  inspiration: (workspaceId: string, inspirationId: string) =>
    ["works", workspaceId, "inspirations", inspirationId] as const,
};

/** Settings list, optionally filtered by kind label (GET .../settings). */
export function useSettings(
  workspaceId: string | undefined,
  kind?: string,
) {
  return useQuery({
    queryKey: settingsQueryKeys.settings(workspaceId ?? "", kind),
    queryFn: () => listSettings(workspaceId as string, { kind }),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}

/** One setting with its latest version content (GET .../settings/{id}). */
export function useSetting(
  workspaceId: string | undefined,
  settingId: string | null,
) {
  return useQuery({
    queryKey: settingsQueryKeys.setting(
      workspaceId ?? "",
      settingId ?? "",
    ),
    queryFn: () => getSetting(workspaceId as string, settingId as string),
    enabled:
      settingId !== null &&
      workspaceId !== undefined &&
      workspaceId !== "",
  });
}

/** Add or revise a setting (POST /works/{id}/settings). */
export function useWriteSetting(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SettingWriteBody) =>
      writeSetting(workspaceId as string, body),
    onSuccess: () => {
      if (workspaceId !== undefined) {
        void queryClient.invalidateQueries({
          queryKey: ["works", workspaceId, "settings"],
        });
      }
    },
  });
}

/** Stale/same-name conflict report; refetch runs the check (GET .../check). */
export function useCheckSettings(workspaceId: string | undefined) {
  return useQuery({
    queryKey: settingsQueryKeys.check(workspaceId ?? ""),
    queryFn: () => checkSettings(workspaceId as string),
    enabled: false,
  });
}

/** Inspirations, newest first, optionally filtered by kind / keyword. */
export function useInspirations(
  workspaceId: string | undefined,
  kind?: string,
  keyword?: string,
) {
  return useQuery({
    queryKey: settingsQueryKeys.inspirations(
      workspaceId ?? "",
      kind,
      keyword,
    ),
    queryFn: () => listInspirations(workspaceId as string, { kind, keyword }),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}

/** One inspiration with its source (GET .../inspirations/{id}). */
export function useInspiration(
  workspaceId: string | undefined,
  inspirationId: string | null,
) {
  return useQuery({
    queryKey: settingsQueryKeys.inspiration(
      workspaceId ?? "",
      inspirationId ?? "",
    ),
    queryFn: () =>
      getInspiration(workspaceId as string, inspirationId as string),
    enabled:
      inspirationId !== null &&
      workspaceId !== undefined &&
      workspaceId !== "",
  });
}

/** Add one inspiration snippet (POST /works/{id}/inspirations). */
export function useCreateInspiration(
  workspaceId: string | undefined,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: InspirationAddBody) =>
      createInspiration(workspaceId as string, body),
    onSuccess: () => {
      if (workspaceId !== undefined) {
        void queryClient.invalidateQueries({
          queryKey: ["works", workspaceId, "inspirations"],
        });
      }
    },
  });
}

/** Remove one inspiration (DELETE .../inspirations/{id}). */
export function useDeleteInspiration(
  workspaceId: string | undefined,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (inspirationId: string) =>
      deleteInspiration(workspaceId as string, inspirationId),
    onSuccess: () => {
      if (workspaceId !== undefined) {
        void queryClient.invalidateQueries({
          queryKey: ["works", workspaceId, "inspirations"],
        });
      }
    },
  });
}
