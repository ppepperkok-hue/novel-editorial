import { useEffect, useMemo, useRef, useState } from "react";
import {
  actOnDraft,
  createAgentAction,
  distillLessons,
  getActivity,
  getAgentActions,
  getAgentStates,
  getAgents,
  getDiaries,
  getKnowledge,
  getKnowledgeDrafts,
  postAgents,
  postControl,
  readKnowledge,
  saveKnowledge,
  updateAgentAction,
  updateAgentState,
  updateDiary,
} from "../api.js";
import { ConfirmDialog } from "./ui.jsx";

const AVATAR_COLORS = [
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

function agentTone(a) {
  return a.synced ? { text: "已同步", cls: "chip-ok" } : { text: "未同步", cls: "chip-warn" };
}

function KnowledgePanel({ pushToast }) {
  const [list, setList] = useState(null);
  const [editor, setEditor] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    getKnowledge()
      .then((r) => setList(r.knowledge || []))
      .catch(() => setList([]));
  };
  useEffect(() => {
    load();
  }, []);

  const open = async (item) => {
    const r = await readKnowledge(item.file);
    if (!r.ok || !r.item) {
      pushToast("读取知识包失败", "bad");
      return;
    }
    setEditor({
      file: r.item.file,
      title: r.item.meta.title || item.file,
      type: r.item.meta.type || "craft",
      agents: (r.item.meta.agents || []).join(","),
      body: r.item.body,
    });
  };

  const save = async () => {
    if (!editor) return;
    setBusy(true);
    try {
      const agents = editor.agents
        .split(/[,，\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      const r = await saveKnowledge(
        editor.file,
        { title: editor.title, type: editor.type, agents },
        editor.body,
      );
      pushToast(r.ok ? "知识包已保存" : "保存失败：" + (r.error || "未知"), r.ok ? "ok" : "bad");
      if (r.ok) {
        setEditor(null);
        load();
      }
    } finally {
      setBusy(false);
    }
  };

  const runKeeper = async () => {
    setBusy(true);
    try {
      const r = await postControl({ action: "run_knowledge_keeper" });
      pushToast(
        r.ok
          ? `维护完成：自动更新 ${(r.auto_updates || []).length}，草案 ${r.draft_suggestions || 0}，废弃 ${r.deprecations || 0}`
          : "维护失败：" + (r.error || "未知"),
        r.ok ? "ok" : "bad",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="section-title !mb-0">知识库（Agent Skills）</div>
        <button className="btn ml-auto !px-3 !py-1 text-xs" disabled={busy} onClick={runKeeper}>
          {busy ? "维护中…" : "▣ 运行知识维护"}
        </button>
      </div>

      {editor ? (
        <div className="rounded-lg border border-[var(--line)] p-3">
          <div className="mb-2 grid grid-cols-1 gap-2 md:grid-cols-3">
            <label className="text-xs muted">
              标题
              <input className="input mt-1" value={editor.title} onChange={(e) => setEditor({ ...editor, title: e.target.value })} />
            </label>
            <label className="text-xs muted">
              类型
              <select className="input mt-1" value={editor.type} onChange={(e) => setEditor({ ...editor, type: e.target.value })}>
                <option value="craft">craft（技巧）</option>
                <option value="market">market（市场）</option>
                <option value="generic">generic（通用常驻）</option>
              </select>
            </label>
            <label className="text-xs muted">
              适用角色（逗号分隔，all=全员）
              <input className="input mt-1" value={editor.agents} onChange={(e) => setEditor({ ...editor, agents: e.target.value })} />
            </label>
          </div>
          <textarea
            className="input mt-2 h-56 w-full font-mono text-xs"
            value={editor.body}
            onChange={(e) => setEditor({ ...editor, body: e.target.value })}
          />
          <div className="mt-2 flex justify-end gap-2">
            <button className="btn" onClick={() => setEditor(null)}>取消</button>
            <button className="btn btn-ok" disabled={busy} onClick={save}>保存知识包</button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {(list || []).map((item) => (
            <div key={item.file} className="card panel-hover p-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold">{item.title}</span>
                <span className={`chip ${item.type === "market" ? "chip-warn" : item.type === "generic" ? "chip-ok" : "chip-info"}`}>{item.type}</span>
                <span className="muted ml-auto text-xs">{item.updated_at}</span>
              </div>
              <div className="muted mt-1 text-xs leading-relaxed">{item.summary}</div>
              <div className="mt-1.5 flex items-center gap-1.5 text-xs">
                <span className="muted">适用：</span>
                {(item.agents || []).slice(0, 6).map((a) => (
                  <span key={a} className="chip !px-1.5 !py-0.5">{a}</span>
                ))}
                <button className="btn ml-auto !px-2.5 !py-0.5 text-xs" onClick={() => open(item)}>编辑</button>
              </div>
            </div>
          ))}
          {!list?.length ? <div className="empty">暂无知识包。</div> : null}
        </div>
      )}
    </section>
  );
}

function DraftsPanel({ pushToast }) {
  const [drafts, setDrafts] = useState([]);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    getKnowledgeDrafts()
      .then((r) => setDrafts(r.drafts || []))
      .catch(() => setDrafts([]));
  };
  useEffect(() => {
    load();
  }, []);

  const act = async (draft, action) => {
    setBusy(true);
    try {
      const r = await actOnDraft(draft.id, action);
      pushToast(
        r.ok
          ? action === "accept"
            ? "已采纳并写入知识库"
            : action === "reject"
              ? "已拒绝"
              : "已标记废弃"
          : "操作失败：" + (r.error || "未知"),
        r.ok ? "ok" : "bad",
      );
      setDetail(null);
      load();
    } finally {
      setBusy(false);
    }
  };

  const distill = async () => {
    setBusy(true);
    try {
      const r = await distillLessons();
      pushToast(
        r.ok ? `蒸馏完成：新增 ${r.drafted || 0} 条经验卡` : "蒸馏失败：" + (r.error || "未知"),
        r.ok ? "ok" : "bad",
      );
      load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="section-title !mb-0">经验卡（反思蒸馏）</div>
        <button className="btn ml-auto !px-3 !py-1 text-xs" disabled={busy} onClick={distill}>
          {busy ? "蒸馏中…" : "✦ 蒸馏最近一次会议"}
        </button>
      </div>
      <div className="flex flex-col gap-2">
        {drafts.map((d) => (
          <div key={d.id} className="card panel-hover p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`chip ${d.kind === "lesson" ? "chip-warn" : d.kind === "deprecation" ? "chip-bad" : "chip-info"}`}>
                {d.kind === "lesson" ? "经验" : d.kind === "deprecation" ? "废弃" : "知识"}
              </span>
              <span className="text-sm font-semibold">{d.title}</span>
              <span className="muted ml-auto text-xs">{d.created_at}</span>
              <span className="muted text-xs">{d.source}</span>
            </div>
            <div className="muted mt-1.5 text-xs leading-relaxed line-clamp-2">{d.content}</div>
            {detail === d.id ? (
              <div className="mt-2 rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-3">
                <div className="whitespace-pre-wrap text-xs leading-relaxed text-slate-300">{d.content}</div>
                {(d.agents || []).length ? (
                  <div className="mt-2 flex gap-1.5 text-xs">
                    <span className="muted">适用：</span>
                    {d.agents.map((a) => <span key={a} className="chip !px-1.5 !py-0.5">{a}</span>)}
                  </div>
                ) : null}
              </div>
            ) : null}
            {d.status === "draft" ? (
              <div className="mt-2 flex gap-2">
                <button className="btn !px-2.5 !py-0.5 text-xs" onClick={() => setDetail(detail === d.id ? null : d.id)}>
                  {detail === d.id ? "收起" : "查看"}
                </button>
                <button className="btn btn-ok !px-2.5 !py-0.5 text-xs" disabled={busy} onClick={() => act(d, "accept")}>
                  采纳
                </button>
                <button className="btn !px-2.5 !py-0.5 text-xs" disabled={busy} onClick={() => act(d, "reject")}>
                  拒绝
                </button>
                {d.kind !== "deprecation" ? (
                  <button className="btn btn-danger !px-2.5 !py-0.5 text-xs" disabled={busy} onClick={() => act(d, "deprecate")}>
                    废弃
                  </button>
                ) : null}
              </div>
            ) : (
              <div className="muted mt-2 text-xs">已{d.status === "accepted" ? "采纳" : d.status === "rejected" ? "拒绝" : "废弃"}</div>
            )}
          </div>
        ))}
        {!drafts.length ? <div className="empty">暂无经验卡。周会或专题会议后会自动蒸馏，也可手动点击上方按钮。</div> : null}
      </div>
    </section>
  );
}

const ACTION_LABELS = {
  pending: { text: "待办", cls: "chip-warn" },
  done: { text: "已完成", cls: "chip-ok" },
  skipped: { text: "已跳过", cls: "chip-info" },
};

const ACTIVITY_LABELS = {
  meeting_speech: { text: "会议发言", cls: "chip-info" },
  meeting_summary: { text: "主席总结", cls: "chip-primary" },
  diary: { text: "日记", cls: "chip-warn" },
  action_created: { text: "收到任务", cls: "chip" },
  action_done: { text: "完成任务", cls: "chip-ok" },
  action_status: { text: "任务状态", cls: "chip" },
  knowledge: { text: "知识维护", cls: "chip" },
  plan: { text: "规划大纲", cls: "chip-primary" },
  chapter: { text: "写作 / 润色", cls: "chip-info" },
  review: { text: "审稿 / 终审", cls: "chip-warn" },
  guard: { text: "设定守护", cls: "chip" },
  summary: { text: "提炼剧情", cls: "chip" },
  meta: { text: "作品资料", cls: "chip" },
  ending: { text: "完结评估", cls: "chip" },
  distill: { text: "经验蒸馏", cls: "chip-ok" },
  daily_summary: { text: "日更归档", cls: "chip-info" },
  agent: { text: "智能体任务", cls: "chip" },
  system: { text: "系统", cls: "chip" },
};

function ActionsPanel({ pushToast }) {
  const [actions, setActions] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null); // {id, task, result}
  const [creating, setCreating] = useState(null); // {agent, task}

  const load = () => {
    getAgentActions("", statusFilter)
      .then((r) => setActions(r.actions || []))
      .catch(() => setActions([]));
  };
  useEffect(() => {
    load();
  }, [statusFilter]);

  const saveStatus = async (id, status) => {
    setBusy(true);
    try {
      const r = await updateAgentAction(id, status, editing?.id === id ? editing.result : "");
      pushToast(r.ok ? "行动项已更新" : "更新失败：" + (r.error || "未知"), r.ok ? "ok" : "bad");
      setEditing(null);
      load();
    } finally {
      setBusy(false);
    }
  };

  const saveTask = async (id) => {
    if (!editing || !editing.task.trim()) return;
    setBusy(true);
    try {
      const r = await updateAgentAction(id, "", editing.result, editing.task);
      pushToast(r.ok ? "任务内容已更新" : "更新失败：" + (r.error || "未知"), r.ok ? "ok" : "bad");
      setEditing(null);
      load();
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    if (!creating || !creating.agent || !creating.task.trim()) return;
    setBusy(true);
    try {
      const r = await createAgentAction({
        agent: creating.agent,
        task: creating.task,
        novel_id: 0,
      });
      pushToast(r.ok ? "已创建行动项" : "创建失败：" + (r.error || "未知"), r.ok ? "ok" : "bad");
      setCreating(null);
      load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="section-title !mb-0">会后任务（Agent 行动项）</div>
        <select
          className="input ml-auto !w-auto !px-2 !py-1 text-xs"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">全部状态</option>
          <option value="pending">待办</option>
          <option value="done">已完成</option>
          <option value="skipped">已跳过</option>
        </select>
        <button
          className="btn !px-3 !py-1 text-xs"
          onClick={() => setCreating({ agent: "planner", task: "" })}
        >
         ＋ 手动添加
        </button>
        <button className="btn !px-3 !py-1 text-xs" onClick={load}>刷新</button>
      </div>

      {creating ? (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-[var(--line)] p-3">
          <select
            className="input !w-auto !px-2 !py-1 text-xs"
            value={creating.agent}
            onChange={(e) => setCreating({ ...creating, agent: e.target.value })}
          >
            {["planner", "guard", "writer", "editor", "reviewer", "reader", "memory", "work_meta", "eic", "ending_judge", "knowledge_keeper"].map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
          <input
            className="input min-w-[240px] flex-1 !px-2 !py-1 text-xs"
            placeholder="要交给这个 agent 的任务"
            value={creating.task}
            onChange={(e) => setCreating({ ...creating, task: e.target.value })}
            onKeyDown={(e) => e.key === "Enter" && create()}
          />
          <button className="btn btn-ok !px-3 !py-1 text-xs" disabled={busy} onClick={create}>创建</button>
          <button className="btn !px-3 !py-1 text-xs" onClick={() => setCreating(null)}>取消</button>
        </div>
      ) : null}

      <div className="flex flex-col gap-2">
        {actions.map((a) => {
          const st = ACTION_LABELS[a.status] || ACTION_LABELS.pending;
          const editingThis = editing?.id === a.id;
          return (
            <div key={a.id} className="card panel-hover p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="chip chip-info">{a.agent}</span>
                <span className={`chip ${st.cls}`}>{st.text}</span>
                <span className="muted ml-auto text-xs">{a.created_at}</span>
                {(a.detail?.due || "") ? <span className="chip">期限：{a.detail.due}</span> : null}
              </div>
              {editingThis ? (
                <div className="mt-2 flex flex-col gap-2">
                  <input
                    className="input !px-2 !py-1 text-xs"
                    value={editing.task}
                    onChange={(e) => setEditing({ ...editing, task: e.target.value })}
                  />
                  <textarea
                    className="input min-h-[60px] !px-2 !py-1 text-xs"
                    placeholder="完成结果（可选）"
                    value={editing.result}
                    onChange={(e) => setEditing({ ...editing, result: e.target.value })}
                  />
                  <div className="flex gap-2">
                    <button className="btn btn-ok !px-2.5 !py-0.5 text-xs" disabled={busy} onClick={() => saveTask(a.id)}>
                      保存内容
                    </button>
                    <button className="btn !px-2.5 !py-0.5 text-xs" onClick={() => setEditing(null)}>取消</button>
                  </div>
                </div>
              ) : (
                <div className="mt-1.5 text-sm leading-relaxed text-slate-300">{a.task}</div>
              )}
              {!editingThis && (a.detail?.reason || a.detail?.expected_output) ? (
                <div className="muted mt-1 text-xs">
                  {a.detail.reason ? `原因：${a.detail.reason}；` : ""}
                  {a.detail.expected_output ? `预期产出：${a.detail.expected_output}` : ""}
                </div>
              ) : null}
              {!editingThis && a.result ? (
                <div className="mt-1 text-xs text-emerald-400">结果：{a.result}</div>
              ) : null}
              {a.status === "pending" ? (
                <div className="mt-2 flex gap-2">
                  <button className="btn !px-2.5 !py-0.5 text-xs" disabled={busy} onClick={() => setEditing({ id: a.id, task: a.task, result: "" })}>
                    编辑 / 完成
                  </button>
                  <button className="btn btn-ok !px-2.5 !py-0.5 text-xs" disabled={busy} onClick={() => saveStatus(a.id, "done", "")}>
                    直接完成
                  </button>
                  <button className="btn !px-2.5 !py-0.5 text-xs" disabled={busy} onClick={() => saveStatus(a.id, "skipped")}>
                    跳过
                  </button>
                </div>
              ) : null}
            </div>
          );
        })}
        {!actions.length ? (
          <div className="empty">暂无行动项。会议结束后每位参会 agent 会自动生成会后任务。</div>
        ) : null}
      </div>
    </section>
  );
}

function ActivityPanel({ pushToast }) {
  const [days, setDays] = useState([]);
  const [agentFilter, setAgentFilter] = useState("");
  const [limit, setLimit] = useState(7);

  const load = () => {
    getActivity(agentFilter || "", "", 600)
      .then((r) => setDays((r.days || []).slice(0, limit)))
      .catch(() => setDays([]));
  };
  useEffect(() => {
    load();
  }, [agentFilter, limit]);

  return (
    <section className="panel p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="section-title !mb-0">Agent 活动日志（谁、何时、干了什么）</div>
        <select
          className="input ml-auto !w-auto !px-2 !py-1 text-xs"
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
        >
          <option value="">全部 Agent</option>
          {["planner", "guard", "writer", "editor", "reviewer", "reader", "memory", "work_meta", "eic", "ending_judge", "knowledge_keeper", "system"].map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select
          className="input !w-auto !px-2 !py-1 text-xs"
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
        >
          <option value={3}>近 3 天</option>
          <option value={7}>近 7 天</option>
          <option value={30}>近 30 天</option>
        </select>
        <button className="btn !px-3 !py-1 text-xs" onClick={load}>刷新</button>
      </div>

      <div className="flex flex-col gap-4">
        {days.map((d) => (
          <div key={d.date}>
            <div className="mb-2 flex items-center gap-2">
              <span className="text-xs font-bold text-[var(--accent-text)]">{d.date}</span>
              <span className="muted text-xs">{d.items.length} 条记录</span>
              <div className="h-px flex-1 bg-[var(--line)]" />
            </div>
            <div className="flex flex-col gap-1.5">
              {d.items.map((it) => {
                const lb = ACTIVITY_LABELS[it.activity_type] || { text: it.activity_type, cls: "chip" };
                return (
                  <div key={it.id} className="flex items-start gap-2 rounded-lg border border-[var(--line)] bg-[var(--code-bg)] px-3 py-2 text-xs">
                    <span className={`chip shrink-0 !px-1.5 !py-0.5 ${lb.cls}`}>{lb.text}</span>
                    <span className="chip shrink-0 chip-info">{it.agent}</span>
                    <span className="min-w-0 flex-1 leading-relaxed text-slate-300">
                      <span className="font-semibold">{it.title}</span>
                      {it.detail?.speech ? (
                        <span className="muted ml-1">：{String(it.detail.speech).slice(0, 80)}</span>
                      ) : null}
                      {it.detail?.what_done ? (
                        <span className="muted ml-1">：{String(it.detail.what_done).slice(0, 80)}</span>
                      ) : null}
                      {it.detail?.task ? (
                        <span className="muted ml-1">：{String(it.detail.task).slice(0, 80)}</span>
                      ) : null}
                      {it.detail?.output ? (
                        <span className="muted ml-1">：{String(it.detail.output).slice(0, 80)}</span>
                      ) : null}
                      {it.detail?.error ? (
                        <span className="ml-1 text-red-400">：失败 {String(it.detail.error).slice(0, 80)}</span>
                      ) : null}
                      {it.detail?.published != null ? (
                        <span className="muted ml-1">：发布 {it.detail.published} 章</span>
                      ) : null}
                    </span>
                    <span className="muted shrink-0">{(it.created_at || "").slice(11, 19)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
        {!days.length ? (
          <div className="empty">暂无活动记录。会议、日更、日记、知识维护都会自动留痕。</div>
        ) : null}
      </div>
    </section>
  );
}

export default function AgentsPage({ pushToast }) {
  const [agents, setAgents] = useState(null);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState("");
  const [log, setLog] = useState([]);
  const [pendingPick, setPendingPick] = useState(null);
  const [confirmDeploy, setConfirmDeploy] = useState(false);
  const [diaries, setDiaries] = useState([]);
  const [states, setStates] = useState([]);
  const [editDiary, setEditDiary] = useState(null);
  const [moodDraft, setMoodDraft] = useState(null);
  const logRef = useRef(null);

  const load = async () => {
    try {
      const r = await getAgents();
      setAgents(r.agents);
      setSelected((s) => {
        if (!s) return r.agents[0] || null;
        const updated = r.agents.find((a) => a.file === s.file);
        return updated || s;
      });
    } catch (e) {
      setAgents(null);
      pushToast("Agent 数据加载失败：" + e, "bad");
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!selected) return;
    getDiaries(selected.file)
      .then((r) => setDiaries(r.diaries || []))
      .catch(() => {});
    getAgentStates()
      .then((r) => setStates(r.states || []))
      .catch(() => {});
  }, [selected]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [log]);

  const addLog = (line, kind = "info") => {
    const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    setLog((l) => [...l.slice(-60), { time, kind, line }]);
  };

  const dirty = useMemo(() => {
    if (!selected || !agents) return false;
    const base = agents.find((a) => a.file === selected.file);
    if (!base) return false;
    return (
      base.model !== selected.model ||
      String(base.temperature) !== String(selected.temperature) ||
      base.prompt !== selected.prompt
    );
  }, [selected, agents]);

  const applyPick = (a) => {
    setSelected({ ...a });
    setLog([]);
  };

  const pick = (a) => {
    if (dirty && selected && a.file !== selected.file) {
      setPendingPick(a);
      return;
    }
    applyPick(a);
  };

  const tempValue = Number(selected?.temperature);
  const tempValid =
    selected != null &&
    selected.temperature !== "" &&
    !Number.isNaN(tempValue) &&
    tempValue >= 0 &&
    tempValue <= 2;

  const moodOf = states.find((s) => s.agent === selected?.file);
  const currentMood = moodDraft || moodOf?.mood || {
    satisfaction: 0.5,
    concern: 0.5,
    excitement: 0.5,
    fatigue: 0.3,
    note: "",
  };

  const saveMood = async () => {
    const r = await updateAgentState(selected.file, 0, currentMood);
    pushToast(r.ok ? "心情已更新" : "更新失败：" + (r.error || "未知"), r.ok ? "ok" : "bad");
    setMoodDraft(null);
    getAgentStates().then((x) => setStates(x.states || []));
  };

  const saveDiary = async () => {
    if (!editDiary) return;
    let content;
    try {
      content = JSON.parse(editDiary.text);
    } catch {
      pushToast("日记内容必须是合法 JSON", "bad");
      return;
    }
    const r = await updateDiary(editDiary.id, content);
    pushToast(r.ok ? "日记已更新" : "更新失败：" + (r.error || "未知"), r.ok ? "ok" : "bad");
    setEditDiary(null);
    getDiaries(selected.file).then((x) => setDiaries(x.diaries || []));
  };

  const save = async () => {
    if (!selected) return;
    setBusy("save");
    addLog(`保存 ${selected.file} → 写回 agent 资产并渲染工作流...`);
    try {
      const r = await postAgents({
        action: "save",
        file: selected.file,
        model: selected.model,
        temperature: Number(selected.temperature),
        prompt: selected.prompt,
      });
      if (!r.ok) {
        addLog(`保存失败：${r.error}`, "bad");
        pushToast("保存失败：" + r.error, "bad");
        return;
      }
      addLog(`渲染完成：${r.render || "（无输出）"}`);
      if (r.validation) {
        addLog("工作流校验通过（56 节点 JS/引用/连接全部有效）", "ok");
        pushToast(`${selected.name} 已保存并通过校验`, "ok");
      } else {
        addLog(`校验未通过：${r.validation_output}`, "bad");
        pushToast("已保存，但工作流校验未通过，请检查提示词", "warn");
      }
      await load();
    } catch (e) {
      addLog(`请求失败：${e}`, "bad");
      pushToast("保存请求失败：" + e, "bad");
    } finally {
      setBusy("");
    }
  };

  const deploy = async () => {
    if (!selected) return;
    setBusy("deploy");
    addLog("部署到 n8n（PUT 日更工作流，会覆盖线上节点配置）...");
    try {
      const r = await postAgents({ action: "deploy" });
      if (!r.ok) {
        addLog(`部署失败：${r.error}`, "bad");
        pushToast("部署失败：" + r.error, "bad");
      } else {
        addLog(`部署成功：${r.nodes} 个节点，active=${r.active}`, "ok");
        pushToast(`已部署到 n8n（${r.nodes} 节点，${r.active ? "运行中" : "未激活"}）`, "ok");
      }
    } catch (e) {
      addLog(`部署请求失败：${e}`, "bad");
      pushToast("部署请求失败：" + e, "bad");
    } finally {
      setBusy("");
    }
  };

  const modelOptions = ["deepseek-v4-pro", "deepseek-v4-flash"];

  return (
    <div className="flex flex-col gap-4">
      <div className="grid h-[calc(100vh-150px)] grid-cols-1 gap-4 xl:grid-cols-[330px_1fr]">
      <div className="panel overflow-hidden flex flex-col">
        <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-3">
          <div className="text-sm font-semibold">写作智能体</div>
          <button className="btn !px-2.5 !py-1 text-xs" onClick={load}>⟳</button>
        </div>
        <div className="agent-grid flex-1 overflow-y-auto !grid-cols-1 p-3">
          {(agents || []).map((a, i) => {
            const tone = agentTone(a);
            const active = selected?.file === a.file;
            return (
              <div
                key={a.file}
                className={`agent-card card panel-hover ${active ? "selected" : ""}`}
                onClick={() => pick(a)}
              >
                <div className="flex items-center gap-2.5">
                  <div className="agent-avatar" style={{ background: AVATAR_COLORS[i % AVATAR_COLORS.length] }}>
                    {a.name.slice(0, 1)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-semibold">{a.name}</span>
                      <span className={`chip ${tone.cls}`}>{tone.text}</span>
                    </div>
                    <div className="muted mt-0.5 truncate text-xs">{a.file}</div>
                  </div>
                </div>
                <div className="muted line-clamp-2 text-xs leading-relaxed">{a.description}</div>
                <div className="flex flex-wrap gap-1">
                  <span className="chip chip-info">{a.model}</span>
                  <span className="chip">temp {a.temperature}</span>
                </div>
                <div className="text-xs text-slate-500">
                  节点：{a.nodes.length ? a.nodes.join("、") : "未映射"}
                </div>
              </div>
            );
          })}
          {!agents && <div className="empty">Agent 数据不可达</div>}
        </div>
      </div>

      <div className="panel overflow-hidden flex flex-col">
        {selected ? (
          <>
            <div className="flex flex-wrap items-center gap-3 border-b border-[var(--line)] px-5 py-3.5">
              <div>
                <div className="text-sm font-bold">{selected.name}</div>
                <div className="muted text-xs">{selected.file} · 用于节点：{selected.nodes.join("、") || "未映射"}</div>
              </div>
              <div className="ml-auto flex items-center gap-2">
                {dirty ? <span className="chip chip-warn">有未保存修改</span> : null}
                <button className="btn btn-ok" disabled={busy !== "" || !tempValid} onClick={save}>
                  {busy === "save" ? "渲染校验中…" : "💾 保存并校验"}
                </button>
                <button className="btn btn-primary" disabled={busy !== "" || dirty} onClick={() => setConfirmDeploy(true)}>
                  {busy === "deploy" ? "部署中…" : "▲ 部署到 n8n"}
                </button>
              </div>
            </div>

            <div className="grid flex-1 grid-cols-1 gap-4 overflow-y-auto p-5 lg:grid-cols-[280px_1fr]">
              <div className="flex flex-col gap-4">
                <div>
                  <label className="label">模型</label>
                  <select className="input" value={selected.model} onChange={(e) => setSelected({ ...selected, model: e.target.value })}>
                    {modelOptions.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <div className="muted mt-1 text-xs">pro 更强推理 · flash 更省成本</div>
                </div>
                <div>
                  <label className="label">温度（0–2）</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    className="input"
                    value={selected.temperature}
                    onChange={(e) => setSelected({ ...selected, temperature: e.target.value })}
                  />
                  <div className={`mt-1 text-xs ${tempValid ? "muted" : "text-red-400"}`}>
                    {tempValid ? "越低越稳定，越高越有发散性" : "温度必须是 0–2 之间的数字"}
                  </div>
                </div>
                <div className="rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-3">
                  <div className="label !mb-2">Agent 说明</div>
                  <div className="text-xs leading-relaxed text-slate-400">{selected.description}</div>
                </div>
                <div className="rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-3">
                  <div className="label !mb-2">提示词占位符</div>
                  <div className="code w-fit rounded-md border border-[var(--accent)]/40 bg-[var(--placeholder-highlight-bg)]/40 px-2 py-1 text-xs text-[var(--accent-text)]">{"{TARGET_WORDS}"}</div>
                  <div className="muted mt-1 text-xs">渲染时会替换为工作流里的目标字数表达式，请保留在提示词中。</div>
                </div>
              </div>

              <div className="flex min-h-0 flex-col">
                <label className="label">系统提示词（System Prompt）</label>
                <textarea
                  className="input code min-h-[300px] flex-1 !text-[12.5px]"
                  value={selected.prompt}
                  spellCheck={false}
                  onChange={(e) => setSelected({ ...selected, prompt: e.target.value })}
                />
                <div className="muted mt-1.5 text-right text-xs">{selected.prompt.length} 字符</div>
              </div>
            </div>

            <div className="border-t border-[var(--line)] px-5 py-4">
              <div className="label !mb-3">记忆与日记（可修改）</div>
              <div className="mb-4 rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-semibold">当前心情</span>
                  <button className="btn btn-ok !px-3 !py-1 text-xs" onClick={saveMood}>保存心情</button>
                </div>
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                  {[
                    ["satisfaction", "满意"],
                    ["concern", "担忧"],
                    ["excitement", "兴奋"],
                    ["fatigue", "疲惫"],
                  ].map(([k, l]) => (
                    <label key={k} className="muted text-xs">
                      {l}
                      <input
                        type="number"
                        min="0"
                        max="1"
                        step="0.1"
                        className="input mt-1"
                        value={currentMood[k] ?? 0.5}
                        onChange={(e) => setMoodDraft({ ...currentMood, [k]: Number(e.target.value) })}
                      />
                    </label>
                  ))}
                </div>
                <input
                  className="input mt-2"
                  placeholder="心情备注（可选）"
                  value={currentMood.note || ""}
                  onChange={(e) => setMoodDraft({ ...currentMood, note: e.target.value })}
                />
              </div>

              <div className="flex flex-col gap-2">
                {diaries.slice(0, 6).map((d) => (
                  <div key={d.id} className="rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-3">
                    <div className="flex items-center gap-2">
                      <span className={`chip ${d.diary_type === "weekly" ? "chip-info" : "chip-warn"}`}>
                        {d.diary_type === "weekly" ? "周记" : "日记"}
                      </span>
                      <span className="muted text-xs">{d.created_at}</span>
                      <button
                        className="btn ml-auto !px-2.5 !py-0.5 text-xs"
                        onClick={() =>
                          setEditDiary(
                            editDiary?.id === d.id
                              ? null
                              : { id: d.id, text: JSON.stringify(d.content, null, 2) },
                          )
                        }
                      >
                        {editDiary?.id === d.id ? "取消" : "编辑"}
                      </button>
                    </div>
                    {editDiary?.id === d.id ? (
                      <div className="mt-2">
                        <textarea
                          className="input code min-h-[140px] !text-xs"
                          value={editDiary.text}
                          spellCheck={false}
                          onChange={(e) => setEditDiary({ ...editDiary, text: e.target.value })}
                        />
                        <div className="mt-2 flex justify-end">
                          <button className="btn btn-ok !px-3 !py-1 text-xs" onClick={saveDiary}>保存日记</button>
                        </div>
                      </div>
                    ) : (
                      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1">
                        {Object.entries(d.content || {})
                          .filter(([k]) => k !== "mood")
                          .slice(0, 4)
                          .map(([k, v]) => (
                            <span key={k} className="text-[11px] text-slate-400">
                              {k}：{Array.isArray(v) ? v.join("；") : typeof v === "object" ? JSON.stringify(v) : v}
                            </span>
                          ))}
                      </div>
                    )}
                  </div>
                ))}
                {!diaries.length ? (
                  <div className="muted text-xs">暂无日记。日更后自动生成，周会前写周记。</div>
                ) : null}
              </div>
            </div>

            <div className="border-t border-[var(--line)] px-5 py-3">
              <div className="label !mb-1.5">操作日志</div>
              <div ref={logRef} className="code max-h-28 overflow-y-auto rounded-lg bg-[var(--code-bg)] px-3 py-2 text-xs leading-relaxed">
                {log.length ? (
                  log.map((l, i) => (
                    <div key={i} className={l.kind === "bad" ? "text-red-400" : l.kind === "ok" ? "text-emerald-400" : "text-slate-400"}>
                      <span className="text-slate-600">[{l.time}]</span> {l.line}
                    </div>
                  ))
                ) : (
                  <div className="text-slate-600">尚未执行操作。修改提示词后点击「保存并校验」，通过后可部署。</div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="empty flex-1">从左侧选择一个 Agent</div>
        )}
      </div>

      <ConfirmDialog
        open={pendingPick !== null}
        title="放弃未保存的修改？"
        body={`当前「${selected?.name}」的修改尚未保存，切换后会丢失。`}
        confirmText="放弃并切换"
        onCancel={() => setPendingPick(null)}
        onConfirm={() => {
          applyPick(pendingPick);
          setPendingPick(null);
        }}
      />

      <ConfirmDialog
        open={confirmDeploy}
        title="部署到 n8n？"
        body="会用当前工作流 JSON 覆盖 n8n 线上的日更工作流节点配置。提示词资产与线上将保持一致。"
        confirmText="部署"
        tone="primary"
        busy={busy === "deploy"}
        onCancel={() => setConfirmDeploy(false)}
        onConfirm={() => {
          setConfirmDeploy(false);
          deploy();
        }}
      />
      </div>
      <ActionsPanel pushToast={pushToast} />
      <ActivityPanel pushToast={pushToast} />
      <KnowledgePanel pushToast={pushToast} />
      <DraftsPanel pushToast={pushToast} />
    </div>
  );
}
