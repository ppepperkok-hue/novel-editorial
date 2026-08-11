import { useEffect, useRef, useState } from "react";
import { getControl, postControl } from "../api.js";
import { ConfirmDialog } from "./ui.jsx";

const desktopApi = typeof window !== "undefined" ? window.desktopApi || null : null;

function WorkflowCard({ label, wf, onAction, onPause }) {
  const state = !wf?.online
    ? { text: "n8n 离线", cls: "chip-bad" }
    : wf.active
      ? { text: "运行中", cls: "chip-ok" }
      : { text: "已暂停", cls: "chip-bad" };
  const statusText = {
    success: "成功",
    running: "运行中",
    waiting: "等待中",
    failed: "失败",
    crashed: "崩溃",
    canceled: "已取消",
  }[wf?.last?.status] || wf?.last?.status;
  const last = wf?.last
    ? `${statusText} · ${(wf.last.stopped_at || wf.last.started_at || "").replace("T", " ").slice(5, 19)}`
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
            <button className="btn btn-danger !px-3 !py-1 text-xs" onClick={onPause}>暂停</button>
          ) : (
            <button className="btn btn-ok !px-3 !py-1 text-xs" onClick={() => onAction("resume")}>恢复</button>
          ))}
      </div>
    </div>
  );
}

