import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { listTalk, sendTalk, type TalkSendBody } from "../../api/client";

export const talkQueryKeys = {
  talk: (workspaceId: string) => ["works", workspaceId, "talk"] as const,
};

/** Conversation for one workspace (GET /works/{id}/talk). */
export function useTalk(workspaceId: string | undefined) {
  return useQuery({
    queryKey: talkQueryKeys.talk(workspaceId ?? ""),
    queryFn: () => listTalk(workspaceId as string),
    enabled: workspaceId !== undefined && workspaceId !== "",
  });
}

/**
 * Send one message (POST /works/{id}/talk). The list query is invalidated on
 * success so the new messages reappear with their CLI-aligned mark/line.
 */
export function useSendTalk(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: TalkSendBody) => sendTalk(workspaceId as string, body),
    onSuccess: () => {
      if (workspaceId !== undefined) {
        void queryClient.invalidateQueries({
          queryKey: talkQueryKeys.talk(workspaceId),
        });
      }
    },
  });
}
