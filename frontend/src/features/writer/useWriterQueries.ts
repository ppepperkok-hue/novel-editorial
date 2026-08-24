import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createAuthorDraft,
  generateDraft,
  getDraft,
  getDraftDiff,
  getDrafts,
  getReviews,
  reviseDraft,
  saveDraftContent,
  type DraftGenerateBody,
  type DraftNewBody,
  type DraftReviseBody,
  type DraftSaveBody,
} from "../../api/client";

export const writerQueryKeys = {
  drafts: (workspaceId: string) =>
    ["works", workspaceId, "drafts"] as const,
  detail: (workspaceId: string, draftId: string) =>
    ["works", workspaceId, "drafts", draftId] as const,
  diff: (
    workspaceId: string,
    draftId: string,
    versionA: number,
    versionB: number,
  ) =>
    [
      "works",
      workspaceId,
      "drafts",
      draftId,
      "diff",
      versionA,
      versionB,
    ] as const,
  reviews: (workspaceId: string, draftId: string) =>
    ["works", workspaceId, "reviews", draftId] as const,
};

/** Draft list for one workspace (GET /works/{id}/drafts). */
export function useDrafts(workspaceId: string | undefined) {
  return useQuery({
    queryKey: writerQueryKeys.drafts(workspaceId ?? ""),
    queryFn: () => getDrafts(workspaceId as string),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}

/** One draft with its full version history (GET /works/{id}/drafts/{draft_id}). */
export function useDraftDetail(
  workspaceId: string | undefined,
  draftId: string | null,
) {
  return useQuery({
    queryKey: writerQueryKeys.detail(workspaceId ?? "", draftId ?? ""),
    queryFn: () => getDraft(workspaceId as string, draftId as string),
    enabled:
      workspaceId !== undefined &&
      workspaceId !== "" &&
      draftId !== null &&
      draftId !== "",
  });
}

/** Unified diff between two draft versions (GET .../diff, plain text). */
export function useDraftDiff(
  workspaceId: string | undefined,
  draftId: string | null,
  versionA: number | null,
  versionB: number | null,
) {
  return useQuery({
    queryKey: writerQueryKeys.diff(
      workspaceId ?? "",
      draftId ?? "",
      versionA ?? 0,
      versionB ?? 0,
    ),
    queryFn: () =>
      getDraftDiff(
        workspaceId as string,
        draftId as string,
        { version_a: versionA as number, version_b: versionB as number },
      ),
    enabled:
      workspaceId !== undefined &&
      workspaceId !== "" &&
      draftId !== null &&
      draftId !== "" &&
      versionA !== null &&
      versionB !== null,
  });
}

/** Review comments on one draft (GET /works/{id}/reviews?draft_id=). */
export function useReviews(
  workspaceId: string | undefined,
  draftId: string | null,
) {
  return useQuery({
    queryKey: writerQueryKeys.reviews(workspaceId ?? "", draftId ?? ""),
    queryFn: () => getReviews(workspaceId as string, draftId as string),
    enabled:
      workspaceId !== undefined &&
      workspaceId !== "" &&
      draftId !== null &&
      draftId !== "",
  });
}

/** Create an empty author-owned draft (POST /works/{id}/drafts/new). */
export function useCreateAuthorDraft(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DraftNewBody) =>
      createAuthorDraft(workspaceId as string, body),
    onSuccess: () => {
      if (workspaceId !== undefined) {
        void queryClient.invalidateQueries({
          queryKey: writerQueryKeys.drafts(workspaceId),
        });
      }
    },
  });
}

/** Generate a draft version via the LLM (POST /works/{id}/drafts). */
export function useGenerateDraft(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DraftGenerateBody) =>
      generateDraft(workspaceId as string, body),
    onSuccess: () => {
      if (workspaceId !== undefined) {
        void queryClient.invalidateQueries({
          queryKey: writerQueryKeys.drafts(workspaceId),
        });
      }
    },
  });
}

/** Save an author-written version (PUT .../content); refreshes list + detail. */
export function useSaveDraft(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { draftId: string; body: DraftSaveBody }) =>
      saveDraftContent(workspaceId as string, vars.draftId, vars.body),
    onSuccess: (_data, vars) => {
      if (workspaceId !== undefined) {
        void queryClient.invalidateQueries({
          queryKey: writerQueryKeys.drafts(workspaceId),
        });
        void queryClient.invalidateQueries({
          queryKey: writerQueryKeys.detail(workspaceId, vars.draftId),
        });
      }
    },
  });
}

/** Re-generate a draft as a new version (POST .../revise); refreshes list + detail. */
export function useReviseDraft(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { draftId: string; body: DraftReviseBody }) =>
      reviseDraft(workspaceId as string, vars.draftId, vars.body),
    onSuccess: (_data, vars) => {
      if (workspaceId !== undefined) {
        void queryClient.invalidateQueries({
          queryKey: writerQueryKeys.drafts(workspaceId),
        });
        void queryClient.invalidateQueries({
          queryKey: writerQueryKeys.detail(workspaceId, vars.draftId),
        });
      }
    },
  });
}
