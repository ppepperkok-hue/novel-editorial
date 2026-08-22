import { useCallback, useEffect, useRef, useState } from "react";

import {
  getConfig,
  getGlobalEvents,
  getOverview,
  getPending,
  type EditorialEvent,
  type Overview,
  type OverviewItem,
  type PendingDraft,
} from "./api/client";
import EventItem from "./components/EventItem";
import PendingDraftItem from "./components/PendingDraftItem";
import { PanelWindow } from "./components/StateViews";
import WorkspaceCard from "./components/WorkspaceCard";
import WorkspaceDrawer from "./components/WorkspaceDrawer";
import { usePolling } from "./hooks/usePolling";

const DEFAULT_POLL_INTERVAL_MS = 3000;

interface PendingGroup {
  workspaceId: string;
  workspaceTitle: string;
  drafts: PendingDraft[];
}

interface PendingState {
  groups: PendingGroup[];
  failedWorkspaces: number;
}

export default function App() {
  const [pollIntervalMs, setPollIntervalMs] = useState(DEFAULT_POLL_INTERVAL_MS);
  const [configError, setConfigError] = useState<Error | null>(null);
  const [configAttempt, setConfigAttempt] = useState(0);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(
    null,
  );

  const loadConfig = useCallback(() => {
    setConfigAttempt((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    getConfig()
      .then((config) => {
        if (cancelled) {
          return;
        }
        setPollIntervalMs(config.panel_poll_interval * 1000);
        setConfigError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return;
        }
        setConfigError(err instanceof Error ? err : new Error(String(err)));
      });
    return () => {
      cancelled = true;
    };
  }, [configAttempt]);

  const overview = usePolling(getOverview, pollIntervalMs);
  const events = usePolling(getGlobalEvents, pollIntervalMs);

  const overviewRef = useRef<Overview | null>(overview.data);
  overviewRef.current = overview.data;

  const [pending, setPending] = useState<PendingState | null>(null);
  const [pendingLoading, setPendingLoading] = useState(false);
  const [pendingError, setPendingError] = useState<Error | null>(null);
  const [pendingAttempt, setPendingAttempt] = useState(0);

  const reloadPending = useCallback(() => {
    setPendingAttempt((value) => value + 1);
  }, []);

  const handleDecided = useCallback(() => {
    overview.reload();
    events.reload();
    reloadPending();
  }, [events, overview, reloadPending]);

  useEffect(() => {
    const current = overviewRef.current;
    if (current === null) {
      return;
    }
    let cancelled = false;
    setPendingLoading(true);
    setPendingError(null);
    void Promise.allSettled(
      current.overviews.map((item) => getPending(item.workspace_id)),
    ).then((results) => {
      if (cancelled) {
        return;
      }
      const groups: PendingGroup[] = [];
      let failedWorkspaces = 0;
      results.forEach((result, index) => {
        const workspace = current.overviews[index];
        if (result.status === "fulfilled") {
          if (result.value.length > 0) {
            groups.push({
              workspaceId: workspace.workspace_id,
              workspaceTitle: workspace.title,
              drafts: result.value,
            });
          }
        } else {
          failedWorkspaces += 1;
        }
      });
      setPending({ groups, failedWorkspaces });
      setPendingLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [overview.data, pendingAttempt]);

  const openWorkspaceFromEvent = useCallback((event: EditorialEvent) => {
    setSelectedWorkspaceId(event.workspace_id);
  }, []);

  const selectedWorkspace: OverviewItem | null =
    overview.data?.overviews.find(
      (item) => item.workspace_id === selectedWorkspaceId,
    ) ?? null;

  const pendingWindowState = overview.error
    ? "error"
    : overview.data === null || pendingLoading || pending === null
      ? "loading"
      : pendingError
        ? "error"
        : pending.groups.length === 0
          ? "empty"
          : "ready";

  return (
    <div className="app">
      <header className="app-header">
        <h1>Novel Editorial 面板</h1>
      </header>
      <main className="panel-grid">
        <PanelWindow
          title="跨作品概览"
          state={
            overview.error
              ? "error"
              : overview.data === null
                ? "loading"
                : overview.data.overviews.length === 0
                  ? "empty"
                  : "ready"
          }
          source="/overview"
          message={overview.error?.message}
          onRetry={overview.reload}
          emptyTitle="还没有作品"
          emptyHint="在 CLI 里创建第一部作品，它就会出现在这里"
          dataTestId="panel-overview"
        >
          <ul className="workspace-grid">
            {overview.data?.overviews.map((item) => (
              <li key={item.workspace_id}>
                <WorkspaceCard
                  item={item}
                  selected={item.workspace_id === selectedWorkspaceId}
                  onClick={() => setSelectedWorkspaceId(item.workspace_id)}
                />
              </li>
            ))}
          </ul>
        </PanelWindow>

        <PanelWindow
          title="事件流"
          state={
            events.error
              ? "error"
              : events.data === null
                ? "loading"
                : events.data.events.length === 0
                  ? "empty"
                  : "ready"
          }
          source="/events"
          message={events.error?.message}
          onRetry={events.reload}
          emptyTitle="暂无事件"
          emptyHint="编辑部还没有动静，先去写点东西吧"
          dataTestId="panel-events"
        >
          <ul className="event-list">
            {events.data?.events.map((event) => (
              <EventItem
                key={event.id}
                event={event}
                onClick={() => openWorkspaceFromEvent(event)}
              />
            ))}
          </ul>
          {events.data !== null && events.data.skipped > 0 ? (
            <p className="partial-failure">
              有 {events.data.skipped} 部作品的事件读取失败（已跳过）
            </p>
          ) : null}
        </PanelWindow>

        <PanelWindow
          title="待拍板"
          state={pendingWindowState}
          source="/works/{id}/pending"
          message={
            pendingError?.message ??
            (overview.error ? "概览未就绪，无法聚合待拍板" : undefined)
          }
          onRetry={() => {
            overview.reload();
            reloadPending();
          }}
          emptyTitle="没有待拍板"
          emptyHint="所有草稿都已处理，轻松一下"
          dataTestId="panel-pending"
        >
          <ul className="pending-list">
            {pending?.groups.map((group) =>
              group.drafts.map((draft) => (
                <PendingDraftItem
                  key={`${group.workspaceId}-${draft.id}`}
                  workspaceId={group.workspaceId}
                  workspaceTitle={group.workspaceTitle}
                  draft={draft}
                  onOpenWorkspace={() => setSelectedWorkspaceId(group.workspaceId)}
                  onDecided={handleDecided}
                />
              )),
            )}
          </ul>
          {pending !== null && pending.failedWorkspaces > 0 ? (
            <p className="partial-failure">
              {pending.failedWorkspaces} 部作品的待拍板读取失败（已跳过）
            </p>
          ) : null}
        </PanelWindow>
      </main>
      <footer className="status-line" data-testid="status-line" aria-live="polite">
        {configError ? (
          <>
            配置读取失败（GET /config），轮询使用默认{" "}
            {DEFAULT_POLL_INTERVAL_MS / 1000} 秒
            <button type="button" className="retry-button" onClick={loadConfig}>
              重试配置
            </button>
          </>
        ) : (
          <>轮询间隔：{pollIntervalMs / 1000} 秒</>
        )}
      </footer>
      {selectedWorkspace !== null ? (
        <WorkspaceDrawer
          key={selectedWorkspace.workspace_id}
          workspace={selectedWorkspace}
          onClose={() => setSelectedWorkspaceId(null)}
        />
      ) : null}
    </div>
  );
}
