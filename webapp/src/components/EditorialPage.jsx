import { useEffect, useState } from "react";
import { claimAction, getEditorialOverview, getMailbox } from "../api.js";

const STATUS_META = {
  pending: ["待认领", "chip-warn"],
  claimed: ["已认领", "chip-info"],
  in_progress: ["进行中", "chip-warn"],
  done: ["已完成", "chip-ok"],
  skipped: ["已跳过", "chip-bad"],
};

function Kpi({ label, value }) {
  return (
    <div className="card kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
    </div>
  );
}

function MessageList({ messages }) {
  if (!messages.length) {
    return <div className="muted text-xs">收件箱是空的，agent 之间还没说过话。</div>;
  }
  return (
    <div className="flex flex-col gap-2">
      {messages.map((m) => (
        <div key={m.id} className="rounded-lg border border-[var(--line-soft)] bg-[var(--bg-soft)] px-3 py-2">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-semibold">{m.from_agent}</span>
            <span className="muted">→</span>
            <span className="font-semibold">{m.to_agent}</span>
            <span className="chip chip-info">{m.kind}</span>
            <span className={`chip ${m.status === "unread" ? "chip-warn" : "chip-soft"}`}>
              {m.status}
            </span>
            <span className="muted ml-auto">{String(m.created_at || "").slice(5, 16)}</span>
          </div>
          {m.subject ? <div className="mt-1 text-xs font-semibold">{m.subject}</div> : null}
          <div className="muted mt-0.5 line-clamp-2 text-xs leading-relaxed">{m.body}</div>
        </div>
      ))}
    </div>
  );
}

function TaskBoard({ actions, agents, onClaim }) {
  const groups = {
    pending: [],
    claimed: [],
    in_progress: [],
    done: [],
  };
  for (const a of actions || []) {
    (groups[a.status] = groups[a.status] || []).push(a);
  }
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
      {Object.entries(groups).map(([status, items]) => {
        const meta = STATUS_META[status] || [status, "chip-soft"];
        return (
          <div key={status} className="rounded-lg border border-[var(--line-soft)] bg-[var(--bg-soft)] p-2.5">
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="font-semibold">{meta[0]}</span>
              <span className="muted">{items.length}</span>
            </div>
            <div className="flex flex-col gap-1.5">
              {items.slice(0, 8).map((a) => (
                <div key={a.id} className="rounded-md border border-[var(--line)] bg-[var(--bg)] px-2 py-1.5 text-xs">
                  <div className="line-clamp-2 leading-snug">{a.task}</div>
                  <div className="muted mt-1 flex flex-wrap gap-1 text-[11px]">
                    <span>负责：{a.assignee || a.agent || "—"}</span>
                    {a.claimed_by ? <span>认领：{a.claimed_by}</span> : null}
                    {a.due_at ? <span>期限：{a.due_at}</span> : null}
                  </div>
                  {status === "pending" && !a.claimed_by ? (
                    <div className="mt-1.5 flex items-center gap-1">
                      <select
                        className="input !h-6 !px-1 text-[11px]"
                        defaultValue={a.assignee || a.agent || (agents[0]?.name || "")}
                        data-action-id={a.id}
                      >
                        {agents.map((ag) => (
                          <option key={ag.file} value={ag.name}>
                            {ag.name}
                          </option>
                        ))}
                      </select>
                      <button
                        className="btn !px-2 !py-0.5 text-[11px]"
                        onClick={() => {
                          const sel = document.querySelector(`[data-action-id="${a.id}"]`);
                          onClaim(a.id, sel?.value || agents[0]?.name || "");
                        }}
                      >
                        认领
                      </button>
                    </div>
                  ) : null}
                </div>
              ))}
              {!items.length ? <div className="muted text-[11px]">暂无</div> : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RelationTable({ relations }) {
  if (!relations.length) {
    return <div className="muted text-xs">还没有建立关系，协作多了自然会出现。</div>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>谁</th>
          <th>和谁</th>
          <th>熟悉</th>
          <th>信任</th>
          <th>摩擦</th>
        </tr>
      </thead>
      <tbody>
        {relations.map((r) => (
          <tr key={r.id}>
            <td>{r.agent}</td>
            <td>{r.other}</td>
            <td className="tabular-nums">{Number(r.familiarity || 0).toFixed(2)}</td>
            <td className="tabular-nums">{Number(r.trust || 0).toFixed(2)}</td>
            <td className="tabular-nums">{Number(r.friction || 0).toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ActivityByAgent({ items }) {
  const byAgent = {};
  for (const a of items || []) {
    (byAgent[a.agent] = byAgent[a.agent] || []).push(a);
  }
  const agents = Object.keys(byAgent);
  if (!agents.length) {
    return <div className="muted text-xs">今天还没有活动记录。</div>;
  }
  return (
    <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
      {agents.map((agent) => (
        <div key={agent} className="rounded-lg border border-[var(--line-soft)] bg-[var(--bg-soft)] p-2.5">
          <div className="mb-1.5 text-xs font-semibold">{agent}</div>
          <div className="flex flex-col gap-1">
            {byAgent[agent].slice(0, 6).map((a) => (
              <div key={a.id} className="muted text-[11px] leading-snug">
                <span className="chip chip-soft mr-1">{a.activity_type}</span>
                {a.title}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function EditorialPage() {
  const [overview, setOverview] = useState(null);
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [o, m] = await Promise.all([getEditorialOverview(), getMailbox("")]);
        if (alive) {
          setOverview(o);
          setMessages(m.messages || []);
          setError("");
        }
      } catch (e) {
        if (alive) setError(String(e));
      }
    };
    load();
    const t = setInterval(load, 30000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const unreadTotal = Object.values(overview?.unread || {}).reduce((s, n) => s + n, 0);
  const openActions = (overview?.actions || []).filter(
    (a) => a.status !== "done" && a.status !== "skipped",
  ).length;
  const agents = overview?.agents || [];

  const handleClaim = async (actionId, agent) => {
    try {
      const r = await claimAction(actionId, agent);
      if (r.ok) {
        const [o, m] = await Promise.all([getEditorialOverview(), getMailbox("")]);
        setOverview(o);
        setMessages(m.messages || []);
      } else {
        setError(r.error || "认领失败");
      }
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm text-red-400">
          编辑部数据不可达：{error}
        </div>
      ) : null}
      <div className="kpi-grid">
        <Kpi label="编辑（Agent）" value={overview?.agents?.length ?? "—"} />
        <Kpi label="未读消息" value={unreadTotal} />
        <Kpi label="待办进行中" value={openActions} />
        <Kpi label="今日活动" value={overview?.today_activity?.length ?? "—"} />
      </div>
      <section className="panel p-4">
        <div className="section-title !mb-3">任务板</div>
        <TaskBoard actions={overview?.actions || []} agents={agents} onClaim={handleClaim} />
      </section>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="panel p-4">
          <div className="section-title !mb-3">消息流</div>
          <MessageList messages={messages} />
        </section>
        <section className="panel p-4">
          <div className="section-title !mb-3">关系网</div>
          <div className="table-wrap">
            <RelationTable relations={overview?.relations || []} />
          </div>
        </section>
      </div>
      <section className="panel p-4">
        <div className="section-title !mb-3">每人今日</div>
        <ActivityByAgent items={overview?.today_activity || []} />
      </section>
    </div>
  );
}
