import { useMemo, useState } from "react";
import { getEditorialOverview, getMailbox } from "../api.js";
import { EmptyState, ErrorState, LoadingState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { Badge } from "../components/ui/badge.jsx";
import { Input } from "../components/ui/input.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select.jsx";
import { avatarColorOf, displayNameOf } from "../lib/agent-custom.js";
import { cn } from "../lib/utils.js";
import { useApi } from "../lib/use-api.js";

const KIND_META = {
  review_feedback: ["审稿", "accent"],
  reply: ["回复", "neutral"],
  topic_request: ["议题", "warn"],
  broadcast: ["广播", "neutral"],
  note: ["便签", "neutral"],
};

const STATUS_META = {
  unread: ["未读", "accent"],
  read: ["已读", "neutral"],
  resolved: ["已解决", "ok"],
  archived: ["已归档", "neutral"],
};

const agentName = (id) => displayNameOf({ file: `${id}.md`, name: id });
const agentColor = (id) => avatarColorOf(`${id}.md`);

/** 消息流：按主题线程聚合成会话视图。@stable */
export default function EditorialPage() {
  const { data: overview, error: overviewError, loading: overviewLoading, refresh } = useApi(getEditorialOverview, {
    interval: 15000,
  });
  const { data: mailbox, error: mailError, loading: mailLoading } = useApi(() => getMailbox("", 500), {
    interval: 10000,
  });
  const [view, setView] = useState("all");
  const [agentFilter, setAgentFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [activeThreadId, setActiveThreadId] = useState(null);

  const messages = mailbox?.messages || [];
  const unreadTotal = messages.filter((m) => m.status === "unread").length;

  const threads = useMemo(() => {
    const byId = new Map(messages.map((m) => [String(m.id), m]));
    const rootOf = (m) => {
      let cur = m;
      const seen = new Set();
      while (cur.reply_to && byId.has(String(cur.reply_to)) && !seen.has(String(cur.id))) {
        seen.add(String(cur.id));
        cur = byId.get(String(cur.reply_to));
      }
      return cur;
    };
    const groups = new Map();
    for (const m of messages) {
      const root = rootOf(m);
      const key = String(root.id);
      if (!groups.has(key)) {
        groups.set(key, { key, root, items: [] });
      }
      groups.get(key).items.push(m);
    }
    const built = [...groups.values()].map((g) => {
      const items = g.items.sort((a, b) => Number(a.id) - Number(b.id));
      const last = items[items.length - 1];
      const participants = [...new Set(items.flatMap((m) => [m.from_agent, m.to_agent]))];
      return {
        ...g,
        items,
        last,
        participants,
        title: g.root.subject || `${agentName(participants[0])} ↔ ${agentName(participants[1] || "")}`,
        unread: items.filter((m) => m.status === "unread").length,
      };
    });
    return built;
  }, [messages]);

  const filtered = useMemo(() => {
    let list = threads;
    if (view === "unread") list = list.filter((t) => t.unread > 0);
    if (view !== "all" && view !== "unread") {
      list = list.filter((t) => t.items.some((m) => m.kind === view));
    }
    if (agentFilter !== "all") {
      list = list.filter((t) => t.participants.includes(agentFilter));
    }
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      list = list.filter((t) =>
        t.items.some(
          (m) =>
            String(m.subject || "").toLowerCase().includes(q) ||
            String(m.body || "").toLowerCase().includes(q),
        ),
      );
    }
    return [...list].sort((a, b) => {
      if (a.unread !== b.unread) return b.unread - a.unread;
      return Number(b.last.id) - Number(a.last.id);
    });
  }, [threads, view, agentFilter, query]);

  const active = filtered.find((t) => t.key === activeThreadId) || filtered[0] || null;
  const error = overviewError || mailError;
  const loading = overviewLoading || mailLoading;
  const agents = overview?.agents || [];

  return (
    <>
      <PageHeader
        title="消息流"
        desc="编辑之间的协作消息，按话题聚合"
        actions={
          unreadTotal > 0 ? (
            <Badge tone="bad">{unreadTotal} 条未读</Badge>
          ) : (
            <Badge tone="ok">全部已读</Badge>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-2.5 border-t border-line py-3">
        <div className="inline-flex overflow-hidden rounded-control border border-line">
          {[
            ["all", "全部"],
            ["unread", "未读"],
            ["review_feedback", "审稿"],
            ["topic_request", "议题"],
            ["note", "便签"],
          ].map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setView(id)}
              className={cn(
                "h-8 border-r border-line px-3 text-xs transition-colors last:border-r-0",
                view === id ? "bg-ink font-semibold text-canvas" : "text-ink-2 hover:text-ink",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <Select value={agentFilter} onValueChange={setAgentFilter}>
          <SelectTrigger className="h-8 w-[150px] text-xs">
            <SelectValue placeholder="全部编辑" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部编辑</SelectItem>
            {agents.map((a) => (
              <SelectItem key={a.file} value={a.file.replace(/\.md$/, "")}>
                {agentName(a.file.replace(/\.md$/, ""))}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          className="h-8 max-w-[220px] text-xs"
          placeholder="搜索标题或内容"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="ml-auto text-xs text-ink-3">
          {filtered.length} 个会话 · {messages.length} 条消息
        </span>
      </div>

      {error ? (
        <ErrorState message="消息加载失败" detail={error} onRetry={refresh} />
      ) : loading ? (
        <LoadingState rows={6} />
      ) : filtered.length ? (
        <div className="grid min-h-[420px] grid-cols-1 overflow-hidden rounded-card border border-line bg-surface lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <aside className="min-w-0 border-b border-line lg:border-b-0 lg:border-r">
            <div className="max-h-[640px] overflow-y-auto">
              {filtered.map((t) => {
                const meta = KIND_META[t.last.kind] || ["消息", "neutral"];
                return (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => setActiveThreadId(t.key)}
                    className={cn(
                      "flex w-full items-start gap-3 border-b border-line px-4 py-3 text-left transition-colors last:border-b-0",
                      active?.key === t.key ? "bg-surface-2" : "hover:bg-surface-2/60",
                    )}
                  >
                    <div className="flex -space-x-1.5 shrink-0">
                      {t.participants.slice(0, 2).map((p) => (
                        <span
                          key={p}
                          className="grid size-7 place-items-center rounded-lg border-2 border-surface text-[11px] font-semibold text-white"
                          style={{ background: agentColor(p) }}
                        >
                          {agentName(p).slice(0, 1)}
                        </span>
                      ))}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline gap-2">
                        <span className="truncate text-[13px] font-semibold text-ink">{t.title}</span>
                        {t.unread > 0 && (
                          <span className="ml-auto shrink-0 rounded-pill bg-bad-soft px-1.5 text-[10px] font-semibold text-bad">
                            {t.unread}
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-3">
                        <span>{t.participants.map(agentName).join("、")}</span>
                        <span>·</span>
                        <span>{String(t.last.created_at || "").slice(5, 16)}</span>
                      </div>
                      <p className="mt-1 line-clamp-1 text-xs text-ink-2">{t.last.body}</p>
                    </div>
                    <Badge tone={meta[1]} className="mt-0.5 shrink-0">
                      {meta[0]}
                    </Badge>
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="min-w-0">
            {active ? (
              <>
                <div className="border-b border-line px-5 py-3.5">
                  <div className="text-sm font-bold text-ink">{active.title}</div>
                  <div className="mt-0.5 text-xs text-ink-3">
                    {active.participants.map(agentName).join("、")} · {active.items.length} 条消息
                  </div>
                </div>
                <div className="max-h-[560px] overflow-y-auto bg-surface-2/60 px-5 py-4">
                  {active.items.map((m) => {
                    const status = STATUS_META[m.status] || ["—", "neutral"];
                    return (
                      <div key={m.id} className="mb-4 flex gap-2.5">
                        <span
                          className="grid size-8 shrink-0 place-items-center rounded-lg text-xs font-semibold text-white"
                          style={{ background: agentColor(m.from_agent) }}
                        >
                          {agentName(m.from_agent).slice(0, 1)}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="mb-1 flex flex-wrap items-baseline gap-2">
                            <span className="text-[13px] font-semibold text-ink">
                              {agentName(m.from_agent)}
                              <span className="font-normal text-ink-3"> → {agentName(m.to_agent)}</span>
                            </span>
                            <span className="font-mono text-[10.5px] text-ink-3">{m.created_at}</span>
                            <Badge tone={status[1]} className="ml-auto">
                              {status[0]}
                            </Badge>
                          </div>
                          <div className="rounded-md border border-line bg-surface p-2.5">
                            {m.subject ? (
                              <div className="mb-1 text-xs font-semibold text-ink">{m.subject}</div>
                            ) : null}
                            <p className="whitespace-pre-wrap text-xs leading-relaxed text-ink-2">{m.body}</p>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : (
              <EmptyState title="没有可展示的会话" />
            )}
          </section>
        </div>
      ) : (
        <EmptyState title="没有符合条件的消息" hint="调整筛选条件，或等编辑们开始协作。" />
      )}

      {overview?.actions?.length ? (
        <section className="mt-6 min-w-0">
          <div className="mb-2.5 flex items-baseline justify-between">
            <h2 className="text-xs font-semibold tracking-[0.02em] text-ink">今日任务</h2>
            <span className="text-xs text-ink-3">{overview.actions.length} 项</span>
          </div>
          <div className="border-t border-line">
            {overview.actions.slice(0, 5).map((a) => (
              <div key={a.id} className="border-b border-line py-2 text-xs last:border-b-0">
                <span className="font-medium text-ink">{a.task}</span>
                <span className="text-ink-3">
                  {" "}· {agentName(a.assignee || a.claimed_by)} · {a.status}
                </span>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}
