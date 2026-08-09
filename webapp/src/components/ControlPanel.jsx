import { useEffect, useState } from "react";
import { getControl, postControl } from "../api.js";

function WorkflowCard({ label, wf, onAction }) {
  const state = !wf?.online
    ? { text: "n8n 离线", cls: "badge-bad" }
    : wf.active
      ? { text: "● 运行中", cls: "badge-ok" }
      : { text: "● 已暂停", cls: "badge-bad" };
  const last = wf?.last
    ? `${wf.last.status} · ${(wf.last.stopped_at || wf.last.started_at || "").replace("T", " ").slice(0, 19)}`
    : "暂无执行记录";
  return (
    <div className="card flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">{label}</span>
        <span className={`text-sm ${state.cls}`}>{state.text}</span>
      </div>
      <div className="muted text-xs">上次：{last}</div>
      <div className="mt-1 flex gap-2">
        {wf?.online && (
          <>
            {wf.active ? (
              <button
                className="rounded-md bg-red-500/15 px-3 py-1 text-xs text-red-400 hover:bg-red-500/25"
                onClick={() => onAction("pause")}
              >
                暂停
              </button>
            ) : (
              <button
                className="rounded-md bg-emerald-500/15 px-3 py-1 text-xs text-emerald-400 hover:bg-emerald-500/25"
                onClick={() => onAction("resume")}
              >
                恢复
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function ControlPanel({ onChanged }) {
  const [control, setControl] = useState(null);
  const [form, setForm] = useState(null);
  const [msg, setMsg] = useState("");

  const refresh = async () => {
    try {
      const c = await getControl();
      setControl(c);
      setForm((f) =>
        f || {
          daily_enabled: String(c.settings?.daily_enabled) === "true",
          monthly_budget: c.settings?.monthly_budget || 100,
          target_words: c.settings?.target_words || 2000,
          style_tweak: c.settings?.style_tweak || "",
        },
      );
    } catch {
      setControl(null);
    }
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 30000);
    return () => clearInterval(t);
  }, []);

  const action = async (payload) => {
    const r = await postControl(payload);
    setMsg(r.ok ? (r.note || "已执行") : "失败：" + (r.error || "未知"));
    refresh();
    onChanged?.();
    setTimeout(() => setMsg(""), 3000);
  };

  const save = () => {
    action({
      action: "save_settings",
      settings: {
        daily_enabled: form.daily_enabled ? "true" : "false",
        monthly_budget: String(form.monthly_budget),
        target_words: String(form.target_words),
        style_tweak: form.style_tweak,
      },
    });
  };

  const wfs = control?.workflows || {};
  const s = control?.settings || {};
  return (
    <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="panel p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-200">工作流控制</h2>
        <div className="flex flex-col gap-3">
          <WorkflowCard
            label="日更工作流"
            wf={wfs.daily}
            onAction={(a) => action({ action: a, workflow: "daily" })}
          />
          <WorkflowCard
            label="架构师周会"
            wf={wfs.weekly}
            onAction={(a) => action({ action: a, workflow: "weekly" })}
          />
          <button
            className="rounded-md bg-sky-500/15 px-3 py-1.5 text-xs text-sky-400 hover:bg-sky-500/25"
            onClick={() => action({ action: "request_run" })}
          >
            请求立即运行（下次定时触发时执行）
          </button>
          {msg && <div className="text-xs text-emerald-400">{msg}</div>}
        </div>
      </div>

      <div className="panel p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-200">运行设置</h2>
        {form ? (
          <div className="flex flex-col gap-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.daily_enabled}
                onChange={(e) => setForm({ ...form, daily_enabled: e.target.checked })}
                className="accent-emerald-500"
              />
              启用每日自动更新
            </label>
            <label className="text-sm">
              月度预算（元）
              <input
                type="number"
                value={form.monthly_budget}
                onChange={(e) => setForm({ ...form, monthly_budget: e.target.value })}
                className="mt-1 w-32 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-sm"
              />
            </label>
            <label className="text-sm">
              目标字数/章
              <input
                type="number"
                value={form.target_words}
                onChange={(e) => setForm({ ...form, target_words: e.target.value })}
                className="mt-1 w-32 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-sm"
              />
            </label>
            <label className="text-sm">
              风格微调
              <input
                type="text"
                value={form.style_tweak}
                placeholder="例：对话更简短，打脸更直接"
                onChange={(e) => setForm({ ...form, style_tweak: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-sm"
              />
            </label>
            <div className="flex items-center gap-3">
              <button
                className="rounded-md bg-emerald-500/15 px-4 py-1.5 text-sm text-emerald-400 hover:bg-emerald-500/25"
                onClick={save}
              >
                保存设置
              </button>
              <span className="muted text-xs">
                当前预算 {s.monthly_budget || 100} · 字数 {s.target_words || 2000}
              </span>
            </div>
          </div>
        ) : (
          <div className="muted text-sm">控制服务不可达</div>
        )}
      </div>
    </section>
  );
}
