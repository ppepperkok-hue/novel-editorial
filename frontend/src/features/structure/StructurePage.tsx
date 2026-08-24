import { useEffect, useState, type CSSProperties, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import type { StructureNode } from "../../api/client";
import {
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "../../components/StateViews";
import { useWorkspaceSelection } from "../../hooks/useWorkspaceSelection";
import { formatDateTime } from "../../utils/format";
import {
  useCreateStructureNode,
  useDeleteStructureNode,
  useMoveStructureNode,
  useOutline,
  usePatchStructureNode,
  useStructure,
  useWriteOutline,
} from "./useStructureQueries";

const STRUCTURE_KIND_LABELS: Record<string, string> = {
  volume: "卷",
  chapter: "章",
  section: "篇目",
};

const STRUCTURE_STATUS_LABELS: Record<string, string> = {
  writing: "创作中",
  completed: "已完成",
  shelved: "搁置",
};

function kindLabel(kind: string): string {
  return STRUCTURE_KIND_LABELS[kind] ?? kind;
}

function statusLabel(status: string): string {
  return STRUCTURE_STATUS_LABELS[status] ?? status;
}

function buildChildrenMap(nodes: StructureNode[]) {
  const children = new Map<string | null, StructureNode[]>();
  for (const node of nodes) {
    const list = children.get(node.parent_id) ?? [];
    list.push(node);
    children.set(node.parent_id, list);
  }
  for (const list of children.values()) {
    list.sort((a, b) => a.sort_order - b.sort_order);
  }
  return children;
}

function subtreeIds(nodes: StructureNode[], rootId: string): Set<string> {
  const children = buildChildrenMap(nodes);
  const ids = new Set<string>([rootId]);
  const queue = [rootId];
  while (queue.length > 0) {
    const current = queue.shift() as string;
    for (const child of children.get(current) ?? []) {
      ids.add(child.id);
      queue.push(child.id);
    }
  }
  return ids;
}

function StructureAddForm({
  workspaceId,
  nodes,
}: {
  workspaceId: string;
  nodes: StructureNode[];
}) {
  const create = useCreateStructureNode(workspaceId);
  const [kind, setKind] = useState("卷");
  const [title, setTitle] = useState("");
  const [parent, setParent] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = title.trim();
    if (trimmed === "") {
      return;
    }
    create.mutate(
      {
        kind,
        title: trimmed,
        ...(parent === "" ? {} : { parent }),
      },
      {
        onSuccess: () => {
          setTitle("");
        },
      },
    );
  }

  return (
    <form className="structure-add-form" onSubmit={handleSubmit}>
      <div className="form-row">
        <label className="form-field">
          <span className="form-label">类型</span>
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value)}
          >
            <option value="卷">卷</option>
            <option value="章">章</option>
            <option value="篇目">篇目</option>
          </select>
        </label>
        <label className="form-field structure-add-title">
          <span className="form-label">标题</span>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="节点标题"
          />
        </label>
        <label className="form-field">
          <span className="form-label">父节点</span>
          <select
            value={parent}
            onChange={(event) => setParent(event.target.value)}
          >
            <option value="">根部</option>
            {nodes.map((node) => (
              <option key={node.id} value={node.id}>
                {kindLabel(node.kind)} · {node.title}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          className="primary-button"
          disabled={title.trim() === "" || create.isPending}
        >
          添加
        </button>
      </div>
      {create.isError ? (
        <p className="inline-error" role="alert">
          添加失败：{create.error.message}
        </p>
      ) : null}
    </form>
  );
}

function StructureNodeRow({
  workspaceId,
  node,
  nodes,
}: {
  workspaceId: string;
  node: StructureNode;
  nodes: StructureNode[];
}) {
  const patch = usePatchStructureNode(workspaceId);
  const move = useMoveStructureNode(workspaceId);
  const remove = useDeleteStructureNode(workspaceId);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState(node.title);
  const [moving, setMoving] = useState(false);
  const [moveTarget, setMoveTarget] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const excluded = subtreeIds(nodes, node.id);
  const currentTarget = node.parent_id ?? "root";

  function submitRename() {
    const trimmed = titleDraft.trim();
    if (trimmed === "" || trimmed === node.title) {
      setEditingTitle(false);
      return;
    }
    patch.mutate(
      { nodeId: node.id, body: { title: trimmed } },
      {
        onSuccess: () => {
          setEditingTitle(false);
        },
      },
    );
  }

  function submitMove() {
    if (moveTarget === "" || moveTarget === currentTarget) {
      setMoving(false);
      return;
    }
    move.mutate(
      {
        nodeId: node.id,
        body:
          moveTarget === "root"
            ? { root: true }
            : { root: false, parent: moveTarget },
      },
      {
        onSuccess: () => {
          setMoving(false);
          setMoveTarget("");
        },
      },
    );
  }

  const activeError =
    patch.error?.message ?? move.error?.message ?? remove.error?.message;

  return (
    <>
      <div className="structure-node-row">
        <span className="structure-kind">{kindLabel(node.kind)}</span>
        <span className="structure-title">{node.title}</span>
        <label className="structure-status-select">
          <span className="visually-hidden">状态</span>
          <select
            value={node.status}
            onChange={(event) =>
              patch.mutate({
                nodeId: node.id,
                body: { status: statusLabel(event.target.value) },
              })
            }
            aria-label={`${node.title} 状态`}
          >
            {Object.entries(STRUCTURE_STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="node-action"
          onClick={() => {
            setEditingTitle((current) => !current);
            setTitleDraft(node.title);
          }}
        >
          改名
        </button>
        <button
          type="button"
          className="node-action"
          onClick={() => {
            setMoving((current) => !current);
            setMoveTarget(currentTarget);
          }}
        >
          移动
        </button>
        <button
          type="button"
          className="node-action node-action--danger"
          onClick={() => {
            if (confirmDelete) {
              remove.mutate(node.id, {
                onSuccess: () => setConfirmDelete(false),
              });
            } else {
              setConfirmDelete(true);
            }
          }}
          disabled={remove.isPending}
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
      </div>
      {editingTitle ? (
        <div className="node-inline-form">
          <input
            value={titleDraft}
            onChange={(event) => setTitleDraft(event.target.value)}
            aria-label={`${node.title} 新标题`}
          />
          <button
            type="button"
            className="primary-button"
            onClick={submitRename}
            disabled={patch.isPending}
          >
            保存
          </button>
          <button
            type="button"
            className="node-action"
            onClick={() => setEditingTitle(false)}
          >
            取消
          </button>
        </div>
      ) : null}
      {moving ? (
        <div className="node-inline-form">
          <select
            value={moveTarget}
            onChange={(event) => setMoveTarget(event.target.value)}
            aria-label={`${node.title} 移动目标`}
          >
            <option value="root">根部</option>
            {nodes
              .filter((candidate) => !excluded.has(candidate.id))
              .map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {kindLabel(candidate.kind)} · {candidate.title}
                </option>
              ))}
          </select>
          <button
            type="button"
            className="primary-button"
            onClick={submitMove}
            disabled={move.isPending}
          >
            确认移动
          </button>
          <button
            type="button"
            className="node-action"
            onClick={() => setMoving(false)}
          >
            取消
          </button>
        </div>
      ) : null}
      {activeError ? (
        <p className="inline-error" role="alert">
          操作失败：{activeError}
        </p>
      ) : null}
    </>
  );
}

function StructureBranch({
  workspaceId,
  nodes,
  childrenMap,
  depth,
}: {
  workspaceId: string;
  nodes: StructureNode[];
  childrenMap: Map<string | null, StructureNode[]>;
  depth: number;
}) {
  return (
    <ul className="structure-tree">
      {nodes.map((node) => (
        <li
          key={node.id}
          className="structure-node"
          data-testid={`structure-node-${node.id}`}
          style={{ "--depth": depth } as CSSProperties}
        >
          <StructureNodeRow
            workspaceId={workspaceId}
            node={node}
            nodes={nodesFromMap(childrenMap)}
          />
          {childrenMap.get(node.id)?.length ? (
            <StructureBranch
              workspaceId={workspaceId}
              nodes={childrenMap.get(node.id) as StructureNode[]}
              childrenMap={childrenMap}
              depth={depth + 1}
            />
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function nodesFromMap(
  childrenMap: Map<string | null, StructureNode[]>,
): StructureNode[] {
  const nodes: StructureNode[] = [];
  for (const list of childrenMap.values()) {
    nodes.push(...list);
  }
  return nodes;
}

function StructureTree({
  workspaceId,
  nodes,
}: {
  workspaceId: string;
  nodes: StructureNode[];
}) {
  const childrenMap = buildChildrenMap(nodes);
  const roots = childrenMap.get(null) ?? [];
  const total = nodes.length;
  const completed = nodes.filter((node) => node.status === "completed").length;
  const completedChapters = nodes.filter(
    (node) => node.kind === "chapter" && node.status === "completed",
  ).length;
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="structure-tree-wrap">
      <div
        className="structure-progress"
        data-testid="structure-progress"
        role="status"
        aria-label={`结构进度 ${completed}/${total}`}
      >
        <div className="structure-progress-track">
          <div
            className="structure-progress-bar"
            style={{ width: `${percent}%` }}
          />
        </div>
        <span className="structure-progress-text">
          已完成 {completed}/{total} 节点 · 完成章 {completedChapters}
        </span>
      </div>
      <StructureBranch
        workspaceId={workspaceId}
        nodes={roots}
        childrenMap={childrenMap}
        depth={0}
      />
    </div>
  );
}

function OutlinePanel({ workspaceId }: { workspaceId: string }) {
  const outline = useOutline(workspaceId);
  const write = useWriteOutline(workspaceId);
  const [content, setContent] = useState("");
  const [reason, setReason] = useState("");
  const outlineData = outline.data;

  useEffect(() => {
    if (outlineData != null) {
      setContent(outlineData.content);
    }
  }, [outlineData]);

  function submitOutline(event: FormEvent) {
    event.preventDefault();
    const trimmed = content.trim();
    if (trimmed === "") {
      return;
    }
    write.mutate(
      {
        content: trimmed,
        actor: "作者",
        ...(reason.trim() === "" ? {} : { reason: reason.trim() }),
      },
      {
        onSuccess: () => {
          setReason("");
        },
      },
    );
  }

  return (
    <section className="panel outline-panel" data-testid="outline-panel">
      <header className="panel-header">
        <h3>大纲</h3>
      </header>
      <div className="panel-body">
        {outline.isPending ? <SkeletonRows count={4} /> : null}
        {outline.isError ? (
          <ErrorState
            source={`/works/${workspaceId}/outline`}
            message={outline.error.message}
            onRetry={() => void outline.refetch()}
          />
        ) : null}
        {outline.isSuccess && outlineData === null ? (
          <EmptyState
            title="还没有大纲"
            hint="先写一版骨架，之后可以随时修订"
          />
        ) : null}
        {outline.isSuccess && outlineData != null ? (
          <div className="outline-current">
            <p className="outline-meta">
              v{outlineData.version} · {outlineData.actor} ·{" "}
              {formatDateTime(outlineData.created_at)}
            </p>
            <pre className="plain-output" data-testid="outline-content">
              {outlineData.content}
            </pre>
          </div>
        ) : null}
        <form className="outline-form" onSubmit={submitOutline}>
          <h4>{outlineData == null ? "创建大纲" : "修订大纲"}</h4>
          <label className="form-field">
            <span className="form-label">内容</span>
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={6}
              placeholder="大纲正文，支持多行"
            />
          </label>
          {outlineData !== null ? (
            <label className="form-field">
              <span className="form-label">修订原因（必填）</span>
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="这次为什么改"
              />
            </label>
          ) : null}
          <button
            type="submit"
            className="primary-button"
            disabled={
              content.trim() === "" ||
              (outlineData != null && reason.trim() === "") ||
              write.isPending
            }
          >
            {outlineData == null ? "创建大纲" : "保存修订"}
          </button>
          {write.isError ? (
            <p className="inline-error" role="alert">
              保存失败：{write.error.message}
            </p>
          ) : null}
        </form>
      </div>
    </section>
  );
}

export default function StructurePage() {
  const { workspaceId } = useParams();
  useWorkspaceSelection(workspaceId);
  const structure = useStructure(workspaceId);
  const workspaceIdValue = workspaceId ?? "";

  return (
    <section
      className="structure-page"
      data-testid="structure-page"
      data-workspace={workspaceId}
    >
      <header className="page-header">
        <h2>结构</h2>
        <Link className="text-link" to={`/works/${workspaceIdValue}`}>
          返回作品
        </Link>
      </header>
      <div className="structure-layout">
        <section className="panel structure-panel" data-testid="structure-panel">
          <header className="panel-header">
            <h3>卷 · 章 · 篇</h3>
          </header>
          <div className="panel-body">
            {structure.isPending ? <SkeletonRows count={4} /> : null}
            {structure.isError ? (
              <ErrorState
                source={`/works/${workspaceIdValue}/structure`}
                message={structure.error.message}
                onRetry={() => void structure.refetch()}
              />
            ) : null}
            {structure.isSuccess ? (
              <>
                <StructureAddForm
                  workspaceId={workspaceIdValue}
                  nodes={structure.data}
                />
                {structure.data.length === 0 ? (
                  <EmptyState
                    title="还没有结构节点"
                    hint="从第一卷或第一章开始搭建骨架"
                  />
                ) : (
                  <StructureTree
                    workspaceId={workspaceIdValue}
                    nodes={structure.data}
                  />
                )}
              </>
            ) : null}
          </div>
        </section>
        <OutlinePanel workspaceId={workspaceIdValue} />
      </div>
    </section>
  );
}
