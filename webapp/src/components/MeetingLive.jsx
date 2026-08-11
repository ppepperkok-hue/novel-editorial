import { useEffect, useRef, useState } from "react";
import {
  advanceSession,
  cancelMeeting,
  getActiveSession,
  getSession,
  startMeeting,
} from "../api.js";
import { ConfirmDialog } from "./ui.jsx";

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

const KIND_LABELS = {
  weekly: "编辑部例会",
  topic: "剧情碰头会",
  planning: "选题会",
  critique: "单章会诊",
  retro: "数据复盘会",
  review: "收尾会",
  incident: "危机处理会",
  learning: "知识分享会",
  free: "茶水间闲聊",
};


function RawSpeech({ raw }) {
  let display = raw;
  try {
    const obj = JSON.parse(raw);
    if (obj && typeof obj === "object") {
      display = obj.speech || obj.opinion || obj.weekly_summary || JSON.stringify(obj, null, 2);
    }
  } catch (e) {
    /* keep raw text */
  }
  return (
    <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">{display}</div>
  );
}

export default function MeetingLive({ onArchived }) {
  const [topic, setTopic] = useState("");
  const [meetingKind, setMeetingKind] = useState("topic");
  const [starting, setStarting] = useState(false);
  const [session, setSession] = useState(null);
  const [pollTick, setPollTick] = useState(0);
  const [nowMs, setNowMs] = useState(Date.now());
  const [instruction, setInstruction] = useState("");
  const [advancing, setAdvancing] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
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

  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    // restore an in-progress meeting after a page refresh
    getActiveSession()
      .then((r) => {
        if (r?.session) setSession(r.session);
      })
      .catch(() => {});
  }, []);

  const start = async () => {
    if (!topic.trim()) return;
    setStarting(true);
    try {
      const r = await startMeeting(topic.trim(), meetingKind);
      if (r.ok) {
        setSession({
          id: r.session_id,
          topic: topic.trim(),
          status: "running",
          kind: meetingKind,
        });
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
      const r = await advanceSession(session.id, instruction, false);
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

  const finishMeeting = async () => {
    setAdvancing(true);
    try {
      const r = await advanceSession(session.id, "", true);
      if (r.ok) {
        setInstruction("");
        setPollTick((t) => t + 1);
      } else {
        setMsg(r.error || "结束失败");
      }
    } finally {
      setAdvancing(false);
    }
  };

  const doCancel = async () => {
    setAdvancing(true);
    try {
      const r = await cancelMeeting(session.id);
      setConfirmCancel(false);
      if (r.ok) {
        setSession(null);
        onArchivedRef.current?.();
      } else {
        setMsg(r.error || "取消失败");
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
          <label className="text-xs muted">
            会议类型
            <select
              className="input mt-1"
              value={meetingKind}
              onChange={(e) => setMeetingKind(e.target.value)}
            >
              {Object.entries(KIND_LABELS).map(([k, label]) => (
                <option key={k} value={k}>{label}</option>
              ))}
            </select>
          </label>
          <button className="btn btn-primary" disabled={starting || !topic.trim()} onClick={start}>
            {starting ? "启动中…" : "▦ 一键组织 Agent 开会"}
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-[var(--line)]">
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--line)] px-4 py-3">
            <span className="text-sm font-bold">
              会议直播 · {session.topic || KIND_LABELS[session.kind] || "专题会议"}
            </span>
            {session.kind ? (
              <span className="chip chip-info">{KIND_LABELS[session.kind] || session.kind}</span>
            ) : null}
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
            {session.status === "running" && session.current_agent ? (
              <span className="chip chip-info !px-2 !py-0.5 text-xs">
                <span className="mr-1 inline-block animate-pulse">●</span>
                {AGENT_NAMES[session.current_agent] || session.current_agent} 正在思考…
                {(() => {
                  const hb = session.heartbeat_at
                    ? new Date(String(session.heartbeat_at).replace(" ", "T")).getTime()
                    : 0;
                  const secs = hb ? Math.max(0, Math.floor((nowMs - hb) / 1000)) : 0;
                  return secs > 300 ? `已 ${Math.floor(secs / 60)} 分钟，可能卡住` : `已 ${secs} 秒`;
                })()}
              </span>
            ) : null}
            {session.attendees?.length ? (
              <span className="muted text-xs">参会：{session.attendees.map((a) => AGENT_NAMES[a] || a).join("、")}</span>
            ) : null}
            <button className="btn ml-auto !px-2.5 !py-1 text-xs" onClick={() => setConfirmCancel(true)}>
              取消会议
            </button>
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
                    <span className="muted text-xs">第 {m.round} 轮</span>
                    {(m.speech?._tools_used || []).map((t) => (
                      <span key={t} className="chip chip-info !px-1.5 !py-0.5 text-[10px]">⚙ {t}</span>
                    ))}
                  </div>
                  {m.speech?.speech ? (
                    <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
                      {m.speech.speech}
                    </div>
                  ) : SPEECH_FIELDS.some(([k]) => {
                    const v = m.speech?.[k];
                    return v !== undefined && v !== null && v !== "";
                  }) ? (
                    <div className="flex flex-col gap-1.5 text-sm leading-relaxed text-slate-200">
                      {SPEECH_FIELDS.map(([k, l]) => {
                        const v = m.speech?.[k];
                        if (v === undefined || v === null || v === "") return null;
                        return (
                          <div key={k}>
                            <span className="mr-1.5 text-xs text-[var(--accent-text)]">{l}：</span>
                            {Array.isArray(v) ? v.join("；") : typeof v === "object" ? JSON.stringify(v) : v}
                          </div>
                        );
                      })}
                    </div>
                  ) : m.speech?.raw ? (
                    <RawSpeech raw={m.speech.raw} />
                  ) : (
                    <div className="muted text-xs">（本次发言未能结构化，跳过）</div>
                  )}
                  {m.speech?.speech && SPEECH_FIELDS.some(([k]) => {
                    const v = m.speech?.[k];
                    return v !== undefined && v !== null && v !== "";
                  }) ? (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs text-sky-400">查看结构化记录</summary>
                      <div className="mt-1.5 flex flex-col gap-1">
                        {SPEECH_FIELDS.map(([k, l]) => {
                          const v = m.speech?.[k];
                          if (v === undefined || v === null || v === "") return null;
                          return (
                            <div key={k} className="text-xs leading-relaxed text-slate-400">
                              <span className="mr-1 text-[var(--accent-text)]">{l}：</span>
                              {Array.isArray(v) ? v.join("；") : typeof v === "object" ? JSON.stringify(v) : v}
                            </div>
                          );
                        })}
                      </div>
                    </details>
                  ) : null}
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
                  onKeyDown={(e) => e.key === "Enter" && (e.ctrlKey || e.metaKey ? finishMeeting() : nextRound())}
                />
                <button className="btn btn-primary" disabled={advancing} onClick={nextRound}>
                  {advancing ? "推进中…" : "继续下一轮"}
                </button>
                <button className="btn btn-ok" disabled={advancing} onClick={finishMeeting}>
                  {advancing ? "总结中…" : "✓ 结束讨论并总结"}
                </button>
              </div>
              <div className="muted mt-1.5 text-xs">会议不限轮数，您随时可以点「结束讨论并总结」收尾。</div>
            </div>
          ) : null}

          {session.status === "finished" && session.report ? (
            <div className="border-t border-[var(--line)] px-4 py-3">
              <div className="mb-1.5 text-xs font-semibold">会议结论</div>
              <div className="text-xs leading-relaxed text-slate-300">{session.report.discussion_summary || "（无摘要）"}</div>
              {session.report.cover_prompt ? (
                <div className="mt-2 rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-2.5">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="text-[11px] font-semibold text-[var(--accent-text)]">封面提示词（豆包出图用）</span>
                    <button
                      className="btn !px-2 !py-0.5 text-[11px]"
                      onClick={async (e) => {
                        try {
                          await navigator.clipboard.writeText(session.report.cover_prompt);
                          e.currentTarget.textContent = "已复制";
                          setTimeout(() => (e.currentTarget.textContent = "复制"), 2000);
                        } catch (err) {
                          alert("复制失败：" + err);
                        }
                      }}
                    >
                      复制
                    </button>
                  </div>
                  <div className="whitespace-pre-wrap text-xs leading-relaxed text-slate-300">
                    {session.report.cover_prompt}
                  </div>
                </div>
              ) : null}
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
      <ConfirmDialog
        open={confirmCancel}
        title="取消这次会议？"
        body="取消后本次讨论立即终止，已发言内容会保留在记录里。注意：直接关闭面板不会停止后台会议，请用这个按钮结束。"
        confirmText="取消会议"
        tone="danger"
        busy={advancing}
        onCancel={() => setConfirmCancel(false)}
        onConfirm={doCancel}
      />
      <div className="muted text-xs leading-relaxed">
        与周会共用引擎：主席点将、3 轮相互通气、主席总结；会议结论写入每位 Agent 的记忆。每轮结束后可插话指示。
        还没有作品时直接开会，就是新书选题会——先讨论写什么，结论存档后再建书。
      </div>
    </div>
  );
}
