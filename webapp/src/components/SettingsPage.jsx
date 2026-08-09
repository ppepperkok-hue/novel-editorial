import { useEffect, useState } from "react";
import { getControl, postControl } from "../api.js";

function WorkflowCard({ label, wf, onAction }) {
  const state = !wf?.online
    ? { text: "n8n 离线", cls: "chip-bad" }
    : wf.active
      ? { text: "运行中", cls: "chip-ok" }
      : { text: "已暂停", cls: "chip-bad" };
  const last = wf?.last
    ? `${wf.last.status} · ${(wf.last.stopped_at || wf.last.started_at || "").replace("T", " ").slice(5, 19)}`
    : "暂无";
  return (
    <div className="card flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">{label}</span>
        <span className={`chip ${state.cls}`}>{state.text}</span>
      </div>
      <div className="muted text-xs">上次执行：{last}</div>
      <div className="mt-1 flex gap-2">
        {wf?.online &&
          (wf.active ? (
            <button className="btn btn-danger !px-3 !py-1 text-xs" onClick={() => onAction("pause")}>暂停</button>
          ) : (
            <button className="btn btn-ok !px-3 !py-1 text-xs" onClick={() => onAction("resume")}>恢复</button>
          ))}
      </div>
    </div>
  );
}

export default function SettingsPage({ data, onRefresh, pushToast }) {
  const [control, setControl] = useState(null);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState("");

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
          daily_run_time: c.settings?.daily_run_time || "08:00",
        },
      );
    } catch {
      setControl(null);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const action = async (payload, okMsg) => {
    const r = await postControl(payload);
    pushToast(r.ok ? okMsg : `失败：${r.error || "未知"}`, r.ok ? "ok" : "bad");
    refresh();
    onRefresh();
  };

  const save = async () => {
    setSaving(true);
    try {
      const r = await postControl({
        action: "save_settings",
        settings: {
          daily_enabled: form.daily_enabled ? "true" : "false",
          monthly_budget: String(form.monthly_budget),
          target_words: String(form.target_words),
          style_tweak: form.style_tweak,
          daily_run_time: form.daily_run_time,
        },
      });
      if (!r.ok) {
        pushToast("保存失败：" + (r.error || "未知"), "bad");
        return;
      }
      const sched = await postControl({
        action: "apply_schedule",
        time: form.daily_run_time,
      });
      if (sched.ok) {
        pushToast(`设置已保存，日更时间已改为每天 ${sched.time}`, "ok");
      } else {
        pushToast("设置已保存，但更新时间应用失败：" + (sched.error || "未知"), "warn");
      }
      refresh();
      onRefresh();
    } finally {
      setSaving(false);
    }
  };

  const runNow = async (workflow, label) => {
    setRunning(workflow);
    try {
      const r = await postControl({ action: "run_now", workflow });
      if (r.ok) {
        pushToast(`${label}已启动，正在后台执行，可到「执行记录」查看进度`, "ok");
      } else {
        pushToast(`${label}启动失败：${r.error || "未知"}`, "bad");
      }
      refresh();
      onRefresh();
    } finally {
      setRunning("");
    }
  };

  const wfs = control?.workflows || {};
  const s = control?.settings || {};

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <section className="panel p-4">
        <div className="section-title !mb-3">工作流控制</div>
        <div className="flex flex-col gap-3">
          <WorkflowCard label="日更工作流（55 节点）" wf={wfs.daily} onAction={(a) => action({ action: a, workflow: "daily" }, a === "pause" ? "日更已暂停" : "日更已恢复")} />
          <WorkflowCard label="架构师周会（5 节点）" wf={wfs.weekly} onAction={(a) => action({ action: a, workflow: "weekly" }, a === "pause" ? "周会已暂停" : "周会已恢复")} />
          <button className="btn btn-primary" onClick={() => action({ action: "request_run" }, "已请求运行，将在下个定时触发点执行")}>
            ⟶ 请求立即运行
          </button>
          <div className="grid grid-cols-2 gap-2">
            <button
              className="btn btn-ok"
              disabled={running !== ""}
              onClick={() => runNow("daily", "日更流水线")}
            >
              {running === "daily" ? "启动中…" : "▶ 立即更新一章"}
            </button>
            <button
              className="btn"
              disabled={running !== ""}
              onClick={() => runNow("weekly", "架构师周会")}
            >
              {running === "weekly" ? "启动中…" : "▶ 立即跑周会"}
            </button>
          </div>
          <div className="rounded-lg border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-xs leading-relaxed text-amber-300/90">
            「立即更新一章」会真实执行完整写作流水线并发布到番茄（消耗 API 额度）。
            机器关机错过定时时，开机后点这里即可补更。
          </div>
          <div className="muted text-xs leading-relaxed">
            当前 {wfs.daily?.active ? "日更运行中" : "日更暂停"} · 周会{wfs.weekly?.active ? "运行中" : "已暂停"}
          </div>
        </div>
      </section>

      <section className="panel p-4">
        <div className="section-title !mb-3">运行设置</div>
        {form ? (
          <div className="flex flex-col gap-4">
            <label className="flex cursor-pointer items-center gap-2.5 text-sm">
              <input
                type="checkbox"
                checked={form.daily_enabled}
                onChange={(e) => setForm({ ...form, daily_enabled: e.target.checked })}
                className="h-4 w-4 accent-emerald-500"
              />
              启用每日自动更新
            </label>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">月度预算（元）</label>
                <input
                  type="number"
                  min="0"
                  className="input"
                  value={form.monthly_budget}
                  onChange={(e) => setForm({ ...form, monthly_budget: e.target.value })}
                />
              </div>
              <div>
                <label className="label">目标字数 / 章</label>
                <input
                  type="number"
                  min="500"
                  step="100"
                  className="input"
                  value={form.target_words}
                  onChange={(e) => setForm({ ...form, target_words: e.target.value })}
                />
              </div>
            </div>
            <div>
              <label className="label">风格微调（写入所有写作提示词）</label>
              <input
                type="text"
                className="input"
                placeholder="例：对话更简短，打脸更直接，避免苦大仇深"
                value={form.style_tweak}
                onChange={(e) => setForm({ ...form, style_tweak: e.target.value })}
              />
              <div className="muted mt-1 text-xs">为空时使用 Agent 提示词自带的风格。</div>
            </div>
            <div>
              <label className="label">每日更新时间（时:分）</label>
              <input
                type="time"
                className="input !w-40"
                value={form.daily_run_time}
                onChange={(e) => setForm({ ...form, daily_run_time: e.target.value })}
              />
              <div className="muted mt-1 text-xs">
                保存后立即重新部署定时器；机器关机时段会被错过，开机后请用手动更新补更。
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button className="btn btn-ok" disabled={saving} onClick={save}>
                {saving ? "保存中…" : "💾 保存设置"}
              </button>
              <span className="muted text-xs">
                当前预算 ¥{s.monthly_budget || 100} · {s.target_words || 2000} 字/章
              </span>
            </div>
          </div>
        ) : (
          <div className="empty">设置服务不可达</div>
        )}
      </section>

      <section className="panel p-4 xl:col-span-2">
        <div className="section-title !mb-3">流水线架构说明</div>
        <div className="grid grid-cols-1 gap-4 text-xs leading-relaxed text-slate-400 md:grid-cols-3">
          <div>
            <div className="mb-1.5 font-semibold text-sky-400">写作链（每日）</div>
            热点采集 → 作品资料 → Planner 出大纲 → 守护细纲 → 写手 A/B → 润色 A/B → 审稿 A/B → 读者审稿 A/B → 主编终审 → 番茄发布 → 记忆提炼
          </div>
          <div>
            <div className="mb-1.5 font-semibold text-emerald-400">进化链（每周）</div>
            架构师周会读取运行数据与完读率，输出下一周写作方向、风格调整与大纲修正建议，写入进化记忆。
          </div>
          <div>
            <div className="mb-1.5 font-semibold text-amber-400">Agent 资产</div>
            每个写作智能体的提示词、模型与温度存放在 prompts/agents/*.md，修改后经渲染与校验再部署到 n8n，保证线上与仓库一致。
          </div>
        </div>
      </section>
    </div>
  );
}
