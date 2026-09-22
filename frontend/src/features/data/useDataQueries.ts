import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getConfig,
  updateConfig,
  type ConfigWriteBody,
} from "../../api/client";

export const dataQueryKeys = {
  config: ["config"] as const,
};

/** Full non-sensitive config snapshot (GET /config). */
export function useConfigSnapshot() {
  return useQuery({
    queryKey: dataQueryKeys.config,
    queryFn: getConfig,
  });
}

/** Write one whitelisted config key (PUT /config), then refresh the snapshot. */
export function useUpdateConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ConfigWriteBody) => updateConfig(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: dataQueryKeys.config });
    },
  });
}
