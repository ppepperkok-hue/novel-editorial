import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createStructureNode,
  deleteStructureNode,
  getOutline,
  getStructure,
  moveStructureNode,
  patchStructureNode,
  writeOutline,
  type OutlineWriteBody,
  type StructureAddBody,
  type StructureMoveBody,
  type StructurePatchBody,
} from "../../api/client";

export const structureQueryKeys = {
  structure: (workspaceId: string) =>
    ["works", workspaceId, "structure"] as const,
  outline: (workspaceId: string) =>
    ["works", workspaceId, "outline"] as const,
};

/** Volume/chapter/section tree as a flat, parent-first list (GET .../structure). */
export function useStructure(workspaceId: string | undefined) {
  return useQuery({
    queryKey: structureQueryKeys.structure(workspaceId ?? ""),
    queryFn: () => getStructure(workspaceId as string),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}

function useInvalidateStructure(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return () => {
    if (workspaceId !== undefined) {
      void queryClient.invalidateQueries({
        queryKey: structureQueryKeys.structure(workspaceId),
      });
    }
  };
}

/** Add a structure node (POST /works/{id}/structure, like ``structure add``). */
export function useCreateStructureNode(
  workspaceId: string | undefined,
) {
  const invalidate = useInvalidateStructure(workspaceId);
  return useMutation({
    mutationFn: (body: StructureAddBody) =>
      createStructureNode(workspaceId as string, body),
    onSuccess: invalidate,
  });
}

/** Rename a node or set its status (PATCH .../structure/{node_id}). */
export function usePatchStructureNode(
  workspaceId: string | undefined,
) {
  const invalidate = useInvalidateStructure(workspaceId);
  return useMutation({
    mutationFn: ({
      nodeId,
      body,
    }: {
      nodeId: string;
      body: StructurePatchBody;
    }) => patchStructureNode(workspaceId as string, nodeId, body),
    onSuccess: invalidate,
  });
}

/** Move a node to the root or under another parent (POST .../move). */
export function useMoveStructureNode(
  workspaceId: string | undefined,
) {
  const invalidate = useInvalidateStructure(workspaceId);
  return useMutation({
    mutationFn: ({
      nodeId,
      body,
    }: {
      nodeId: string;
      body: StructureMoveBody;
    }) => moveStructureNode(workspaceId as string, nodeId, body),
    onSuccess: invalidate,
  });
}

/** Remove a node and its whole subtree (DELETE .../structure/{node_id}). */
export function useDeleteStructureNode(
  workspaceId: string | undefined,
) {
  const invalidate = useInvalidateStructure(workspaceId);
  return useMutation({
    mutationFn: (nodeId: string) =>
      deleteStructureNode(workspaceId as string, nodeId),
    onSuccess: invalidate,
  });
}

/** Current outline version, or null when none (GET /works/{id}/outline). */
export function useOutline(workspaceId: string | undefined) {
  return useQuery({
    queryKey: structureQueryKeys.outline(workspaceId ?? ""),
    queryFn: () => getOutline(workspaceId as string),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}

/** Create (no reason) or revise (with reason) the outline (POST .../outline). */
export function useWriteOutline(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: OutlineWriteBody) =>
      writeOutline(workspaceId as string, body),
    onSuccess: () => {
      if (workspaceId !== undefined) {
        void queryClient.invalidateQueries({
          queryKey: structureQueryKeys.outline(workspaceId),
        });
      }
    },
  });
}
