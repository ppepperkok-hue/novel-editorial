import { useCallback, useEffect, useState } from "react";

import {
  getDraft,
  getDrafts,
  getInspect,
  getLog,
  getReviews,
  getStructure,
  getStyle,
  type DraftDetail,
  type DraftSummary,
  type OverviewItem,
  type Review,
  type StructureNode,
} from "../api/client";
import { formatDateTime } from "../utils/format";
import { EmptyState, ErrorState, SkeletonRows } from "./StateViews";

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
}

function useAsyncOnce<T>(
  fetcher: () => Promise<T>,
  enabled = true,
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetcher()
      .then((result) => {
        if (cancelled) {
          return;
        }
        setData(result);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return;
        }
        setError(err instanceof Error ? err : new Error(String(err)));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [attempt, enabled, fetcher]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);
  return { data, loading, error, reload };
}

const TABS = [
  { key: "inspect", label: "检索" },
  { key: "drafts", label: "草稿与版本" },
  { key: "reviews", label: "意见" },
  { key: "log", label: "日志" },
  { key: "settings", label: "设定·结构·风格" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

function InspectTab({ workspaceId }: { workspaceId: string }) {
  const [keyword, setKeyword] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const search = useCallback(async () => {
    const trimmed = keyword.trim();
    if (!trimmed) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setResult(await getInspect(workspaceId, trimmed));
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, [keyword, workspaceId]);

  return (
    <div className="drawer-tab">
      <form
        className="inspect-form"
        onSubmit={(event) => {
          event.preventDefault();
          void search();
        }}
      >
        <input
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="关键词，例如：冷峻"
          aria-label="检索关键词"
        />
        <button type="submit" disabled={!keyword.trim()}>
          检索
        </button>
      </form>
      {error ? (
        <ErrorState
          source={`/works/${workspaceId}/inspect`}
          message={error.message}
          onRetry={() => void search()}
        />
      ) : null}
      {loading ? <SkeletonRows count={4} /> : null}
      {!error && !loading && result === null ? (
        <EmptyState
          title="输入关键词开始检索"
          hint="搜索记忆包、草稿、意见、设定等全部层级"
        />
      ) : null}
      {!error && !loading && result !== null ? (
        <pre className="plain-output" data-testid="inspect-result">
          {result}
        </pre>
      ) : null}
    </div>
  );
}

function DraftVersionList({ detail }: { detail: DraftDetail }) {
  return (
    <ol className="version-list" data-testid="draft-versions">
      {detail.versions.map((version) => (
        <li key={version.version} className="version-item">
          <p className="version-head">
            v{version.version} · {version.reason || "无说明"} ·{" "}
            {formatDateTime(version.created_at)}
          </p>
          <pre className="plain-output">{version.content}</pre>
        </li>
      ))}
    </ol>
  );
}

function DraftsTab({
  workspaceId,
  drafts,
}: {
  workspaceId: string;
  drafts: AsyncState<DraftSummary[]>;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const detail = useAsyncOnce(
    useCallback(
      () => getDraft(workspaceId, selectedId as string),
      [workspaceId, selectedId],
    ),
    selectedId !== null,
  );

  if (drafts.loading) {
    return <SkeletonRows count={3} />;
  }
  if (drafts.error) {
    return (
      <ErrorState
        source={`/works/${workspaceId}/drafts`}
        message={drafts.error.message}
        onRetry={drafts.reload}
      />
    );
  }
  if (drafts.data === null || drafts.data.length === 0) {
    return <EmptyState title="还没有草稿" hint="新草稿诞生后会出现在这里" />;
  }

  const selected = drafts.data.find((item) => item.id === selectedId);
  return (
    <div className="drawer-tab">
      <ul className="draft-list" data-testid="draft-list">
        {drafts.data.map((draft) => (
          <li key={draft.id}>
            <button
              type="button"
              className={`draft-list-item${
                draft.id === selectedId ? " draft-list-item--selected" : ""
              }`}
              onClick={() => setSelectedId(draft.id)}
            >
              <span className="draft-list-title">{draft.title}</span>
              <span className="draft-list-meta">
                {draft.status} · v{draft.current_version} ·{" "}
                {formatDateTime(draft.updated_at)}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {selected === undefined ? (
        <EmptyState title="选择一篇草稿查看版本" />
      ) : null}
      {selected !== undefined && detail.loading ? <SkeletonRows count={3} /> : null}
      {selected !== undefined && detail.error ? (
        <ErrorState
          source={`/works/${workspaceId}/drafts/${selectedId}`}
          message={detail.error.message}
          onRetry={detail.reload}
        />
      ) : null}
      {selected !== undefined && detail.data !== null ? (
        <DraftVersionList detail={detail.data} />
      ) : null}
    </div>
  );
}

function ReviewsTab({
  workspaceId,
  drafts,
}: {
  workspaceId: string;
  drafts: AsyncState<DraftSummary[]>;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const effectiveId = selectedId ?? drafts.data?.[0]?.id ?? null;
  const reviews = useAsyncOnce(
    useCallback(
      () => getReviews(workspaceId, effectiveId as string),
      [workspaceId, effectiveId],
    ),
    effectiveId !== null,
  );

  if (drafts.loading) {
    return <SkeletonRows count={3} />;
  }
  if (drafts.error) {
    return (
      <ErrorState
        source={`/works/${workspaceId}/drafts`}
        message={drafts.error.message}
        onRetry={drafts.reload}
      />
    );
  }
  if (drafts.data === null || drafts.data.length === 0) {
    return <EmptyState title="还没有草稿" hint="先有草稿，才会有意见" />;
  }

  return (
    <div className="drawer-tab">
      <label className="review-draft-label" htmlFor="review-draft-select">
        草稿
      </label>
      <select
        id="review-draft-select"
        className="review-draft-select"
        value={effectiveId ?? ""}
        onChange={(event) => setSelectedId(event.target.value)}
        data-testid="review-draft-select"
      >
        {drafts.data.map((draft) => (
          <option key={draft.id} value={draft.id}>
            {draft.title}（v{draft.current_version}）
          </option>
        ))}
      </select>
      {effectiveId === null ? (
        <EmptyState title="选择一篇草稿查看意见" />
      ) : null}
      {effectiveId !== null && reviews.loading ? <SkeletonRows count={3} /> : null}
      {effectiveId !== null && reviews.error ? (
        <ErrorState
          source={`/works/${workspaceId}/reviews?draft_id=${effectiveId}`}
          message={reviews.error.message}
          onRetry={reviews.reload}
        />
      ) : null}
      {effectiveId !== null && reviews.data !== null &&
      reviews.data.length === 0 ? (
        <EmptyState title="这篇草稿还没有意见" hint="审稿伙伴还没开口" />
      ) : null}
      {effectiveId !== null && reviews.data !== null &&
      reviews.data.length > 0 ? (
        <ul className="review-list" data-testid="review-list">
          {reviews.data.map((review: Review) => (
            <li key={review.id} className="review-item">
              <p className="review-head">
                {review.actor}（{review.role}） · {formatDateTime(review.created_at)}
              </p>
              <p className="review-content">{review.content}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function LogTab({ workspaceId }: { workspaceId: string }) {
  const log = useAsyncOnce(useCallback(() => getLog(workspaceId), [workspaceId]));

  if (log.loading) {
    return <SkeletonRows count={4} />;
  }
  if (log.error) {
    return (
      <ErrorState
        source={`/works/${workspaceId}/log`}
        message={log.error.message}
        onRetry={log.reload}
      />
    );
  }
  if (log.data === null || log.data.trim() === "") {
    return <EmptyState title="日志还是空的" hint="工作流还没有留下痕迹" />;
  }
  return (
    <pre className="plain-output" data-testid="workspace-log">
      {log.data}
    </pre>
  );
}

function SettingsTab({
  workspace,
}: {
  workspace: OverviewItem;
}) {
  const style = useAsyncOnce(
    useCallback(() => getStyle(workspace.workspace_id), [workspace.workspace_id]),
  );
  const structure = useAsyncOnce(
    useCallback(
      () => getStructure(workspace.workspace_id),
      [workspace.workspace_id],
    ),
  );

  return (
    <div className="drawer-tab">
      <section className="settings-block" data-testid="workspace-settings">
        <h4>设定</h4>
        <p>类型：{workspace.genre || "未设定"}</p>
        <p>状态：{workspace.status}</p>
        <p>创建时间：{formatDateTime(workspace.created_at)}</p>
      </section>
      <section className="settings-block" data-testid="workspace-style">
        <h4>风格</h4>
        {style.loading ? <SkeletonRows count={2} /> : null}
        {style.error ? (
          <ErrorState
            source={`/works/${workspace.workspace_id}/style`}
            message={style.error.message}
            onRetry={style.reload}
          />
        ) : null}
        {style.data !== null ? (
          <div className="style-anchor">
            <p>描述：{style.data.description || "未设定"}</p>
            <p>违禁词：{style.data.forbidden_words || "无"}</p>
          </div>
        ) : null}
      </section>
      <section className="settings-block" data-testid="workspace-structure">
        <h4>结构</h4>
        {structure.loading ? <SkeletonRows count={2} /> : null}
        {structure.error ? (
          <ErrorState
            source={`/works/${workspace.workspace_id}/structure`}
            message={structure.error.message}
            onRetry={structure.reload}
          />
        ) : null}
        {structure.data !== null && structure.data.length === 0 ? (
          <EmptyState title="还没有结构节点" />
        ) : null}
        {structure.data !== null && structure.data.length > 0 ? (
          <ul className="structure-list" data-testid="structure-list">
            {structure.data.map((node: StructureNode) => (
              <li key={node.id} className="structure-item">
                <span className="structure-kind">{node.kind}</span>
                <span className="structure-title">{node.title}</span>
                <span className="structure-status">{node.status}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  );
}

interface WorkspaceDrawerProps {
  workspace: OverviewItem;
  onClose: () => void;
}

export default function WorkspaceDrawer({
  workspace,
  onClose,
}: WorkspaceDrawerProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("inspect");
  const drafts = useAsyncOnce(
    useCallback(
      () => getDrafts(workspace.workspace_id),
      [workspace.workspace_id],
    ),
  );

  return (
    <aside
      className="drawer"
      data-testid="workspace-drawer"
      aria-label={`作品穿透：${workspace.title}`}
    >
      <header className="drawer-header">
        <div className="drawer-heading">
          <h3>{workspace.title}</h3>
          <p className="drawer-subtitle">
            {workspace.genre || "未设定类型"} · 状态：{workspace.status}
          </p>
        </div>
        <button
          type="button"
          className="drawer-close"
          onClick={onClose}
          aria-label="关闭抽屉"
        >
          ×
        </button>
      </header>
      <nav className="drawer-tabs" role="tablist" aria-label="穿透分层">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.key}
            className={`drawer-tab-button${
              activeTab === tab.key ? " drawer-tab-button--active" : ""
            }`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      <div className="drawer-content" role="tabpanel">
        {activeTab === "inspect" ? (
          <InspectTab workspaceId={workspace.workspace_id} />
        ) : null}
        {activeTab === "drafts" ? (
          <DraftsTab workspaceId={workspace.workspace_id} drafts={drafts} />
        ) : null}
        {activeTab === "reviews" ? (
          <ReviewsTab workspaceId={workspace.workspace_id} drafts={drafts} />
        ) : null}
        {activeTab === "log" ? (
          <LogTab workspaceId={workspace.workspace_id} />
        ) : null}
        {activeTab === "settings" ? <SettingsTab workspace={workspace} /> : null}
      </div>
    </aside>
  );
}
