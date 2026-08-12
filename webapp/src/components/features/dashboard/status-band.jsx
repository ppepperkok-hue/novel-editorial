import { StateDot } from "../state-dot.jsx";

const PHASE_TEXT = {
  opening: "开门",
  morning: "晨会",
  producing: "写稿",
  awaiting_close: "待决策",
  closing: "收工",
};

/** 首页状态带：编辑部当前状态 + 今日产出。@stable */
export function StatusBand({ scheduler, summary, todayPublished, todayFailed, lastRun }) {
  const state = deriveState(scheduler, lastRun, todayPublished);
  return (
    <div className="mb-5 flex items-center justify-between rounded-card border border-line bg-surface px-6 py-[18px]">
      <div className="flex items-center gap-3.5">
        <StateDot tone={state.dot} className="size-2.5" />
        <div>
          <div className="text-xl font-bold tracking-[-0.01em] text-ink">{state.text}</div>
          <div className="mt-0.5 text-xs text-ink-2">{state.desc}</div>
        </div>
      </div>
      <div className="text-right">
        <span className="text-[26px] font-bold tracking-[-0.02em] text-ink">{todayPublished}</span>
        <span className="text-xs text-ink-2"> 章已发布</span>
        <div className="mt-0.5 text-[11.5px] text-ink-3">
          {todayFailed > 0 ? `另有 ${todayFailed} 条发布失败 · ` : ""}
          上次运行：{lastRun ? (lastRun.status === "failed" || lastRun.status === "error" ? "失败" : lastRun.status === "partial" ? "部分成功" : "成功") : "暂无"}
        </div>
      </div>
    </div>
  );
}

function deriveState(sch, lastRun, todayPublished) {
  if (!sch) return { text: "状态未知", desc: "无法读取调度器，请检查后端服务", dot: "bad" };
  const row = sch.workday || null;
  const finished = ["completed", "completed_with_pending", "partial", "failed"].includes(row?.status || "");
  if (row?.phase === "awaiting_close") {
    return { text: "待决策", desc: "今天的主产出已完成，可收工、开会或继续", dot: "ok" };
  }
  if (row?.phase && !finished) {
    return {
      text: `工作中 · ${PHASE_TEXT[row.phase] || row.phase}`,
      desc: "编辑部正在上班，可在下方查看当前进度",
      dot: "ok",
    };
  }
  if (row?.status === "completed_with_pending") {
    return { text: "已收工 · 有遗留", desc: "遗留事项明天优先处理", dot: "warn" };
  }
  if (row?.status === "completed") return { text: "已收工", desc: "今天的工作已完整收工", dot: "ok" };
  if (row?.status === "partial") return { text: "已收工 · 部分完成", desc: "明天优先续跑未完成章节", dot: "warn" };
  if (row?.status === "failed") return { text: "已收工 · 失败", desc: "今天没有产出，请查看执行记录", dot: "bad" };
  if (!sch.enabled) return { text: "已暂停", desc: "手动与定时开工均已暂停", dot: "warn" };
  if (lastRun?.status === "failed" || lastRun?.status === "error") {
    return { text: "待命 · 上次失败", desc: String(lastRun.error || "无详情").slice(0, 48), dot: "warn" };
  }
  if (lastRun?.status === "partial") {
    return { text: "待命 · 上次部分成功", desc: `发布 ${lastRun.published ?? 0} 章，有失败节点待处理`, dot: "warn" };
  }
  return {
    text: "待命",
    desc: todayPublished > 0 ? "今天已完成日更" : `${sch.scheduled_time || "08:00"} 自动更新 · 随时可手动开工`,
    dot: "ok",
  };
}
