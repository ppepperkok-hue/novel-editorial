import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  createWorkspace,
  getWorkspace,
  listTemplates,
  listWorks,
  type CreateWorkspaceBody,
} from "../../api/client";

export const worksQueryKeys = {
  all: ["works"] as const,
  detail: (workspaceId: string) => ["works", workspaceId] as const,
  templates: ["templates"] as const,
};

/** Works list (GET /works), cached by TanStack Query. */
export function useWorks() {
  return useQuery({ queryKey: worksQueryKeys.all, queryFn: listWorks });
}

/** One workspace with its band profile (GET /works/{id}); disabled without an id. */
export function useWorkspace(workspaceId: string | undefined) {
  return useQuery({
    queryKey: worksQueryKeys.detail(workspaceId ?? ""),
    queryFn: () => getWorkspace(workspaceId as string),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}

/** Preset editorial band templates (GET /templates). */
export function useTemplates() {
  return useQuery({ queryKey: worksQueryKeys.templates, queryFn: listTemplates });
}

/**
 * Create a workspace (POST /works). The create response is only a summary
 * (no band), so the detail cache is left for GET /works/{id} to fetch.
 */
export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateWorkspaceBody) => createWorkspace(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: worksQueryKeys.all });
    },
  });
}
