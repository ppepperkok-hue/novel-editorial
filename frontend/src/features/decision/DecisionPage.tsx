import { useCallback } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import EventStreamStatus from "../../components/EventStreamStatus";
import PendingDraftItem from "../../components/PendingDraftItem";
import {
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "../../components/StateViews";
import { useEventStream } from "../../hooks/useEventStream";
import { useWorkspaceSelection } from "../../hooks/useWorkspaceSelection";
import { usePending } from "./useDecisionQueries";

/**
 * Decision workbench: drafts awaiting the author's call (accept / reject /
 * note), with two-step confirmation and a live SSE connection so new pending
 * drafts appear as they arrive. Success refreshes every workspace-scoped
 * query (pending, drafts, workspace detail) so CLI and UI stay in sync.
 */
export default function DecisionPage() {
  const { workspaceId } = useParams();
  const workspace = useWorkspaceSelection(workspaceId);
  const pending = usePending(workspaceId);
  const stream = useEventStream(workspaceId);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const handleDecided = useCallback(() => {
    if (workspaceId !== undefined && workspaceId !== "") {
      void queryClient.invalidateQueries({
        queryKey: ["works", workspaceId],
      });
    }
  }, [queryClient, workspaceId]);

  return (
    <section className="decision-page" data-testid="decision-page">
      <header className="page-header">
        <h2>拍板</h2>
        <div className="workspace-toolbar">
          <EventStreamStatus status={stream.status} notice={stream.notice} />
          <Link className="text-link" to={`/works/${workspaceId ?? ""}`}>
            返回作品
          </Link>
        </div>
      </header>
      <section className="panel decision-panel" data-testid="decision-panel">
        <header className="panel-header">
          <h3>待拍板草稿</h3>
        </header>
        <div className="panel-body">
          {pending.isPending ? <SkeletonRows count={3} /> : null}
          {pending.isError ? (
            <ErrorState
              source={`/works/${workspaceId ?? ""}/pending`}
              message={pending.error.message}
              onRetry={() => void pending.refetch()}
            />
          ) : null}
          {pending.isSuccess && pending.data.length === 0 ? (
            <EmptyState
              title="没有待拍板"
              hint="所有草稿都已处理，轻松一下"
            />
          ) : null}
          {pending.isSuccess && pending.data.length > 0 ? (
            <ul className="pending-list" data-testid="decision-pending-list">
              {pending.data.map((draft) => (
                <PendingDraftItem
                  key={draft.id}
                  workspaceId={workspaceId ?? ""}
                  workspaceTitle={workspace.data?.title ?? ""}
                  draft={draft}
                  onOpenWorkspace={() =>
                    navigate(`/works/${workspaceId ?? ""}/writer`)
                  }
                  onDecided={handleDecided}
                />
              ))}
            </ul>
          ) : null}
        </div>
      </section>
    </section>
  );
}
