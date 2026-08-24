import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import {
  getInspect,
  type Inspiration,
  type SettingEntry,
} from "../../api/client";
import {
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "../../components/StateViews";
import { useWorkspaceSelection } from "../../hooks/useWorkspaceSelection";
import { formatDateTime } from "../../utils/format";
import {
  useCheckSettings,
  useCreateInspiration,
  useDeleteInspiration,
  useInspiration,
  useInspirations,
  useSetting,
  useSettings,
  useWriteSetting,
} from "./useSettingsQueries";

const SETTING_KIND_LABELS: Record<string, string> = {
  character: "人物",
  relation: "关系",
  timeline: "时间线",
  world: "世界观",
};

const SETTING_KIND_OPTIONS = ["人物", "关系", "时间线", "世界观"];

function settingKindLabel(kind: string): string {
  return SETTING_KIND_LABELS[kind] ?? kind;
}

function InspectPanel({ workspaceId }: { workspaceId: string }) {
  const [keyword, setKeyword] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runInspect(event: FormEvent) {
    event.preventDefault();
    const trimmed = keyword.trim();
    if (trimmed === "") {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const text = await getInspect(workspaceId, trimmed);
      setResult(text);
    } catch (inspectError) {
      setError(
        inspectError instanceof Error ? inspectError.message : String(inspectError),
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel inspect-panel" data-testid="inspect-panel">
      <header className="panel-header">
        <h3>穿透检索</h3>
      </header>
      <div className="panel-body">
        <form className="inspect-form" onSubmit={runInspect}>
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="检索草稿 / 意见 / 设定 / 灵感…"
            aria-label="检索关键词"
          />
          <button type="submit" disabled={keyword.trim() === "" || loading}>
            {loading ? "检索中…" : "检索"}
          </button>
        </form>
        {error ? (
          <p className="inline-error" role="alert">
            检索失败：{error}
          </p>
        ) : null}
        {result !== null ? (
          <pre className="plain-output" data-testid="inspect-result">
            {result}
          </pre>
        ) : null}
      </div>
    </section>
  );
}

function SettingRow({
  entry,
  onSelect,
}: {
  entry: SettingEntry;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        className="setting-item"
        onClick={onSelect}
        data-testid={`setting-item-${entry.id}`}
      >
        <span className="structure-kind">{settingKindLabel(entry.kind)}</span>
        <span className="setting-item-name">{entry.name}</span>
        <span className="setting-item-meta">v{entry.current_version}</span>
      </button>
    </li>
  );
}

function SettingsPanel({ workspaceId }: { workspaceId: string }) {
  const [kindFilter, setKindFilter] = useState("");
  const settings = useSettings(workspaceId, kindFilter || undefined);
  const write = useWriteSetting(workspaceId);
  const check = useCheckSettings(workspaceId);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const detail = useSetting(workspaceId, selectedId);
  const [revisingId, setRevisingId] = useState<string | null>(null);
  const [newKind, setNewKind] = useState("人物");
  const [newName, setNewName] = useState("");
  const [newContent, setNewContent] = useState("");
  const [reviseContent, setReviseContent] = useState("");
  const [reviseReason, setReviseReason] = useState("");

  function submitNewSetting(event: FormEvent) {
    event.preventDefault();
    if (newName.trim() === "" || newContent.trim() === "") {
      return;
    }
    write.mutate(
      {
        kind: newKind,
        name: newName.trim(),
        content: newContent.trim(),
        source: "作者",
        actor: "作者",
      },
      {
        onSuccess: () => {
          setNewName("");
          setNewContent("");
        },
      },
    );
  }

  function submitRevision(event: FormEvent) {
    event.preventDefault();
    if (revisingId === null || reviseContent.trim() === "" || reviseReason.trim() === "") {
      return;
    }
    write.mutate(
      {
        setting_id: revisingId,
        content: reviseContent.trim(),
        reason: reviseReason.trim(),
        source: "作者",
        actor: "作者",
      },
      {
        onSuccess: () => {
          setRevisingId(null);
          setReviseContent("");
          setReviseReason("");
        },
      },
    );
  }

  function openRevision(entry: SettingEntry) {
    setRevisingId(entry.id);
    setReviseContent(entry.content);
    setReviseReason("");
  }

  return (
    <section className="panel settings-panel" data-testid="settings-panel">
      <header className="panel-header">
        <h3>设定库</h3>
      </header>
      <div className="panel-body">
        <div className="settings-toolbar">
          <label className="form-field">
            <span className="form-label">按类型过滤</span>
            <select
              value={kindFilter}
              onChange={(event) => setKindFilter(event.target.value)}
            >
              <option value="">全部</option>
              {SETTING_KIND_OPTIONS.map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="node-action"
            onClick={() => void check.refetch()}
            disabled={check.isFetching}
          >
            {check.isFetching ? "检查中…" : "运行检查"}
          </button>
        </div>
        {check.data !== undefined ? (
          <pre className="plain-output" data-testid="settings-check-report">
            {check.data}
          </pre>
        ) : null}
        {check.isError ? (
          <p className="inline-error" role="alert">
            检查失败：{check.error.message}
          </p>
        ) : null}
        {settings.isPending ? <SkeletonRows count={4} /> : null}
        {settings.isError ? (
          <ErrorState
            source={`/works/${workspaceId}/settings`}
            message={settings.error.message}
            onRetry={() => void settings.refetch()}
          />
        ) : null}
        {settings.isSuccess && settings.data.length === 0 ? (
          <EmptyState
            title="设定库还是空的"
            hint="人物、关系、时间线、世界观，从第一条开始"
          />
        ) : null}
        {settings.isSuccess && settings.data.length > 0 ? (
          <ul className="setting-list" data-testid="setting-list">
            {settings.data.map((entry) => (
              <SettingRow
                key={entry.id}
                entry={entry}
                onSelect={() =>
                  setSelectedId((current) =>
                    current === entry.id ? null : entry.id,
                  )
                }
              />
            ))}
          </ul>
        ) : null}
        {selectedId !== null ? (
          <div className="setting-detail" data-testid="setting-detail">
            {detail.isPending ? <SkeletonRows count={2} /> : null}
            {detail.isError ? (
              <ErrorState
                source={`/works/${workspaceId}/settings/${selectedId}`}
                message={detail.error.message}
                onRetry={() => void detail.refetch()}
              />
            ) : null}
            {detail.isSuccess ? (
              <>
                <p className="setting-detail-meta">
                  {settingKindLabel(detail.data.kind)} · {detail.data.name} ·
                  v{detail.data.current_version} · 更新于{" "}
                  {formatDateTime(detail.data.updated_at)}
                </p>
                <pre className="plain-output">{detail.data.content}</pre>
                {detail.data.source ? (
                  <p className="setting-detail-source">
                    来源：{detail.data.source}
                  </p>
                ) : null}
                <button
                  type="button"
                  className="node-action"
                  onClick={() => openRevision(detail.data)}
                >
                  修订此条
                </button>
              </>
            ) : null}
          </div>
        ) : null}
        {revisingId !== null ? (
          <form className="setting-revise-form" onSubmit={submitRevision}>
            <h4>修订设定</h4>
            <label className="form-field">
              <span className="form-label">内容</span>
              <textarea
                value={reviseContent}
                onChange={(event) => setReviseContent(event.target.value)}
                rows={4}
              />
            </label>
            <label className="form-field">
              <span className="form-label">修订原因（必填）</span>
              <input
                value={reviseReason}
                onChange={(event) => setReviseReason(event.target.value)}
                placeholder="这次为什么改"
              />
            </label>
            <button
              type="submit"
              className="primary-button"
              disabled={
                reviseContent.trim() === "" ||
                reviseReason.trim() === "" ||
                write.isPending
              }
            >
              保存修订
            </button>
            <button
              type="button"
              className="node-action"
              onClick={() => setRevisingId(null)}
            >
              取消
            </button>
          </form>
        ) : null}
        {write.isError ? (
          <p className="inline-error" role="alert">
            保存失败：{write.error.message}
          </p>
        ) : null}
        <form className="setting-add-form" onSubmit={submitNewSetting}>
          <h4>新增设定</h4>
          <div className="form-row">
            <label className="form-field">
              <span className="form-label">类型</span>
              <select
                value={newKind}
                onChange={(event) => setNewKind(event.target.value)}
              >
                {SETTING_KIND_OPTIONS.map((kind) => (
                  <option key={kind} value={kind}>
                    {kind}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-field setting-add-name">
              <span className="form-label">名称</span>
              <input
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                placeholder="条目名称"
              />
            </label>
          </div>
          <label className="form-field">
            <span className="form-label">内容</span>
            <textarea
              value={newContent}
              onChange={(event) => setNewContent(event.target.value)}
              rows={3}
              placeholder="设定正文"
            />
          </label>
          <button
            type="submit"
            className="primary-button"
            disabled={
              newName.trim() === "" ||
              newContent.trim() === "" ||
              write.isPending
            }
          >
            新增
          </button>
        </form>
      </div>
    </section>
  );
}

function InspirationRow({
  item,
  onSelect,
  onDelete,
}: {
  item: Inspiration;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <li className="inspiration-item">
      <button
        type="button"
        className="inspiration-item-open"
        onClick={onSelect}
        data-testid={`inspiration-item-${item.id}`}
      >
        <span className="structure-kind">{item.kind}</span>
        <span className="inspiration-item-content">{item.content}</span>
        <span className="setting-item-meta">
          {formatDateTime(item.created_at)}
        </span>
      </button>
      <button
        type="button"
        className="node-action node-action--danger"
        onClick={() => {
          if (confirmDelete) {
            onDelete();
            setConfirmDelete(false);
          } else {
            setConfirmDelete(true);
          }
        }}
      >
        {confirmDelete ? "确认删除？" : "删除"}
      </button>
      {confirmDelete ? (
        <button
          type="button"
          className="node-action"
          onClick={() => setConfirmDelete(false)}
        >
          取消
        </button>
      ) : null}
    </li>
  );
}

function InspirationsPanel({ workspaceId }: { workspaceId: string }) {
  const [kindFilter, setKindFilter] = useState("");
  const [keywordFilter, setKeywordFilter] = useState("");
  const [appliedKind, setAppliedKind] = useState("");
  const [appliedKeyword, setAppliedKeyword] = useState("");
  const inspirations = useInspirations(
    workspaceId,
    appliedKind || undefined,
    appliedKeyword || undefined,
  );
  const create = useCreateInspiration(workspaceId);
  const remove = useDeleteInspiration(workspaceId);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const detail = useInspiration(workspaceId, selectedId);
  const [content, setContent] = useState("");
  const [kind, setKind] = useState("灵感");
  const [source, setSource] = useState("");

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setAppliedKind(kindFilter.trim());
    setAppliedKeyword(keywordFilter.trim());
    setSelectedId(null);
  }

  function submitNew(event: FormEvent) {
    event.preventDefault();
    if (content.trim() === "") {
      return;
    }
    create.mutate(
      {
        content: content.trim(),
        kind: kind.trim() === "" ? "灵感" : kind.trim(),
        source: source.trim(),
      },
      {
        onSuccess: () => {
          setContent("");
          setSource("");
        },
      },
    );
  }

  return (
    <section className="panel inspirations-panel" data-testid="inspirations-panel">
      <header className="panel-header">
        <h3>灵感素材</h3>
      </header>
      <div className="panel-body">
        <form className="inspiration-filters" onSubmit={applyFilters}>
          <label className="form-field">
            <span className="form-label">类型</span>
            <input
              value={kindFilter}
              onChange={(event) => setKindFilter(event.target.value)}
              placeholder="如 灵感 / 场景"
            />
          </label>
          <label className="form-field">
            <span className="form-label">关键词</span>
            <input
              value={keywordFilter}
              onChange={(event) => setKeywordFilter(event.target.value)}
              placeholder="匹配内容与来源"
            />
          </label>
          <button
            type="submit"
            className="node-action"
            disabled={kindFilter.trim() === "" && keywordFilter.trim() === ""}
          >
            应用过滤
          </button>
          <button
            type="button"
            className="node-action"
            onClick={() => {
              setKindFilter("");
              setKeywordFilter("");
              setAppliedKind("");
              setAppliedKeyword("");
              setSelectedId(null);
            }}
          >
            清除
          </button>
        </form>
        {inspirations.isPending ? <SkeletonRows count={4} /> : null}
        {inspirations.isError ? (
          <ErrorState
            source={`/works/${workspaceId}/inspirations`}
            message={inspirations.error.message}
            onRetry={() => void inspirations.refetch()}
          />
        ) : null}
        {inspirations.isSuccess && inspirations.data.length === 0 ? (
          <EmptyState
            title="还没有灵感素材"
            hint="随手记下的句子、画面、点子都在这里"
          />
        ) : null}
        {inspirations.isSuccess && inspirations.data.length > 0 ? (
          <ul className="inspiration-list" data-testid="inspiration-list">
            {inspirations.data.map((item) => (
              <InspirationRow
                key={item.id}
                item={item}
                onSelect={() =>
                  setSelectedId((current) =>
                    current === item.id ? null : item.id,
                  )
                }
                onDelete={() => remove.mutate(item.id)}
              />
            ))}
          </ul>
        ) : null}
        {selectedId !== null ? (
          <div className="inspiration-detail" data-testid="inspiration-detail">
            {detail.isPending ? <SkeletonRows count={2} /> : null}
            {detail.isError ? (
              <ErrorState
                source={`/works/${workspaceId}/inspirations/${selectedId}`}
                message={detail.error.message}
                onRetry={() => void detail.refetch()}
              />
            ) : null}
            {detail.isSuccess ? (
              <>
                <p className="inspiration-detail-meta">
                  {detail.data.kind} · {formatDateTime(detail.data.created_at)}
                </p>
                <pre className="plain-output">{detail.data.content}</pre>
                {detail.data.source ? (
                  <p className="setting-detail-source">
                    来源：{detail.data.source}
                  </p>
                ) : null}
              </>
            ) : null}
          </div>
        ) : null}
        {remove.isError ? (
          <p className="inline-error" role="alert">
            删除失败：{remove.error.message}
          </p>
        ) : null}
        <form className="inspiration-add-form" onSubmit={submitNew}>
          <h4>新增灵感</h4>
          <label className="form-field">
            <span className="form-label">内容</span>
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={3}
              placeholder="一句画面、一个点子…"
            />
          </label>
          <div className="form-row">
            <label className="form-field">
              <span className="form-label">类型</span>
              <input
                value={kind}
                onChange={(event) => setKind(event.target.value)}
                placeholder="灵感"
              />
            </label>
            <label className="form-field">
              <span className="form-label">来源</span>
              <input
                value={source}
                onChange={(event) => setSource(event.target.value)}
                placeholder="可选"
              />
            </label>
          </div>
          <button
            type="submit"
            className="primary-button"
            disabled={content.trim() === "" || create.isPending}
          >
            新增
          </button>
          {create.isError ? (
            <p className="inline-error" role="alert">
              新增失败：{create.error.message}
            </p>
          ) : null}
        </form>
      </div>
    </section>
  );
}

export default function SettingsPage() {
  const { workspaceId } = useParams();
  useWorkspaceSelection(workspaceId);
  const workspaceIdValue = workspaceId ?? "";

  return (
    <section
      className="settings-page"
      data-testid="settings-page"
      data-workspace={workspaceId}
    >
      <header className="page-header">
        <h2>设定</h2>
        <Link className="text-link" to={`/works/${workspaceIdValue}`}>
          返回作品
        </Link>
      </header>
      <InspectPanel workspaceId={workspaceIdValue} />
      <div className="settings-layout">
        <SettingsPanel workspaceId={workspaceIdValue} />
        <InspirationsPanel workspaceId={workspaceIdValue} />
      </div>
    </section>
  );
}
