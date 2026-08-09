import { useEffect, useState } from "react";
import { getMeetings } from "../api.js";
import { fmtTime } from "./ui.jsx";

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState([]);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    let alive = true;
    getMeetings()
      .then((r) => alive && setMeetings(r.meetings || []))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="flex flex-col gap-4">
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
