import { useEffect, useMemo, useRef, useState } from "react";
import { getAgents, postAgents } from "../api.js";

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

  const pick = (a) => {
    setSelected({ ...a });
    setLog([]);
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
        addLog("工作流校验通过（55 节点 JS/引用/连接全部有效）", "ok");
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
    <div className="grid h-[calc(100vh-150px)] grid-cols-1 gap-4 xl:grid-cols-[330px_1fr]">
      <div className="panel overflow-hidden flex flex-col">
        <div className="flex items-center justify-between border-b border-[#1a2332] px-4 py-3">
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
            <div className="flex flex-wrap items-center gap-3 border-b border-[#1a2332] px-5 py-3.5">
              <div>
                <div className="text-sm font-bold">{selected.name}</div>
                <div className="muted text-xs">{selected.file} · 用于节点：{selected.nodes.join("、") || "未映射"}</div>
              </div>
              <div className="ml-auto flex items-center gap-2">
                {dirty ? <span className="chip chip-warn">有未保存修改</span> : null}
                <button className="btn btn-ok" disabled={busy !== ""} onClick={save}>
                  {busy === "save" ? "渲染校验中…" : "💾 保存并校验"}
                </button>
                <button className="btn btn-primary" disabled={busy !== "" || dirty} onClick={deploy}>
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
                  <div className="muted mt-1 text-xs">越低越稳定，越高越有发散性</div>
                </div>
                <div className="rounded-lg border border-[#1a2332] bg-[#0a0f18] p-3">
                  <div className="label !mb-2">Agent 说明</div>
                  <div className="text-xs leading-relaxed text-slate-400">{selected.description}</div>
                </div>
                <div className="rounded-lg border border-[#1a2332] bg-[#0a0f18] p-3">
                  <div className="label !mb-2">提示词占位符</div>
                  <div className="code text-xs text-sky-400">{"{TARGET_WORDS}"}</div>
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

            <div className="border-t border-[#1a2332] px-5 py-3">
              <div className="label !mb-1.5">操作日志</div>
              <div ref={logRef} className="code max-h-28 overflow-y-auto rounded-lg bg-[#0a0f18] px-3 py-2 text-[11.5px] leading-relaxed">
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
    </div>
  );
}
