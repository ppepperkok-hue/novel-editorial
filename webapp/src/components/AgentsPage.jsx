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
  getMemories,
  postAgents,
  postControl,
  readKnowledge,
  saveKnowledge,
  updateAgentAction,
  updateAgentState,
  updateDiary,
} from "../api.js";
import { ConfirmDialog } from "./ui.jsx";
import { ActionsPanel, ActivityPanel, KnowledgePanel, DraftsPanel } from "./agent-panels.jsx";

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

export default function AgentsPage({ pushToast }) {
  const [agents, setAgents] = useState(null);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState("");
  const [log, setLog] = useState([]);
  const [pendingPick, setPendingPick] = useState(null);
  const [diaries, setDiaries] = useState([]);
  const [memories, setMemories] = useState([]);
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
    getMemories(selected.file.replace(/\.md$/, ""))
      .then((r) => setMemories(r.items || []))
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
        addLog("工作流校验通过（JS/引用/连接全部有效）", "ok");
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
                <div className="mb-2 text-xs font-semibold">观点演化</div>
                {memories.filter((m) => m.category === "opinion").length ? (
                  <ul className="flex flex-col gap-1 text-xs text-slate-400">
                    {memories
                      .filter((m) => m.category === "opinion")
                      .map((m) => (
                        <li key={m.id}>
                          <span className="chip chip-info">{m.created_at || "—"}</span>{" "}
                          {m.content}
                        </li>
                      ))}
                  </ul>
                ) : (
                  <div className="text-xs text-slate-500">
                    还没有观点记录，周会之后会出现在这里
                  </div>
                )}
              </div>
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

      </div>
      <ActionsPanel pushToast={pushToast} />
      <ActivityPanel pushToast={pushToast} />
      <KnowledgePanel pushToast={pushToast} />
      <DraftsPanel pushToast={pushToast} />
    </div>
  );
}
