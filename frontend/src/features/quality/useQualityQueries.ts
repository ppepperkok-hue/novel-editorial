import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  analyzeQualityFeedback,
  calibrateQuality,
  getDraftConsistency,
  getDrafts,
  getQualityCheck,
  getQualityExplain,
  getStyleDrift,
  learnStyle,
  type CorpusPathBody,
} from "../../api/client";

export const qualityQueryKeys = {
  drafts: (workspaceId: string) =>
    ["works", workspaceId, "quality", "drafts"] as const,
  check: (workspaceId: string, draftId: string) =>
    ["works", workspaceId, "quality", "check", draftId] as const,
  explain: (workspaceId: string, draftId: string) =>
    ["works", workspaceId, "quality", "explain", draftId] as const,
  consistency: (workspaceId: string, draftId: string) =>
    ["works", workspaceId, "quality", "consistency", draftId] as const,
  drift: (workspaceId: string) =>
    ["works", workspaceId, "style", "drift"] as const,
};

/** Draft summaries for the quality workbench draft selector (GET .../drafts). */
export function useQualityDrafts(workspaceId: string | undefined) {
  return useQuery({
    queryKey: qualityQueryKeys.drafts(workspaceId ?? ""),
    queryFn: () => getDrafts(workspaceId as string),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}

/** AI-flavor quality gate report for one draft (GET .../quality/check). */
export function useQualityCheck(
  workspaceId: string | undefined,
  draftId: string | null,
) {
  return useQuery({
    queryKey: qualityQueryKeys.check(workspaceId ?? "", draftId ?? ""),
    queryFn: () => getQualityCheck(workspaceId as string, draftId as string),
    enabled:
      draftId !== null &&
      workspaceId !== undefined &&
      workspaceId !== "",
  });
}

/** AI-flavor localization + rewrite suggestions (GET .../quality/explain). */
export function useQualityExplain(
  workspaceId: string | undefined,
  draftId: string | null,
) {
  return useQuery({
    queryKey: qualityQueryKeys.explain(workspaceId ?? "", draftId ?? ""),
    queryFn: () => getQualityExplain(workspaceId as string, draftId as string),
    enabled:
      draftId !== null &&
      workspaceId !== undefined &&
      workspaceId !== "",
  });
}

/** Contradiction report against settings/threads (GET .../consistency). */
export function useDraftConsistency(
  workspaceId: string | undefined,
  draftId: string | null,
) {
  return useQuery({
    queryKey: qualityQueryKeys.consistency(
      workspaceId ?? "",
      draftId ?? "",
    ),
    queryFn: () =>
      getDraftConsistency(workspaceId as string, draftId as string),
    enabled:
      draftId !== null &&
      workspaceId !== undefined &&
      workspaceId !== "",
  });
}

/** Cross-chapter style drift report (GET .../style/drift). */
export function useStyleDrift(workspaceId: string | undefined) {
  return useQuery({
    queryKey: qualityQueryKeys.drift(workspaceId ?? ""),
    queryFn: () => getStyleDrift(workspaceId as string),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}

/** Corpus calibration; ``apply`` writes the config threshold (POST .../calibrate). */
export function useCalibrateQuality() {
  return useMutation({
    mutationFn: (body: CorpusPathBody) => calibrateQuality(body),
  });
}

/** Trial-reader feedback alignment; ``apply`` writes config (POST .../feedback). */
export function useQualityFeedback() {
  return useMutation({
    mutationFn: (body: CorpusPathBody) => analyzeQualityFeedback(body),
  });
}

/** Learn a style description from reference texts (POST .../style/learn). */
export function useLearnStyle(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CorpusPathBody) =>
      learnStyle(workspaceId as string, body),
    onSuccess: () => {
      if (workspaceId !== undefined) {
        void queryClient.invalidateQueries({
          queryKey: ["works", workspaceId, "style"],
        });
      }
    },
  });
}
