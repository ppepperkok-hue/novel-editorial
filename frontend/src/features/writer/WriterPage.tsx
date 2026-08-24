import { useEffect, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router-dom";

import type {
  DraftDetail,
  DraftVersion,
  DraftWriteResponse,
  Review,
} from "../../api/client";
import {
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "../../components/StateViews";
import { useWorkspaceSelection } from "../../hooks/useWorkspaceSelection";
import { formatDateTime } from "../../utils/format";
import {
  useCreateAuthorDraft,
  useDraftDetail,
  useDraftDiff,
  useDrafts,
  useGenerateDraft,
  useReviseDraft,
  useReviews,
  useSaveDraft,
} from "./useWriterQueries";

function latestVersion(detail: DraftDetail): DraftVersion | undefined {
  return detail.versions[detail.versions.length - 1];
}

function hasContent(detail: DraftDetail): boolean {
  const latest = latestVersion(detail);
  return latest !== undefined && latest.content.trim() !== "";
}

function statusLabel(detail: DraftDetail): string {
  if (detail.status === "draft") {
    return hasContent(detail) ? "待拍板 · 质量门通过" : "空稿（尚无内容）";
  }
  if (detail.status === "quality_failed") {
    return "质量门未通过";
  }
  if (detail.status === "accepted") {
    return "已接受";
  }
  if (detail.status === "rejected") {
    return "已拒绝";
  }
  return detail.status;
}

function DraftEditor({
  detail,
  saveMutation,
}: {
  detail: DraftDetail;
  saveMutation: ReturnType<typeof useSaveDraft>;
}) {
  const [content, setContent] = useState("");
  const [mode, setMode] = useState<"write" | "preview">("write");
  const [reason, setReason] = useState("");
  const [lastSaved, setLastSaved] = useState<DraftWriteResponse | null>(null);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);
  const dirtyRef = useRef(false);
  const lastHandledIdRef = useRef<string | null>(null);
  const latestText = latestVersion(detail)?.content ?? "";

  useEffect(() => {
    if (lastHandledIdRef.current !== detail.id) {
      // 切换草稿：整体重置编辑器状态
      lastHandledIdRef.current = detail.id;
      dirtyRef.current = false;
      setContent(latestText);
      setSyncNotice(null);
      setReason("");
      setLastSaved(null);
      setMode("write");
      return;
    }
    // 同一草稿的最新版本刷新：保留未保存的手改，否则同步最新正文
    if (dirtyRef.current) {
      setSyncNotice("检测到新版本，你未保存的修改仍在编辑器中");
      return;
    }
    setContent(latestText);
    setSyncNotice(null);
  }, [detail.id, latestText]);

  const canSave =
    content.trim() !== "" && !saveMutation.isPending && detail.status !== "accepted";

  function handleSave() {
    const text = content.trim();
    if (!text || saveMutation.isPending) {
      return;
    }
    saveMutation.mutate(
      {
        draftId: detail.id,
        body: {
          content: text,
          reason: reason.trim() || "作者修改",
        },
      },
      {
        onSuccess: (result) => {
          dirtyRef.current = false;
          setSyncNotice(null);
          setLastSaved(result);
        },
      },
    );
  }

  return (
    <section className="writer-editor" data-testid="draft-editor">
      <div className="editor-toolbar">
        <div className="editor-mode-switch" role="tablist" aria-label="编辑模式">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "write"}
            className={`editor-mode-button${
              mode === "write" ? " editor-mode-button--active" : ""
            }`}
            onClick={() => setMode("write")}
          >
            编辑
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "preview"}
            className={`editor-mode-button${
              mode === "preview" ? " editor-mode-button--active" : ""
            }`}
            onClick={() => setMode("preview")}
          >
            预览
          </button>
        </div>
        <span className="editor-version-hint">
          当前 v{detail.current_version}
        </span>
      </div>
      {syncNotice !== null ? (
        <div
          className="result-banner editor-sync-notice"
          data-testid="editor-sync-notice"
          role="status"
        >
          {syncNotice}
        </div>
      ) : null}
      {detail.versions.length === 0 ? (
        <div className="editor-empty" data-testid="draft-empty-v0">
          <EmptyState
            title="暂无内容"
            hint="这是空稿 v0，从第一行开始写，保存后生成 v1"
          />
        </div>
      ) : null}
      {mode === "write" ? (
        <textarea
          className="editor-textarea"
          value={content}
          onChange={(event) => {
            dirtyRef.current = true;
            setContent(event.target.value);
          }}
          placeholder="从第一行开始写正文…"
          aria-label="正文内容"
          data-testid="editor-textarea"
        />
      ) : (
        <div className="markdown-preview" data-testid="markdown-preview">
          {content.trim() === "" ? (
            <EmptyState title="暂无内容" hint="正文写好后会自动出现在这里" />
          ) : (
            <ReactMarkdown>{content}</ReactMarkdown>
          )}
        </div>
      )}
      <div className="editor-actions">
        <div className="form-field editor-reason">
          <label className="form-label" htmlFor="save-reason-input">
            修改说明（可留空）
          </label>
          <input
            id="save-reason-input"
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="作者修改"
            data-testid="save-reason-input"
          />
        </div>
        <button
          type="button"
          className="primary-button"
          disabled={!canSave}
          onClick={handleSave}
          data-testid="save-content-button"
        >
          {saveMutation.isPending ? "保存中…" : "手动保存"}
        </button>
      </div>
      {saveMutation.isError ? (
        <p className="inline-error" data-testid="save-error">
          {saveMutation.error.message}
        </p>
      ) : null}
      {lastSaved !== null ? (
        <div className="result-banner" data-testid="save-result" role="status">
          {lastSaved.awaiting_decision
            ? "已保存 · 质量门通过，等待拍板"
            : `已保存 · 当前状态：${lastSaved.status}`}
        </div>
      ) : null}
    </section>
  );
}

