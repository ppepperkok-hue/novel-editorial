import { PanelWindow, type WindowState } from "./StateViews";

/**
 * Plain-text report panel with the shared three-state baseline.
 *
 * Consumes a TanStack Query result (or a structurally compatible object) and
 * renders exactly one state: loading skeleton, empty guidance, inline error
 * with retry, or the report as monospace ``pre`` that preserves the CLI byte
 * format. Pass ``disabled`` to hold the panel in the empty state until a
 * prerequisite (for example a selected draft) exists.
 */
export interface ReportQuery {
  isPending: boolean;
  isError: boolean;
  error: Error | null;
  data: string | undefined;
  refetch: () => Promise<unknown>;
}

export function TextReportPanel({
  title,
  source,
  query,
  disabled,
  emptyTitle,
  emptyHint,
  dataTestId,
}: {
  title: string;
  source: string;
  query: ReportQuery;
  disabled: boolean;
  emptyTitle: string;
  emptyHint?: string;
  dataTestId: string;
}) {
  const state: WindowState = disabled
    ? "empty"
    : query.isPending
      ? "loading"
      : query.isError
        ? "error"
        : query.data === undefined || query.data === ""
          ? "empty"
          : "ready";
  return (
    <PanelWindow
      title={title}
      state={state}
      source={source}
      message={query.error?.message}
      onRetry={() => void query.refetch()}
      emptyTitle={emptyTitle}
      emptyHint={emptyHint}
      dataTestId={dataTestId}
    >
      <pre className="plain-output" data-testid={`${dataTestId}-report`}>
        {query.data}
      </pre>
    </PanelWindow>
  );
}