export default function SettingsPage({ data, onRefresh, pushToast, theme, onThemeChange }) {
  const [control, setControl] = useState(null);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState("");
  const [confirm, setConfirm] = useState(null);
  const [confirmRun, setConfirmRun] = useState(null);
  const [runChapters, setRunChapters] = useState(2);
  const [autoLaunch, setAutoLaunch] = useState(false);
  const autoLaunchInit = useRef(false);

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
          daily_chapters: c.settings?.daily_chapters || 2,
          target_chapters: c.settings?.target_chapters || 0,
          novel_premise: c.settings?.novel_premise || "",
          novel_keywords: c.settings?.novel_keywords || "",
          novel_genre: c.settings?.novel_genre || "",
        },
      );
    } catch {
      setControl(null);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (desktopApi && !autoLaunchInit.current) {
      autoLaunchInit.current = true;
      desktopApi.getAutoLaunch().then(setAutoLaunch).catch(() => {});
    }
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
          daily_chapters: String(form.daily_chapters),
          target_chapters: String(form.target_chapters),
          novel_premise: form.novel_premise,
          novel_keywords: form.novel_keywords,
          novel_genre: form.novel_genre,
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
    setConfirmRun(null);
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

  const budgetNum = Number(form?.monthly_budget);
  const wordsNum = Number(form?.target_words);
  const chaptersNum = Number(form?.daily_chapters);
  const targetNum = Number(form?.target_chapters);
  const formValid =
    form != null &&
    !Number.isNaN(budgetNum) &&
    budgetNum > 0 &&
    !Number.isNaN(wordsNum) &&
    wordsNum >= 500 &&
    wordsNum <= 10000 &&
    chaptersNum >= 1 &&
    chaptersNum <= 10 &&
    targetNum >= 0 &&
    targetNum <= 5000 &&
    /^\d{2}:\d{2}$/.test(form.daily_run_time || "");

  const wfs = control?.workflows || {};
  const s = control?.settings || {};

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <section className="panel p-4">
        <div className="section-title !mb-3">工作流控制</div>
        <div className="flex flex-col gap-3">
          <WorkflowCard label={`日更工作流（${wfs.daily?.nodes ?? "?"} 节点）`} wf={wfs.daily} onAction={(a) => action({ action: a, workflow: "daily" }, "日更已恢复")} onPause={() => setConfirm("pause-daily")} />
          <WorkflowCard label={`架构师周会（${wfs.weekly?.nodes ?? "?"} 节点）`} wf={wfs.weekly} onAction={(a) => action({ action: a, workflow: "weekly" }, "周会已恢复")} onPause={() => setConfirm("pause-weekly")} />
          <WorkflowCard label={`知识管家（${wfs.keeper?.nodes ?? "?"} 节点）`} wf={wfs.keeper} onAction={(a) => action({ action: a, workflow: "keeper" }, "知识管家已恢复")} onPause={() => setConfirm("pause-keeper")} />
          <div className="grid grid-cols-2 gap-2">
            <button
              className="btn btn-ok"
              disabled={running !== ""}
              onClick={() => setConfirmRun("daily")}
            >
              {running === "daily" ? "启动中…" : "▶ 立即补更（按每日章数）"}
            </button>
            <button
              className="btn"
              disabled={running !== ""}
              onClick={() => setConfirmRun("weekly")}
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
                <div className={`mt-1 text-xs ${budgetNum > 0 ? "muted" : "text-red-400"}`}>
                  预算必须大于 0
                </div>
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
                <div className={`mt-1 text-xs ${wordsNum >= 500 && wordsNum <= 10000 ? "muted" : "text-red-400"}`}>
                  目标字数建议 500–10000
                </div>
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
              <label className="label">日更题材 · 核心设定（premise）</label>
              <textarea
                className="input min-h-20 w-full"
                placeholder="例：凡人修仙：捡到一只会提纯灵物的破碗，从杂灵根苟到无敌"
                value={form.novel_premise}
                onChange={(e) => setForm({ ...form, novel_premise: e.target.value })}
              />
              <div className="muted mt-1 text-xs">
                留空时使用 .env 的 NOVEL_PREMISE，两者都没有则用工作流内置默认题材。
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">题材（genre）</label>
                <input
                  type="text"
                  className="input"
                  placeholder="例：玄幻"
                  value={form.novel_genre}
                  onChange={(e) => setForm({ ...form, novel_genre: e.target.value })}
                />
              </div>
              <div>
                <label className="label">关键词（逗号分隔）</label>
                <input
                  type="text"
                  className="input"
                  placeholder="例：修仙,苟,提纯,杂灵根"
                  value={form.novel_keywords}
                  onChange={(e) => setForm({ ...form, novel_keywords: e.target.value })}
                />
              </div>
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
            <div>
              <label className="label">每批发布章数（1–10，存稿优先）</label>
              <input
                type="number"
                min="1"
                max="10"
                className="input !w-32"
                value={form.daily_chapters}
                onChange={(e) => setForm({ ...form, daily_chapters: e.target.value })}
              />
              <div className="muted mt-1 text-xs">
                每天先发存稿池里的章节，不够再现场生成补足；多出来的章节会存着下次发。
              </div>
            </div>
            <div>
              <label className="label">目标总章数（0 = 不限，达到 90% 后周会评估收尾）</label>
              <input
                type="number"
                min="0"
                max="5000"
                className="input !w-32"
                value={form.target_chapters}
                onChange={(e) => setForm({ ...form, target_chapters: e.target.value })}
              />
              <div className="muted mt-1 text-xs">
                设了上限后，完结评估 Agent 会在临近目标时建议收尾；0 表示只看剧情判断。
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button className="btn btn-ok" disabled={saving || !formValid} onClick={save}>
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

      <section className="panel p-4">
        <div className="section-title !mb-3">外观主题</div>
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-3 gap-2">
            {[
              ["dark", "深色", "适合夜间与长时间使用"],
              ["light", "浅色", "明亮清爽"],
              ["system", "跟随系统", "随 Windows 主题自动切换"],
            ].map(([id, label, desc]) => (
              <button
                key={id}
                className={`btn flex-col !items-start !py-3 text-left ${theme === id ? "btn-primary" : ""}`}
                onClick={() => onThemeChange(id)}
              >
                <span className="text-sm font-semibold">{label}</span>
                <span className="muted mt-0.5 text-xs">{desc}</span>
              </button>
            ))}
          </div>
          <div className="muted text-xs">主题选择会保存，下次启动自动恢复。</div>
        </div>
      </section>

      {desktopApi ? (
        <section className="panel p-4">
          <div className="section-title !mb-3">桌面应用</div>
          <div className="flex flex-col gap-3">
            <label className="flex cursor-pointer items-center gap-2.5 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4 accent-emerald-500"
                checked={autoLaunch}
                onChange={(e) => {
                  setAutoLaunch(e.target.checked);
                  desktopApi.setAutoLaunch(e.target.checked).then((v) => {
                    setAutoLaunch(v);
                    pushToast(v ? "已开启开机自启" : "已关闭开机自启", "ok");
                  });
                }}
              />
              开机自动启动
            </label>
            <div className="muted text-xs leading-relaxed">
              关闭窗口会最小化到系统托盘，应用在后台继续运行；需要完全退出请点下面的按钮。
            </div>
            <div>
              <button className="btn btn-danger" onClick={() => desktopApi.quit()}>
                退出应用
              </button>
            </div>
          </div>
        </section>
      ) : null}

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

      <ConfirmDialog
        open={confirm === "pause-daily" || confirm === "pause-weekly" || confirm === "pause-keeper"}
        title="暂停工作流？"
        body="暂停后定时触发将停止，需要手动恢复。"
        confirmText="暂停"
        onCancel={() => setConfirm(null)}
        onConfirm={() => {
          const workflow = confirm === "pause-daily" ? "daily" : confirm === "pause-weekly" ? "weekly" : "keeper";
          setConfirm(null);
          action({ action: "pause", workflow }, "已暂停");
        }}
      />

      <ConfirmDialog
        open={confirmRun === "weekly"}
        title="立即执行架构师周会？"
        body="周会会调用架构师模型生成蓝图并写入作品设定，耗时约 2 分钟。"
        confirmText="立即跑周会"
        busy={running !== ""}
        onCancel={() => setConfirmRun(null)}
        onConfirm={() => {
          runNow("weekly", "架构师周会");
        }}
      />

      {confirmRun === "daily" ? (
        <div className="modal-mask" onMouseDown={(e) => e.target === e.currentTarget && setConfirmRun(null)}>
          <div className="modal confirm-modal">
            <div className="modal-head">
              <div className="text-sm font-bold">本次发布几章？</div>
              <button className="btn !px-2 !py-0.5 text-sm" onClick={() => setConfirmRun(null)}>✕</button>
            </div>
            <div className="modal-body">
              <div className="mb-4 text-sm text-slate-400">
                存稿池有存货就直接发，不够会自动补造。最多一次发 5 章。
              </div>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    className={`btn flex-1 !py-3 text-base ${runChapters === n ? "btn-primary" : ""}`}
                    onClick={() => setRunChapters(n)}
                  >
                    {n} 章
                  </button>
                ))}
              </div>
              <div className="mt-5 flex justify-end gap-2">
                <button className="btn" onClick={() => setConfirmRun(null)}>取消</button>
                <button
                  className="btn btn-ok"
                  disabled={running !== ""}
                  onClick={() => {
                    setConfirmRun(null);
                    setRunning("daily");
                    postControl({ action: "run_now", workflow: "daily", chapters: runChapters })
                      .then((r) => {
                        pushToast(
                          r.ok ? `已启动：本次目标发布 ${runChapters} 章` : `启动失败：${r.error || "未知"}`,
                          r.ok ? "ok" : "bad",
                        );
                      })
                      .catch((e) => pushToast("启动失败：" + e, "bad"))
                      .finally(() => {
                        setRunning("");
                        refresh();
                        onRefresh();
                      });
                  }}
                >
                  发布 {runChapters} 章
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
