import { useEffect, useState } from "react";
import { getMeetings, getSession } from "../api.js";
import { fmtTime } from "./ui.jsx";
import MeetingLive from "./MeetingLive.jsx";

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState([]);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);
  const [log, setLog] = useState(null); // {meeting, transcript, loading}
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

  const loadLog = async (m) => {
    if (!m.session_id) {
      setLog({ meeting: m, transcript: null, loading: false });
      return;
    }
    setLog({ meeting: m, transcript: null, loading: true });
    try {
      const s = await getSession(m.session_id);
      setLog({ meeting: m, transcript: s?.transcript || [], loading: false });
    } catch {
      setLog({ meeting: m, transcript: [], loading: false });
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm text-red-400">
          周会档案加载失败：{error}
        </div>
      ) : null}

      <section className="panel p-4">
        <div className="section-title !mb-3">会议中心</div>
        <MeetingLive onArchived={() => setRefreshTick((t) => t + 1)} />
      </section>

      {!meetings.length && !error ? (
        <div className="panel">
          <div className="empty">还没有会议记录。专题会议或每周周会完成后会存档在这里。</div>
        </div>
      ) : null}

      {meetings.map((m) => (
        <section key={m.id} className="panel p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold">会议 #{m.id}</span>
            <span className="chip">{fmtTime(m.held_at)}</span>
            <span className={`chip ${m.kind === "topic" ? "chip-warn" : "chip-info"}`}>
              {m.kind === "topic" ? "专题会议" : "周会"}
            </span>
            <span className={`chip ${m.status === "completed" ? "chip-ok" : "chip-warn"}`}>{m.status}</span>
            <button className="btn ml-auto !px-3 !py-1 text-xs" onClick={() => setDetail(detail === m.id ? null : m.id)}>
              {detail === m.id ? "收起" : "查看报告"}
            </button>
            <button className="btn !px-3 !py-1 text-xs" onClick={() => loadLog(m)}>
              查看完整对话
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

          {log?.meeting?.id === m.id ? (
            <div className="mt-3 rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-3">
              <div className="label !mb-2">完整对话记录{log.loading ? "（加载中…）" : ""}</div>
              {!log.loading && !log.transcript?.length ? (
                <div className="muted text-xs">
                  {m.session_id ? "本次会议没有可回放的对话（可能已清理）" : "这条记录没有关联的交互式会议会话，无法回放逐轮对话"}
                </div>
              ) : null}
              {!log.loading
                ? (log.transcript || []).map((t, i) => (
                    <div key={i} className="mb-3 border-b border-[var(--line)] pb-3 last:border-b-0 last:pb-0">
                      <div className="mb-1 flex items-center gap-2 text-xs">
                        <span className="chip chip-info">{t.agent}</span>
                        <span className="chip">第 {t.round} 轮</span>
                        <span className="muted">发言</span>
                      </div>
                      <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
                        {typeof t.speech === "string" ? t.speech : t.speech?.speech || JSON.stringify(t.speech, null, 2)}
                      </div>
                      {t.speech && typeof t.speech === "object" ? (
                        <div className="mt-1.5 flex flex-wrap gap-1.5 text-xs">
                          {t.speech.weekly_summary ? <span className="chip chip-warn">本周：{t.speech.weekly_summary}</span> : null}
                          {t.speech.feelings ? <span className="chip">感受：{t.speech.feelings}</span> : null}
                          {(t.speech.proposals || []).length ? (
                            <span className="chip chip-info">提案：{t.speech.proposals.join("；")}</span>
                          ) : null}
                          {(t.speech.concerns || []).length ? (
                            <span className="chip chip-bad">顾虑：{t.speech.concerns.join("；")}</span>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ))
                : null}
            </div>
          ) : null}
        </section>
      ))}
    </div>
  );
}
