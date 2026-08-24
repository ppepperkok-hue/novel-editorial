import type { ReactNode } from "react";

/**
 * Three-state view baseline (shared across every workspace).
 *
 * Every data-driven component must render exactly one of:
 *
 * - loading: `SkeletonRows` (skeleton, not a spinner; keeps layout stable).
 * - empty: `EmptyState` (guiding copy, never a bare "no data").
 * - error: `ErrorState` (inline, with source path and a retry action).
 *
 * `PanelWindow` composes all three around a ready-state slot:
 *
 * ```tsx
 * <PanelWindow
 *   title="作品列表"
 *   state={query.isPending ? "loading" : query.isError ? "error" : query.data.length === 0 ? "empty" : "ready"}
 *   source="/works"
 *   message={query.error?.message}
 *   onRetry={() => void query.refetch()}
 *   emptyTitle="还没有作品"
 *   emptyHint="创建第一部作品"
 * >
 *   {query.data.map(...)}
 * </PanelWindow>
 * ```
 *
 * Props:
 * - `SkeletonRows`: `count` (rows to render, default 3). State: loading.
 * - `EmptyState`: `title` (required), `hint` (optional guidance). State: empty.
 * - `ErrorState`: `source` (API path shown to the user), `message` (detail),
 *   `onRetry` (retry callback). State: error.
 * - `PanelWindow`: `title`, `state` ("loading" | "empty" | "error" | "ready"),
 *   `source`, `message`, `onRetry`, `emptyTitle`, `emptyHint`, `dataTestId`,
 *   `children` (rendered only in the ready state).
 */

export function SkeletonRows({ count = 3 }: { count?: number }) {
  return (
    <div
      className="skeleton-list"
      data-testid="panel-state-loading"
      aria-busy="true"
    >
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="skeleton-row" />
      ))}
    </div>
  );
}

interface EmptyStateProps {
  title: string;
  hint?: string;
}

export function EmptyState({ title, hint }: EmptyStateProps) {
  return (
    <div className="panel-state panel-state--empty" data-testid="panel-state-empty">
      <p className="panel-state-title">{title}</p>
      {hint ? <p className="panel-state-hint">{hint}</p> : null}
    </div>
  );
}

interface ErrorStateProps {
  source: string;
  message?: string;
  onRetry: () => void;
}

export function ErrorState({ source, message, onRetry }: ErrorStateProps) {
  return (
    <div
      className="panel-state panel-state--error"
      data-testid="panel-state-error"
      role="alert"
    >
      <p className="panel-state-title">加载失败：{source}</p>
      {message ? <p className="panel-state-hint">{message}</p> : null}
      <button type="button" className="retry-button" onClick={onRetry}>
        重试
      </button>
    </div>
  );
}

export type WindowState = "loading" | "empty" | "error" | "ready";

interface PanelWindowProps {
  title: string;
  state: WindowState;
  source: string;
  message?: string;
  onRetry: () => void;
  emptyTitle?: string;
  emptyHint?: string;
  dataTestId?: string;
  children: ReactNode;
}

export function PanelWindow({
  title,
  state,
  source,
  message,
  onRetry,
  emptyTitle,
  emptyHint,
  dataTestId,
  children,
}: PanelWindowProps) {
  return (
    <section className="panel" data-testid={dataTestId}>
      <header className="panel-header">
        <h2>{title}</h2>
      </header>
      <div className="panel-body">
        {state === "loading" ? <SkeletonRows /> : null}
        {state === "empty" ? (
          <EmptyState title={emptyTitle ?? "暂无数据"} hint={emptyHint} />
        ) : null}
        {state === "error" ? (
          <ErrorState source={source} message={message} onRetry={onRetry} />
        ) : null}
        {state === "ready" ? children : null}
      </div>
    </section>
  );
}
