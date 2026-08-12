import { useEffect, useState } from "react";
import { toast } from "sonner";
import { getControl, postControl } from "../api.js";
import { EmptyState, ErrorState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { Badge } from "../components/ui/badge.jsx";
import { Button } from "../components/ui/button.jsx";
import { Input } from "../components/ui/input.jsx";
import { cn } from "../lib/utils.js";
import { useApi } from "../lib/use-api.js";

const SECTIONS = [
  ["run", "运行"],
  ["budget", "预算与目标"],
];

/** 系统设置：运行开关、调度、预算与目标。@stable */
export default function SettingsPage() {
  const { data: control, error, loading, refresh } = useApi(getControl, { interval: 30000 });
  const [section, setSection] = useState("run");
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!control) return;
    const s = control.scheduler || {};
    const settings = control.settings || {};
    setForm({
      enabled: Boolean(s.enabled),
      scheduled_time: s.scheduled_time || "08:00",
      monthly_budget: settings.monthly_budget ?? 100,
      target_words: settings.target_words ?? 2000,
      daily_chapters: settings.daily_chapters ?? 2,
      target_chapters: settings.target_chapters ?? 0,
      novel_keywords: settings.novel_keywords || "",
    });
  }, [control]);

  if (!form) return null;

  const valid =
    Number(form.monthly_budget) > 0 &&
    Number(form.target_words) >= 500 &&
    Number(form.target_words) <= 10000 &&
    Number(form.daily_chapters) >= 1 &&
    Number(form.daily_chapters) <= 10;

  const saveSettings = async () => {
    setBusy(true);
    try {
      const r = await postControl({
        action: "save_settings",
        settings: {
          monthly_budget: String(form.monthly_budget),
          target_words: String(form.target_words),
          daily_chapters: String(form.daily_chapters),
          target_chapters: String(form.target_chapters),
          novel_keywords: form.novel_keywords,
        },
      });
      if (r.ok) {
        toast.success("设置已保存");
        refresh();
      } else {
        toast.error(r.error || "保存失败");
      }
    } finally {
      setBusy(false);
    }
  };

  const applySchedule = async () => {
    setBusy(true);
    try {
      const r = await postControl({ action: "apply_schedule", scheduled_time: form.scheduled_time });
      if (r.ok) toast.success("调度已更新");
      else toast.error(r.error || "调度更新失败");
    } finally {
      setBusy(false);
    }
  };

  const toggleDaily = async () => {
    const next = !form.enabled;
    setBusy(true);
    try {
      const r = await postControl({ action: next ? "resume" : "pause", workflow: "daily" });
      if (r.ok) {
        setForm((f) => ({ ...f, enabled: next }));
        toast.success(next ? "日更已恢复" : "日更已暂停");
        refresh();
      } else {
        toast.error(r.error || "操作失败");
      }
    } finally {
      setBusy(false);
    }
  };

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <>
      <PageHeader
        title="系统设置"
        desc="运行、预算、模型与风格"
        actions={
          <Button size="sm" disabled={busy || !valid} onClick={saveSettings}>
            {busy ? "保存中…" : "保存"}
          </Button>
        }
      />
      {error ? (
        <ErrorState message="设置加载失败" detail={error} onRetry={refresh} />
      ) : loading ? (
        <EmptyState title="加载中…" />
      ) : (
        <div className="grid grid-cols-1 gap-7 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.2fr)]">
          <aside className="min-w-0">
            <div className="border-t border-line">
              {SECTIONS.map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setSection(id)}
                  className={cn(
                    "flex w-full items-center border-b border-line py-2.5 text-left text-[13px] transition-colors",
                    section === id ? "font-semibold text-accent-ink" : "text-ink-2 hover:text-ink",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </aside>

          <section className="min-w-0 rounded-card border border-line bg-surface p-5">
            {section === "run" ? (
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-xs text-ink-2">自动定时</label>
                  <div className="inline-flex overflow-hidden rounded-control border border-line">
                    <button
                      type="button"
                      onClick={() => !form.enabled && toggleDaily()}
                      className={cn(
                        "h-8 border-r border-line px-4 text-xs transition-colors",
                        form.enabled ? "bg-ink font-semibold text-canvas" : "text-ink-2 hover:text-ink",
                      )}
                    >
                      开启
                    </button>
                    <button
                      type="button"
                      onClick={() => form.enabled && toggleDaily()}
                      className={cn(
                        "h-8 px-4 text-xs transition-colors",
                        !form.enabled ? "bg-ink font-semibold text-canvas" : "text-ink-2 hover:text-ink",
                      )}
                    >
                      关闭
                    </button>
                  </div>
                  <p className="mt-1.5 text-[11px] leading-relaxed text-ink-3">
                    关闭后仅保留手动开工；本机定时任务由系统计划任务执行。
                  </p>
                </div>
                <div>
                  <label className="mb-1.5 block text-xs text-ink-2">调度时间</label>
                  <div className="flex gap-2">
                    <Input type="time" value={form.scheduled_time} onChange={set("scheduled_time")} />
                    <Button variant="outline" disabled={busy} onClick={applySchedule}>
                      应用
                    </Button>
                  </div>
                  <p className="mt-1.5 text-[11px] text-ink-3">
                    当前状态：
                    <Badge tone={form.enabled ? "ok" : "warn"} className="ml-1">
                      {form.enabled ? "已开启" : "已暂停"}
                    </Badge>
                  </p>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-xs text-ink-2">月预算（¥）</label>
                  <Input type="number" min="1" value={form.monthly_budget} onChange={set("monthly_budget")} />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs text-ink-2">目标字数 / 章</label>
                  <Input type="number" min="500" max="10000" value={form.target_words} onChange={set("target_words")} />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs text-ink-2">日更章数</label>
                  <Input type="number" min="1" max="10" value={form.daily_chapters} onChange={set("daily_chapters")} />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs text-ink-2">目标总章数（0 = 不限）</label>
                  <Input type="number" min="0" value={form.target_chapters} onChange={set("target_chapters")} />
                </div>
                <div className="sm:col-span-2">
                  <label className="mb-1.5 block text-xs text-ink-2">题材关键词（逗号分隔）</label>
                  <Input value={form.novel_keywords} onChange={set("novel_keywords")} placeholder="规则怪谈, 无限流" />
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}
