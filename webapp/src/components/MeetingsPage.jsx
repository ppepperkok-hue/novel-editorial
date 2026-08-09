import { useEffect, useState } from "react";
import { advanceSession, getMeetings, getSession, startMeeting } from "../api.js";
import { fmtTime } from "./ui.jsx";

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
};

const COLORS = [
  "linear-gradient(135deg,#38bdf8,#0ea5e9)",
  "linear-gradient(135deg,#818cf8,#6366f1)",
  "linear-gradient(135deg,#34d399,#10b981)",
  "linear-gradient(135deg,#fbbf24,#f59e0b)",
  "linear-gradient(135deg,#f472b6,#ec4899)",
  "linear-gradient(135deg,#a78bfa,#8b5cf6)",
  "linear-gradient(135deg,#f87171,#ef4444)",
  "linear-gradient(135deg,#2dd4bf,#14b8a6)",
  "linear-gradient(135deg,#fb923c,#f97316)",
];

const colorOf = (name) => COLORS[Math.abs([...name].reduce((a, c) => a + c.charCodeAt(0), 0)) % COLORS.length];

const SPEECH_FIELDS = [
  ["weekly_summary", "本周小结"],
  ["feelings", "感受"],
  ["opinion", "意见"],
  ["concerns", "顾虑"],
  ["proposals", "提案"],
  ["priority", "优先级"],
];

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState([]);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);
  const [topic, setTopic] = useState("");
  const [starting, setStarting] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);
  const [session, setSession] = useState(null);
  const [sessionPoll, setSessionPoll] = useState(0);
  const [instruction, setInstruction] = useState("");
  const [advancing, setAdvancing] = useState(false);

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
        setSession({ id: r.session_id, topic: topic.trim(), status: "running" });
        setInstruction("");
        setSessionPoll((t) => t + 1);
      }
    } finally {
      setStarting(false);
    }
  };

  useEffect(() => {
    if (!session) return;
    let alive = true;
    const load = async () => {
      try {
        const s = await getSession(session.id);
        if (alive) {
          setSession((prev) => (prev && prev.id === s.id ? s : prev));
          if (s.status === "finished" || s.status === "failed") {
            setRefreshTick((t) => t + 1);
          }
        }
      } catch {
        // keep polling
      }
    };
    load();
    const t = setInterval(load, 2500);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [sessionPoll, session?.id]);

  const nextRound = async () => {
    setAdvancing(true);
    try {
      const r = await advanceSession(session.id, instruction);
      setError(r.ok ? "" : "推进失败：" + (r.error || "未知"));
      if (r.ok) {
        setInstruction("");
        setSessionPoll((t) => t + 1);
      }
    } finally {
      setAdvancing(false);
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

      {session ? (
        <section className="panel overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--line)] px-4 py-3">
            <span className="text-sm font-bold">会议直播 · {session.topic || "专题会议"}</span>
            <span className={`chip ${
              session.status === "running" ? "chip-warn" :
              session.status === "awaiting_input" ? "chip-info" :
              session.status === "finished" ? "chip-ok" : "chip-bad"
            }`}>
              {session.status === "running" && `第 ${session.current_round || 1} 轮讨论中…`}
              {session.status === "awaiting_input" && "等待你的指示"}
              {session.status === "finished" && "已完成"}
              {session.status === "failed" && "失败"}
            </span>
            {session.attendees?.length ? (
              <span className="muted text-xs">参会：{session.attendees.map((a) => AGENT_NAMES[a] || a).join("、")}</span>
            ) : null}
            <button className="btn ml-auto !px-2.5 !py-1 text-xs" onClick={() => setSession(null)}>关闭</button>
          </div>

          <div className="max-h-[420px] overflow-y-auto bg-[var(--bg-soft)] p-4">
            {(session.transcript || []).map((m, i) => (
              <div key={i} className="mb-3 flex gap-2.5">
                <div
                  className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-xs font-bold text-[#0a0e17]"
                  style={{ background: colorOf(m.agent) }}
                >
                  {(AGENT_NAMES[m.agent] || m.agent).slice(0, 1)}
                </div>
                <div className="min-w-0 flex-1 rounded-xl rounded-tl-sm border border-[var(--line)] bg-[var(--panel)] p-3">
                  <div className="mb-1.5 flex items-center gap-2">
                    <span className="text-xs font-bold">{AGENT_NAMES[m.agent] || m.agent}</span>
                    <span className="chip">第 {m.round} 轮</span>
                  </div>
                  <div className="grid grid-cols-1 gap-1.5 lg:grid-cols-2">
                    {SPEECH_FIELDS.map(([k, l]) => {
                      const v = m.speech?.[k];
                      if (v === undefined || v === null || v === "") return null;
                      return (
                        <div key={k} className="text-xs leading-relaxed text-slate-300">
                          <span className="mr-1.5 text-[var(--accent-text)]">{l}：</span>
                          {Array.isArray(v) ? v.join("；") : typeof v === "object" ? JSON.stringify(v) : v}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            ))}
            {!(session.transcript || []).length ? (
              <div className="muted py-6 text-center text-sm">会议准备中，主席正在点将…</div>
            ) : null}
          </div>

          {session.status === "awaiting_input" ? (
            <div className="border-t border-[var(--line)] px-4 py-3">
              <div className="mb-1.5 text-xs font-semibold">给下一轮的指示（可留空直接继续）</div>
              <div className="flex gap-2">
                <input
                  className="input flex-1"
                  placeholder="例：大家针对主角的性格再讨论一下 / 把伏笔回收提前"
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && nextRound()}
                />
                <button className="btn btn-primary" disabled={advancing} onClick={nextRound}>
                  {advancing ? "推进中…" : "继续下一轮"}
                </button>
              </div>
            </div>
          ) : null}

          {session.status === "finished" && session.report ? (
            <div className="border-t border-[var(--line)] px-4 py-3">
              <div className="mb-1.5 text-xs font-semibold">会议结论</div>
              <div className="text-xs leading-relaxed text-slate-300">{session.report.discussion_summary || "（无摘要）"}</div>
              {(session.report.action_items || []).length ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {(session.report.action_items || []).map((a, i) => (
                    <span key={i} className="chip chip-info">{typeof a === "string" ? a : JSON.stringify(a)}</span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}

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
