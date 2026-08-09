import { useEffect, useState } from "react";
import { getAgentStates, getDiaries } from "../api.js";
import { fmtTime } from "./ui.jsx";

const AGENTS = [
  ["", "全部 Agent"],
  ["planner", "文策"],
  ["guard", "守界"],
  ["writer", "墨白"],
  ["editor", "润物"],
  ["reviewer", "守正"],
  ["reader", "阿读"],
  ["memory", "录事"],
  ["work_meta", "书案"],
  ["eic", "掌印"],
  ["ending_judge", "终局"],
];

const AGENT_LABEL = Object.fromEntries(AGENTS);

function MoodBar({ label, value }) {
  const pct = Math.round((value ?? 0) * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="muted w-16 text-[11px]">{label}</span>
      <div className="progress h-1.5 flex-1">
        <div style={{ width: `${pct}%` }} />
      </div>
      <span className="muted w-8 text-right text-[11px]">{pct}%</span>
    </div>
  );
}

export default function DiariesPage() {
  const [agent, setAgent] = useState("");
  const [type, setType] = useState("");
  const [diaries, setDiaries] = useState([]);
  const [states, setStates] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    getAgentStates()
      .then((r) => setStates(r.states || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    let alive = true;
    getDiaries(agent, type)
      .then((r) => alive && setDiaries(r.diaries || []))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [agent, type]);

  const moodOf = (a) => states.find((s) => s.agent === a);

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm text-red-400">
          日记加载失败：{error}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <select className="input !w-40" value={agent} onChange={(e) => setAgent(e.target.value)}>
          {AGENTS.map(([v, l]) => (
            <option key={v || "all"} value={v}>{l}</option>
          ))}
        </select>
        <span className="chip cursor-pointer" onClick={() => setType(type === "" ? "daily" : "")}>
          {type === "daily" ? "每日日记 ✓" : "每日日记"}
        </span>
        <span className="chip cursor-pointer" onClick={() => setType(type === "" ? "weekly" : "")}>
          {type === "weekly" ? "每周周记 ✓" : "每周周记"}
        </span>
        <span className="muted ml-auto text-xs">共 {diaries.length} 条</span>
      </div>

      {states.length ? (
        <section className="panel p-4">
          <div className="section-title !mb-3">当前心情</div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
            {states.map((s) => (
              <div key={s.agent} className="rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-3">
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-xs font-semibold">{AGENT_LABEL[s.agent] || s.agent}</span>
                  <span className="muted text-[11px]">{fmtTime(s.updated_at, false)}</span>
                </div>
                <MoodBar label="满意" value={s.mood?.satisfaction} />
                <MoodBar label="担忧" value={s.mood?.concern} />
                <MoodBar label="兴奋" value={s.mood?.excitement} />
                <MoodBar label="疲惫" value={s.mood?.fatigue} />
                {s.mood?.note ? (
                  <div className="muted mt-1.5 text-[11px] leading-relaxed">“{s.mood.note}”</div>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {diaries.map((d) => (
        <section key={d.id} className="panel p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold">{AGENT_LABEL[d.agent] || d.agent}</span>
            <span className={`chip ${d.diary_type === "weekly" ? "chip-info" : "chip-warn"}`}>
              {d.diary_type === "weekly" ? "周记" : "日记"}
            </span>
            <span className="muted text-xs">{fmtTime(d.created_at)}</span>
            <span className="muted text-xs">书 #{d.novel_id}</span>
          </div>
          <div className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-2">
            {Object.entries(d.content || {}).filter(([k]) => k !== "mood").map(([k, v]) => (
              <div key={k} className="rounded-md bg-[var(--code-bg)] px-3 py-2">
                <div className="label !mb-1">{k}</div>
                <div className="text-xs leading-relaxed text-slate-300">
                  {Array.isArray(v) ? v.join("；") : typeof v === "object" ? JSON.stringify(v) : v}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
      {!diaries.length && !error ? (
        <div className="panel">
          <div className="empty">暂无日记。日更后每个 Agent 会自动写当日日记，周会前写本周周记。</div>
        </div>
      ) : null}
    </div>
  );
}
