import { useEffect, useState } from "react";
import {
  actOnDraft,
  createAgentAction,
  distillLessons,
  getActivity,
  getAgentActions,
  getKnowledge,
  getKnowledgeDrafts,
  postControl,
  readKnowledge,
  saveKnowledge,
  updateAgentAction,
} from "../api.js";

export function KnowledgePanel({ pushToast }) {
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

export function DraftsPanel({ pushToast }) {
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
  knowledge_lookup: { text: "知识检索", cls: "chip-info" },
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

export function ActionsPanel({ pushToast }) {
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

export function ActivityPanel({ pushToast }) {
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