function ReviseForm({
  detail,
  reviseMutation,
}: {
  detail: DraftDetail;
  reviseMutation: ReturnType<typeof useReviseDraft>;
}) {
  const [reason, setReason] = useState("");
  const [lastRevised, setLastRevised] = useState<DraftWriteResponse | null>(null);

  useEffect(() => {
    setReason("");
    setLastRevised(null);
  }, [detail.id]);

  const hasLatestContent = hasContent(detail);
  const canRevise =
    reason.trim() !== "" &&
    !reviseMutation.isPending &&
    detail.status !== "accepted" &&
    hasLatestContent;

  function handleRevise() {
    const text = reason.trim();
    if (!text || reviseMutation.isPending) {
      return;
    }
    reviseMutation.mutate(
      {
        draftId: detail.id,
        body: { reason: text },
      },
      {
        onSuccess: (result) => setLastRevised(result),
      },
    );
  }

  return (
    <section className="writer-revise" data-testid="draft-revise">
      <h4>LLM 修订</h4>
      <div className="editor-actions">
        <div className="form-field editor-reason">
          <label className="form-label" htmlFor="revise-reason-input">
            修订理由
          </label>
          <input
            id="revise-reason-input"
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="例如：按审稿意见重写结尾"
            data-testid="revise-reason-input"
          />
        </div>
        <button
          type="button"
          className="primary-button"
          disabled={!canRevise}
          onClick={handleRevise}
          data-testid="revise-button"
        >
          {reviseMutation.isPending ? "修订中…" : "生成修订版"}
        </button>
      </div>
      {!hasLatestContent ? (
        <p className="form-hint" data-testid="revise-empty-hint">
          空稿暂无内容，先保存第一版再生成修订版
        </p>
      ) : null}
      {reviseMutation.isError ? (
        <p className="inline-error" data-testid="revise-error">
          {reviseMutation.error.message}
        </p>
      ) : null}
      {lastRevised !== null ? (
        <div className="result-banner" data-testid="revise-result" role="status">
          {lastRevised.awaiting_decision
            ? "修订完成 · 质量门通过，等待拍板"
            : `修订完成 · 当前状态：${lastRevised.status}`}
        </div>
      ) : null}
    </section>
  );
}

