import { getEditorialOverview, getMailbox } from "../api.js";
import { EmptyState, ErrorState, LoadingState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { Badge } from "../components/ui/badge.jsx";
import { avatarColorOf, displayNameOf } from "../lib/agent-custom.js";
import { useApi } from "../lib/use-api.js";

const AGENT_NAMES = {
  planner: "文策",
  guard: "守界",
  writer: "墨白",
  editor: "润物",
  reviewer: "守正",
  reader: "阿读",
  memory: "录事",
  work_meta: "书案",
  eic: "掌印",
  ending_judge: "终局",
  knowledge_keeper: "博闻",
};

const agentName = (id) => displayNameOf({ file: `${id}.md`, name: AGENT_NAMES[id] || id });
const agentColor = (id) => avatarColorOf(`${id}.md`);

/** 消息流：协作消息 + 今日任务。@stable */
export default function EditorialPage() {
  const { data: overview, error, loading, refresh } = useApi(getEditorialOverview, { interval: 15000 });
  const { data: mailbox } = useApi(() => getMailbox(""), { interval: 10000 });

  const messages = mailbox?.messages || [];
  const unreadCount = messages.filter((m) => m.status === "unread").length;
  const actions = overview?.actions || [];

  return (
    <>
      <PageHeader
        title="消息流"
        desc="编辑之间的协作消息与今日任务"
        actions={
          unreadCount > 0 ? (
            <Badge tone="bad">{unreadCount} 条未读</Badge>
          ) : (
            <Badge tone="ok">全部已读</Badge>
          )
        }
      />
      <div className="grid grid-cols-1 gap-7 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section className="min-w-0">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-xs font-semibold tracking-[0.02em] text-ink">收件箱</h2>
            <span className="text-xs text-ink-3">{messages.length} 条消息</span>
          </div>
          {error ? (
            <ErrorState message="消息加载失败" detail={error} onRetry={refresh} />
          ) : loading ? (
            <LoadingState rows={4} />
          ) : messages.length ? (
            <div className="border-t border-line">
              {messages.slice(0, 30).map((m) => (
                <div key={m.id} className="grid grid-cols-[56px_1fr_auto] items-start gap-3 border-b border-line py-3">
                  <div className="flex items-center">
                    <span
                      className="grid size-6 shrink-0 place-items-center rounded-md text-[11px] font-semibold text-white"
                      style={{ background: agentColor(m.from_agent) }}
                    >
                      {agentName(m.from_agent).slice(0, 1)}
                    </span>
                    <span className="ml-1 text-[11px] text-ink-3">→</span>
                    <span
                      className="grid size-6 shrink-0 place-items-center rounded-md text-[11px] font-semibold text-white"
                      style={{ background: agentColor(m.to_agent) }}
                    >
                      {agentName(m.to_agent).slice(0, 1)}
                    </span>
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="truncate text-[13px] font-semibold text-ink">{m.subject}</span>
                      {m.status === "unread" && <span className="size-1.5 shrink-0 rounded-full bg-bad" />}
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-xs leading-relaxed text-ink-2">{m.body}</p>
                    <p className="mt-0.5 text-[11px] text-ink-3">
                      {agentName(m.from_agent)} → {agentName(m.to_agent)} · {m.created_at}
                    </p>
                  </div>
                  <Badge tone={m.status === "unread" ? "accent" : "neutral"}>{m.status}</Badge>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="收件箱是空的" hint="Agent 之间的审稿打回、提案与协作消息会出现在这里。" />
          )}
        </section>

        <aside className="min-w-0">
          <section className="min-w-0">
            <h2 className="mb-2.5 text-xs font-semibold text-ink">今日任务</h2>
            {actions.length ? (
              actions.slice(0, 8).map((a) => (
                <div key={a.id} className="border-t border-line py-2.5 first:border-t-0">
                  <div className="text-[13px] font-semibold text-ink">{a.task}</div>
                  <div className="mt-0.5 text-xs text-ink-2">
                    {agentName(a.assignee || a.claimed_by)} · {a.status}
                    {a.due_at ? ` · 截止 ${a.due_at}` : ""}
                  </div>
                </div>
              ))
            ) : (
              <p className="text-xs leading-relaxed text-ink-3">今天没有待办行动项。</p>
            )}
          </section>
        </aside>
      </div>
    </>
  );
}
