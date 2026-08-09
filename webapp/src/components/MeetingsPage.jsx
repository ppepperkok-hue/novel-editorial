import { useEffect, useState } from "react";
import { getMeetings, startMeeting } from "../api.js";
import { fmtTime } from "./ui.jsx";

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState([]);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);
  const [topic, setTopic] = useState("");
  const [starting, setStarting] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let alive = true;
    getMeetings()
      .then((r) => alive && setMeetings(r.meetings || []))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [refreshTick]);

  const start = async () => {
    if (!topic.trim()) return;
    setStarting(true);
    try {
      const r = await startMeeting(topic.trim());
      setTopic("");
      setError(r.ok ? "" : "启动失败：" + (r.error || "未知"));
      if (r.ok) {
        setDetail("started");
        setTimeout(() => setDetail(null), 6000);
        setTimeout(() => setRefreshTick((t) => t + 1), 8000);
      }
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <section className="panel p-4">
        <div className="section-title !mb-3">发起专题会议</div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="min-w-[280px] flex-1 text-xs muted">
            会议主题
            <input
              className="input mt-1"
              placeholder="例：讨论主角下一段剧情如何发展 / 这个副本怎么设计"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && start()}
            />
          </label>
          <button className="btn btn-primary" disabled={starting || !topic.trim()} onClick={start}>
            {starting ? "启动中…" : "▦ 一键组织 Agent 开会"}
          </button>
        </div>
        <div className="muted mt-2 text-xs leading-relaxed">
          会议与周会共用同一套引擎：主席点将、3 轮相互通气、主席总结。每个参会 Agent
          会后会把会议主题与自己的发言写入记忆（日记），之后的周会也会参考这些记忆。
        </div>
        {detail === "started" ? (
          <div className="mt-2 rounded-md border border-emerald-800/50 bg-emerald-950/20 px-3 py-2 text-xs text-emerald-300">
            专题会议已启动，预计几分钟完成，稍后自动出现在下方档案里。
          </div>
        ) : null}
      </section>

      {error ? (
        <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm text-red-400">
          周会档案加载失败：{error}
        </div>
      ) : null}

      {!meetings.length && !error ? (
        <div className="panel">
          <div className="empty">还没有周会记录。每周日或手动触发周会后，这里会存档完整会议。</div>
        </div>
      ) : null}

      {meetings.map((m) => (
        <section key={m.id} className="panel p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold">周会 #{m.id}</span>
            <span className="chip">{fmtTime(m.held_at)}</span>
            <span className={`chip ${m.kind === "topic" ? "chip-warn" : "chip-info"}`}>
              {m.kind === "topic" ? "专题会议" : "周会"}
            </span>
            <span className={`chip ${m.status === "completed" ? "chip-ok" : "chip-warn"}`}>{m.status}</span>
            <button className="btn ml-auto !px-3 !py-1 text-xs" onClick={() => setDetail(detail === m.id ? null : m.id)}>
              {detail === m.id ? "收起" : "查看报告"}
            </button>
          </div>
          <div className="muted mt-2 text-xs">
            参会：{m.attendees.join("、")} · 议题：{m.topics.join("、")}
          </div>
          <div className="mt-2 text-sm leading-relaxed text-slate-300">{m.summary || "（无摘要）"}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {m.blueprint_count ? <span className="chip chip-info">蓝图 {m.blueprint_count} 条</span> : null}
            {m.volume_goal_adjust ? <span className="chip chip-warn">卷目标：{m.volume_goal_adjust.slice(0, 30)}</span> : null}
            {m.action_items?.length ? <span className="chip">行动项 {m.action_items.length}</span> : null}
          </div>

          {detail === m.id ? (
            <div className="mt-3 rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-3">
              <div className="label !mb-2">完整报告（JSON）</div>
              <pre className="code max-h-96 overflow-auto text-xs leading-relaxed">
                {JSON.stringify(m.report, null, 2)}
              </pre>
            </div>
          ) : null}
        </section>
      ))}
    </div>
  );
}