function DiffPanel({
  workspaceId,
  detail,
}: {
  workspaceId: string;
  detail: DraftDetail;
}) {
  const versions = detail.versions;
  const hasEnoughVersions = versions.length >= 2;
  const [versionA, setVersionA] = useState<number | null>(null);
  const [versionB, setVersionB] = useState<number | null>(null);

  useEffect(() => {
    if (versions.length >= 2) {
      const before = versions[versions.length - 2];
      const last = versions[versions.length - 1];
      setVersionA(before.version);
      setVersionB(last.version);
    } else {
      setVersionA(null);
      setVersionB(null);
    }
  }, [detail.id, versions.length]);

  const diff = useDraftDiff(workspaceId, detail.id, versionA, versionB);

  return (
    <section className="writer-diff" data-testid="draft-diff-panel">
      <h4>版本对比</h4>
      {!hasEnoughVersions ? (
        <p className="form-hint" data-testid="diff-disabled-hint">
          至少需要两个版本才能对比
        </p>
      ) : (
        <>
          <div className="diff-controls">
            <label className="form-label" htmlFor="diff-version-a">
              版本 A（旧）
            </label>
            <select
              id="diff-version-a"
              value={versionA ?? ""}
              onChange={(event) => setVersionA(Number(event.target.value))}
              data-testid="diff-version-a"
            >
              {versions.map((version) => (
                <option key={version.version} value={version.version}>
                  v{version.version}
                </option>
              ))}
            </select>
            <label className="form-label" htmlFor="diff-version-b">
              版本 B（新）
            </label>
            <select
              id="diff-version-b"
              value={versionB ?? ""}
              onChange={(event) => setVersionB(Number(event.target.value))}
              data-testid="diff-version-b"
            >
              {versions.map((version) => (
                <option key={version.version} value={version.version}>
                  v{version.version}
                </option>
              ))}
            </select>
          </div>
          {diff.isPending || versionA === null || versionB === null ? (
            <SkeletonRows count={4} />
          ) : null}
          {diff.isError ? (
            <ErrorState
              source={`/works/${workspaceId}/drafts/${detail.id}/diff`}
              message={diff.error.message}
              onRetry={() => void diff.refetch()}
            />
          ) : null}
          {diff.isSuccess ? (
            <pre className="diff-output" data-testid="diff-output">
              {diff.data}
            </pre>
          ) : null}
        </>
      )}
    </section>
  );
}

