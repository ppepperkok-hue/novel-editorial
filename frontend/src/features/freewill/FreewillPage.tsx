import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { TextReportPanel } from "../../components/TextReportPanel";
import {
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "../../components/StateViews";
import { useWorkspaceSelection } from "../../hooks/useWorkspaceSelection";
import {
  behaviorKindLabel,
  groupBehaviorStateByActor,
  parseBehaviorStateText,
  parseTimelineText,
} from "./behaviorText";
import {
  groupMotivesByOwner,
  parseMotiveText,
  type MotiveEntry,
} from "./motiveText";
import {
  useBehaviorState,
  useBehaviorTimeline,
  useDropMotive,
  useMotives,
  usePatience,
} from "./useFreewillQueries";

const BEHAVIOR_KIND_OPTIONS: Array<[string, string]> = [
  ["impression", "印象"],
  ["relationship", "关系"],
  ["viewpoint", "观点"],
  ["silence", "沉默"],
  ["conflict", "冲突"],
  ["cooldown", "冷却"],
];

function MotiveRow({
  motive,
  onDrop,
  pending,
}: {
  motive: MotiveEntry;
  onDrop: () => void;
  pending: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  return (
    <li className="motive-item" data-testid={`motive-${motive.id}`}>
      <div className="motive-item-head">
        <span className="motive-kind">{motive.kind}</span>
        <span className="motive-strength">强度 {motive.strength}</span>
        <span className="motive-source">来源 {motive.source}</span>
      </div>
      <p className="motive-content">{motive.content}</p>
      <button
        type="button"
        className="node-action node-action--danger"
        onClick={() => {
          if (confirming) {
            onDrop();
            setConfirming(false);
          } else {
            setConfirming(true);
          }
        }}
        disabled={pending}
      >
        {confirming ? "确认弃置？" : "弃置"}
      </button>
      {confirming ? (
        <button
          type="button"
          className="node-action"
          onClick={() => setConfirming(false)}
        >
          取消
        </button>
      ) : null}
    </li>
  );
}

function MotivesPanel({ workspaceId }: { workspaceId: string }) {
  const motives = useMotives(workspaceId);
  const drop = useDropMotive(workspaceId);
  const text = motives.data ?? "";
  const entries = parseMotiveText(text);
  const groups = groupMotivesByOwner(entries);
  const isEmpty =
    text.trim() === "" || (entries.length === 0 && text.includes("no motives"));

  return (
    <section className="panel motives-panel" data-testid="motives-panel">
      <header className="panel-header">
        <h3>动机</h3>
      </header>
      <div className="panel-body">
        {motives.isPending ? <SkeletonRows count={4} /> : null}
        {motives.isError ? (
          <ErrorState
            source={`/works/${workspaceId}/motives`}
            message={motives.error.message}
            onRetry={() => void motives.refetch()}
          />
        ) : null}
        {motives.isSuccess && isEmpty ? (
          <EmptyState
            title="还没有动机"
            hint="伙伴的动机浮现后会按伙伴分组、按强度列在这里"
          />
        ) : null}
        {motives.isSuccess && !isEmpty ? (
          <>
            <div className="motive-groups" data-testid="motive-groups">
              {groups.map((group) => (
                <div className="motive-group" key={group.owner}>
                  <h4 className="motive-owner">{group.owner}</h4>
                  <ul className="motive-list">
                    {group.motives.map((motive) => (
                      <MotiveRow
                        key={motive.id}
                        motive={motive}
                        pending={drop.isPending}
                        onDrop={() => drop.mutate(motive.id)}
                      />
                    ))}
                  </ul>
                </div>
              ))}
            </div>
            {drop.isError ? (
              <p className="inline-error" role="alert">
                弃置失败：{drop.error.message}
              </p>
            ) : null}
            <details className="motive-raw">
              <summary>CLI 原文</summary>
              <pre className="plain-output" data-testid="motives-report">
                {text}
              </pre>
            </details>
          </>
        ) : null}
      </div>
    </section>
  );
}

function PatiencePanel({ workspaceId }: { workspaceId: string }) {
  const patience = usePatience(workspaceId);
  return (
    <TextReportPanel
      title="耐心池"
      source={`/works/${workspaceId}/patience`}
      query={patience}
      disabled={false}
      emptyTitle="暂无耐心数据"
      emptyHint="伙伴的耐心池与三状态来源会逐条列在这里"
      dataTestId="patience"
    />
  );
}

function BehaviorTimelinePanel({ workspaceId }: { workspaceId: string }) {
  const [agentDraft, setAgentDraft] = useState("");
  const [kindsDraft, setKindsDraft] = useState<string[]>([]);
  const [agent, setAgent] = useState("");
  const [kinds, setKinds] = useState<string[]>([]);

  useEffect(() => {
    setAgentDraft("");
    setKindsDraft([]);
    setAgent("");
    setKinds([]);
  }, [workspaceId]);

  const timeline = useBehaviorTimeline(workspaceId, {
    ...(agent === "" ? {} : { agent }),
    ...(kinds.length > 0 ? { kind: kinds } : {}),
  });

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setAgent(agentDraft.trim());
    setKinds([...kindsDraft]);
  }

  function clearFilters() {
    setAgentDraft("");
    setKindsDraft([]);
    setAgent("");
    setKinds([]);
  }

  const text = timeline.data ?? "";
  const entries = parseTimelineText(text);

  return (
    <section className="panel behavior-timeline-panel" data-testid="behavior-timeline">
      <header className="panel-header">
        <h3>行为时间线</h3>
      </header>
      <div className="panel-body">
        <form className="timeline-filters" onSubmit={applyFilters}>
          <label className="form-field">
            <span className="form-label">伙伴</span>
            <input
              value={agentDraft}
              onChange={(event) => setAgentDraft(event.target.value)}
              placeholder="别名或 id"
              aria-label="行为伙伴过滤"
            />
          </label>
          <fieldset className="kind-filter">
            <legend>行为类型</legend>
            {BEHAVIOR_KIND_OPTIONS.map(([value, label]) => (
              <label key={value}>
                <input
                  type="checkbox"
                  value={value}
                  checked={kindsDraft.includes(value)}
                  onChange={(event) => {
                    if (event.target.checked) {
                      setKindsDraft((current) => [...current, value]);
                    } else {
                      setKindsDraft((current) =>
                        current.filter((kind) => kind !== value),
                      );
                    }
                  }}
                />
                {label}
              </label>
            ))}
          </fieldset>
          <div className="timeline-filter-actions">
            <button type="submit" className="node-action">
              应用过滤
            </button>
            <button type="button" className="node-action" onClick={clearFilters}>
              清除
            </button>
          </div>
        </form>
        {timeline.isPending ? <SkeletonRows count={4} /> : null}
        {timeline.isError ? (
          <ErrorState
            source={`/works/${workspaceId}/behavior/timeline`}
            message={timeline.error.message}
            onRetry={() => void timeline.refetch()}
          />
        ) : null}
        {timeline.isSuccess && text === "" ? (
          <EmptyState
            title="暂无行为记录"
            hint="伙伴的行为轨迹会按时间顺序出现在这里"
          />
        ) : null}
        {timeline.isSuccess && text !== "" ? (
          <>
            {entries.length > 0 ? (
              <ol className="timeline-list">
                {entries.map((entry, index) => (
                  <li
                    className="timeline-entry"
                    key={`${entry.at}-${index}`}
                  >
                    <div className="timeline-entry-head">
                      <span className="timeline-kind">
                        {behaviorKindLabel(entry.kind)}
                      </span>
                      <span className="timeline-actor">{entry.actor}</span>
                      <span className="timeline-arrow">→</span>
                      <span className="timeline-target">{entry.target}</span>
                      <time className="timeline-at">
                        {entry.at.slice(5, 16).replace("T", " ")}
                      </time>
                    </div>
                    <p className="timeline-content">{entry.content}</p>
                    {entry.source !== "" ? (
                      <p className="timeline-source">来源 {entry.source}</p>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : null}
            <details className="motive-raw">
              <summary>CLI 原文</summary>
              <pre className="plain-output" data-testid="timeline-report">
                {text}
              </pre>
            </details>
          </>
        ) : null}
      </div>
    </section>
  );
}

function BehaviorStatePanel({ workspaceId }: { workspaceId: string }) {
  const state = useBehaviorState(workspaceId);
  const text = state.data ?? "";
  const groups = groupBehaviorStateByActor(parseBehaviorStateText(text));

  return (
    <section className="panel behavior-state-panel" data-testid="behavior-state">
      <header className="panel-header">
        <h3>当前状态</h3>
      </header>
      <div className="panel-body">
        {state.isPending ? <SkeletonRows count={4} /> : null}
        {state.isError ? (
          <ErrorState
            source={`/works/${workspaceId}/behavior`}
            message={state.error.message}
            onRetry={() => void state.refetch()}
          />
        ) : null}
        {state.isSuccess && text.trim() === "" ? (
          <EmptyState
            title="暂无状态数据"
            hint="每位伙伴当前的耐心、关系与立场状态在这里"
          />
        ) : null}
        {state.isSuccess && text.trim() !== "" ? (
          <>
            {groups.length > 0 ? (
              <div className="state-groups">
                {groups.map((group) => (
                  <div className="state-group" key={group.actor}>
                    <h4 className="state-actor">{group.actor}</h4>
                    <ul className="state-list">
                      {group.entries.map((entry, index) => (
                        <li
                          className="state-entry"
                          key={`${entry.kind}-${index}`}
                        >
                          <span className="timeline-kind">
                            {behaviorKindLabel(entry.kind)}
                          </span>
                          <span className="state-target">{entry.target}</span>
                          <p className="state-content">{entry.content}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            ) : null}
            <details className="motive-raw">
              <summary>CLI 原文</summary>
              <pre
                className="plain-output"
                data-testid="behavior-state-report"
              >
                {text}
              </pre>
            </details>
          </>
        ) : null}
      </div>
    </section>
  );
}

export default function FreewillPage() {
  const { workspaceId } = useParams();
  useWorkspaceSelection(workspaceId);
  const workspaceIdValue = workspaceId ?? "";

  const state = useBehaviorState(workspaceIdValue);
  const timeline = useBehaviorTimeline(workspaceIdValue, {});
  const motives = useMotives(workspaceIdValue);

  const timelineEntries = parseTimelineText(timeline.data ?? "");
  const stateGroups = groupBehaviorStateByActor(
    parseBehaviorStateText(state.data ?? ""),
  );
  const motiveCount = parseMotiveText(motives.data ?? "").length;

  return (
    <section
      className="freewill-page"
      data-testid="freewill-page"
      data-workspace={workspaceId}
    >
      <header className="page-header">
        <h2>编辑部</h2>
        <div className="workspace-toolbar">
          <Link
            className="text-link"
            to={`/works/${workspaceIdValue}/talk`}
            data-testid="talk-entry-link"
          >
            去对话看讨论与自然讨论标记
          </Link>
          <Link className="text-link" to={`/works/${workspaceIdValue}`}>
            返回作品
          </Link>
        </div>
      </header>

      <div className="kpi-row">
        <div className="kpi">
          <span className="kpi-value">{stateGroups.length}</span>
          <span className="kpi-label">有位伙伴的状态</span>
        </div>
        <div className="kpi">
          <span className="kpi-value">{timelineEntries.length}</span>
          <span className="kpi-label">行为记录</span>
        </div>
        <div className="kpi kpi--accent">
          <span className="kpi-value">{motiveCount}</span>
          <span className="kpi-label">动机</span>
        </div>
      </div>

      <div className="overview-layout">
        <div className="overview-primary">
          <BehaviorTimelinePanel workspaceId={workspaceIdValue} />
        </div>
        <div className="overview-secondary">
          <BehaviorStatePanel workspaceId={workspaceIdValue} />
          <MotivesPanel workspaceId={workspaceIdValue} />
          <PatiencePanel workspaceId={workspaceIdValue} />
        </div>
      </div>
    </section>
  );
}
