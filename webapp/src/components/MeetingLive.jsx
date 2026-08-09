import { useEffect, useRef, useState } from "react";
import { advanceSession, getSession, startMeeting } from "../api.js";

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

const colorOf = (name) =>
  COLORS[Math.abs([...name].reduce((a, c) => a + c.charCodeAt(0), 0)) % COLORS.length];

const SPEECH_FIELDS = [
  ["weekly_summary", "本周小结"],
  ["feelings", "感受"],
  ["opinion", "意见"],
  ["concerns", "顾虑"],
  ["proposals", "提案"],
  ["priority", "优先级"],
];

export default function MeetingLive({ onArchived }) {
  const [topic, setTopic] = useState("");
  const [starting, setStarting] = useState(false);
  const [session, setSession] = useState(null);
  const [pollTick, setPollTick] = useState(0);
  const [instruction, setInstruction] = useState("");
  const [advancing, setAdvancing] = useState(false);
  const [msg, setMsg] = useState("");
  const onArchivedRef = useRef(onArchived);

  useEffect(() => {
    onArchivedRef.current = onArchived;
  }, [onArchived]);

  useEffect(() => {
    if (!session) return;
    let alive = true;
    let timer = null;
    const load = async () => {
      try {
        const s = await getSession(session.id);
        if (!alive) return;
        setSession((prev) => {
          if (prev && prev.id === s.id && JSON.stringify(prev) === JSON.stringify(s)) {
            return prev;
          }
          return s;
        });
        if (s.status === "finished" || s.status === "failed") {
          if (timer) clearInterval(timer);
          onArchivedRef.current?.();
        }
      } catch {
        // keep polling
      }
    };
    load();
    timer = setInterval(load, 2500);
    return () => {
      alive = false;
      if (timer) clearInterval(timer);
    };
  }, [pollTick, session?.id]);

  const start = async () => {
    if (!topic.trim()) return;
    setStarting(true);
    try {
      const r = await startMeeting(topic.trim());
      if (r.ok) {
        setSession({ id: r.session_id, topic: topic.trim(), status: "running" });
        setTopic("");
        setInstruction("");
        setMsg("");
      } else {
        setMsg(r.error || "启动失败");
      }
    } finally {
      setStarting(false);
    }
  };

  const nextRound = async () => {
    setAdvancing(true);
    try {
      const r = await advanceSession(session.id, instruction);
      if (r.ok) {
        setInstruction("");
        setPollTick((t) => t + 1);
      } else {
        setMsg(r.error || "推进失败");
      }
    } finally {
      setAdvancing(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {!session ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="min-w-[260px] flex-1 text-xs muted">
            会议主题
            <input
              className="input mt-1"
              placeholder="例：讨论主角下一段剧情如何发展"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && start()}
            />
          </label>
          <button className="btn btn-primary" disabled={starting || !topic.trim()} onClick={start}>
            {starting ? "启动中…" : "▦ 一键组织 Agent 开会"}
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-[var(--line)]">
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

          <div className="max-h-[380px] overflow-y-auto bg-[var(--bg-soft)] p-4">
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
                  placeholder="例：大家针对主角的性格再讨论一下"
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
        </div>
      )}
      {msg ? <div className="text-xs text-red-400">{msg}</div> : null}
      <div className="muted text-xs leading-relaxed">
        与周会共用引擎：主席点将、3 轮相互通气、主席总结；会议结论写入每位 Agent 的记忆。每轮结束后可插话指示。
        还没有作品时直接开会，就是新书选题会——先讨论写什么，结论存档后再建书。
      </div>
    </div>
  );
}