function VersionPanel({
  workspaceId,
  detail,
}: {
  workspaceId: string;
  detail: DraftDetail;
}) {
  const [viewedVersion, setViewedVersion] = useState<DraftVersion | null>(null);

  useEffect(() => {
    setViewedVersion(null);
  }, [detail.id]);

  const latest = latestVersion(detail);
  const viewed = viewedVersion ?? latest ?? null;

  return (
    <section className="writer-versions" data-testid="draft-versions-panel">
      <h4>版本</h4>
      {detail.versions.length === 0 ? (
        <EmptyState title="暂无版本" hint="保存正文后会生成第一个版本" />
      ) : (
        <ol className="version-list" data-testid="draft-versions">
          {detail.versions.map((version) => (
            <li key={version.version}>
              <button
                type="button"
                className={`version-item-button${
                  viewed?.version === version.version
                    ? " version-item-button--selected"
                    : ""
                }`}
                onClick={() => setViewedVersion(version)}
                data-testid="version-item"
              >
                <span className="version-item-title">v{version.version}</span>
                <span className="version-item-meta">
                  {version.actor} · {version.reason || "无说明"} ·{" "}
                  {formatDateTime(version.created_at)}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
      {viewed !== null ? (
        <div className="version-view" data-testid="version-content">
          <p className="version-view-head">
            v{viewed.version} 正文 · {viewed.actor}
          </p>
          {viewed.content.trim() === "" ? (
            <EmptyState title="暂无内容" />
          ) : (
            <div className="markdown-preview markdown-preview--readonly">
              <ReactMarkdown>{viewed.content}</ReactMarkdown>
            </div>
          )}
        </div>
      ) : null}
      <DiffPanel workspaceId={workspaceId} detail={detail} />
    </section>
  );
}

function ReviewsPanel({
  workspaceId,
  detail,
  reviews,
}: {
  workspaceId: string;
  detail: DraftDetail;
  reviews: ReturnType<typeof useReviews>;
}) {
  return (
    <section className="writer-reviews" data-testid="draft-reviews-panel">
      <h4>审稿意见</h4>
      {reviews.isPending ? <SkeletonRows count={2} /> : null}
      {reviews.isError ? (
        <ErrorState
          source={`/works/${workspaceId}/reviews?draft_id=${detail.id}`}
          message={reviews.error.message}
          onRetry={() => void reviews.refetch()}
        />
      ) : null}
      {reviews.isSuccess && reviews.data.length === 0 ? (
        <EmptyState title="这篇草稿还没有意见" hint="审稿伙伴还没开口" />
      ) : null}
      {reviews.isSuccess && reviews.data.length > 0 ? (
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
    </section>
  );
}

function DraftWorkbench({
  workspaceId,
  detail,
  reviews,
  saveMutation,
  reviseMutation,
}: {
  workspaceId: string;
  detail: DraftDetail;
  reviews: ReturnType<typeof useReviews>;
  saveMutation: ReturnType<typeof useSaveDraft>;
  reviseMutation: ReturnType<typeof useReviseDraft>;
}) {
  return (
    <section className="panel writer-workbench" data-testid="writer-workbench">
      <header className="panel-header writer-workbench-head">
        <h3>{detail.title}</h3>
        <span className="draft-status" data-testid="draft-status">
          {statusLabel(detail)}
        </span>
      </header>
      <div className="panel-body writer-grid">
        <div className="writer-editor-col">
          <DraftEditor detail={detail} saveMutation={saveMutation} />
          <ReviseForm detail={detail} reviseMutation={reviseMutation} />
        </div>
        <div className="writer-side-col">
          <VersionPanel workspaceId={workspaceId} detail={detail} />
          <ReviewsPanel
            workspaceId={workspaceId}
            detail={detail}
            reviews={reviews}
          />
        </div>
      </div>
    </section>
  );
}

export default function WriterPage() {
  const { workspaceId } = useParams();
  useWorkspaceSelection(workspaceId);
  const drafts = useDrafts(workspaceId);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [generateTitle, setGenerateTitle] = useState("");
  const createMutation = useCreateAuthorDraft(workspaceId);
  const generateMutation = useGenerateDraft(workspaceId);

  const effectiveId = selectedId ?? drafts.data?.[0]?.id ?? null;
  const detail = useDraftDetail(workspaceId, effectiveId);
  const reviews = useReviews(workspaceId, effectiveId);
  const saveMutation = useSaveDraft(workspaceId);
  const reviseMutation = useReviseDraft(workspaceId);

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const title = newTitle.trim();
    if (!title || createMutation.isPending) {
      return;
    }
    createMutation.mutate(
      { title },
      {
        onSuccess: (created) => {
          setNewTitle("");
          setSelectedId(created.id);
        },
      },
    );
  }

  function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (generateMutation.isPending) {
      return;
    }
    generateMutation.mutate(
      { title: generateTitle.trim() || "未命名章节" },
      {
        onSuccess: (created) => {
          setGenerateTitle("");
          setSelectedId(created.id);
        },
      },
    );
  }

  return (
    <section className="writer-page" data-testid="writer-page">
      <header className="page-header">
        <h2>写作</h2>
        <Link className="text-link" to={`/works/${workspaceId ?? ""}`}>
          返回作品
        </Link>
      </header>
      <div className="writer-layout">
        <aside className="writer-side" data-testid="writer-sidebar">
          <section className="panel writer-drafts-panel" data-testid="draft-list-panel">
            <header className="panel-header">
              <h3>草稿</h3>
            </header>
            <div className="panel-body">
              <form className="writer-form" onSubmit={handleCreate}>
                <div className="form-field">
                  <label className="form-label" htmlFor="new-draft-title">
                    新建作者空稿
                  </label>
                  <input
                    id="new-draft-title"
                    type="text"
                    value={newTitle}
                    onChange={(event) => setNewTitle(event.target.value)}
                    placeholder="草稿标题"
                    data-testid="new-draft-title"
                  />
                </div>
                <button
                  type="submit"
                  className="primary-button"
                  disabled={newTitle.trim() === "" || createMutation.isPending}
                  data-testid="new-draft-submit"
                >
                  {createMutation.isPending ? "创建中…" : "新建空稿"}
                </button>
              </form>
              <form className="writer-form" onSubmit={handleGenerate}>
                <div className="form-field">
                  <label className="form-label" htmlFor="generate-draft-title">
                    LLM 生成（标题可留空）
                  </label>
                  <input
                    id="generate-draft-title"
                    type="text"
                    value={generateTitle}
                    onChange={(event) => setGenerateTitle(event.target.value)}
                    placeholder="未命名章节"
                    data-testid="generate-draft-title"
                  />
                </div>
                <button
                  type="submit"
                  className="primary-button"
                  disabled={generateMutation.isPending}
                  data-testid="generate-draft-submit"
                >
                  {generateMutation.isPending ? "生成中…" : "生成草稿"}
                </button>
              </form>
              {createMutation.isError ? (
                <p className="inline-error" data-testid="new-draft-error">
                  {createMutation.error.message}
                </p>
              ) : null}
              {generateMutation.isError ? (
                <p className="inline-error" data-testid="generate-error">
                  {generateMutation.error.message}
                </p>
              ) : null}
              {drafts.isPending ? <SkeletonRows count={3} /> : null}
              {drafts.isError ? (
                <ErrorState
                  source={`/works/${workspaceId ?? ""}/drafts`}
                  message={drafts.error.message}
                  onRetry={() => void drafts.refetch()}
                />
              ) : null}
              {drafts.isSuccess && drafts.data.length === 0 ? (
                <EmptyState
                  title="还没有草稿"
                  hint="新建一篇空稿，或让 LLM 生成第一章"
                />
              ) : null}
              {drafts.isSuccess && drafts.data.length > 0 ? (
                <ul className="draft-list" data-testid="draft-list">
                  {drafts.data.map((draft) => (
                    <li key={draft.id}>
                      <button
                        type="button"
                        className={`draft-list-item${
                          draft.id === effectiveId
                            ? " draft-list-item--selected"
                            : ""
                        }`}
                        onClick={() => setSelectedId(draft.id)}
                        data-testid="draft-list-item"
                      >
                        <span className="draft-list-title">{draft.title}</span>
                        <span className="draft-list-meta">
                          {statusLabelFromSummary(draft)} · v{draft.current_version}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </section>
        </aside>
        <div className="writer-main">
          {drafts.isPending && effectiveId === null ? (
            <section className="panel writer-workbench">
              <header className="panel-header">
                <h3>正文工作台</h3>
              </header>
              <div className="panel-body">
                <SkeletonRows count={4} />
              </div>
            </section>
          ) : null}
          {drafts.isSuccess && drafts.data.length === 0 ? (
            <section className="panel writer-workbench">
              <header className="panel-header">
                <h3>正文工作台</h3>
              </header>
              <div className="panel-body">
                <EmptyState
                  title="先创建一篇草稿"
                  hint="作者空稿从 v0 开始，LLM 生成直接出第一版"
                />
              </div>
            </section>
          ) : null}
          {effectiveId !== null && detail.isPending ? (
            <section className="panel writer-workbench">
              <header className="panel-header">
                <h3>正文工作台</h3>
              </header>
              <div className="panel-body">
                <SkeletonRows count={4} />
              </div>
            </section>
          ) : null}
          {effectiveId !== null && detail.isError ? (
            <section className="panel writer-workbench">
              <header className="panel-header">
                <h3>正文工作台</h3>
              </header>
              <div className="panel-body">
                <ErrorState
                  source={`/works/${workspaceId ?? ""}/drafts/${effectiveId}`}
                  message={detail.error.message}
                  onRetry={() => void detail.refetch()}
                />
              </div>
            </section>
          ) : null}
          {detail.isSuccess ? (
            <DraftWorkbench
              workspaceId={workspaceId ?? ""}
              detail={detail.data}
              reviews={reviews}
              saveMutation={saveMutation}
              reviseMutation={reviseMutation}
            />
          ) : null}
        </div>
      </div>
    </section>
  );
}

function statusLabelFromSummary(
  draft: { status: string; current_version: number },
): string {
  if (draft.status === "draft") {
    return draft.current_version === 0 ? "空稿" : "待拍板";
  }
  if (draft.status === "quality_failed") {
    return "未过质量门";
  }
  if (draft.status === "accepted") {
    return "已接受";
  }
  if (draft.status === "rejected") {
    return "已拒绝";
  }
  return draft.status;
}
