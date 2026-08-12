import { useState } from "react";
import { getDailyRunDetail, getDailyRuns, getExecutions } from "../api.js";
import { EmptyState, ErrorState, LoadingState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { Badge } from "../components/ui/badge.jsx";
import { Button } from "../components/ui/button.jsx";
import { cn } from "../lib/utils.js";
import { useApi } from "../lib/use-api.js";

const RUN_TONE = {
  success: "ok",
  completed: "ok",
  partial: "warn",
  failed: "bad",
  error: "bad",
  crashed: "bad",
  running: "accent",
  waiting: "warn",
  canceled: "bad",
};

const RUN_LABEL = {
  success: "成功",
  completed: "成功",
  partial: "部分成功",
  failed: "失败",
  error: "失败",
  crashed: "崩溃",
  running: "运行中",
  waiting: "等待中",
  canceled: "已取消",
};

/** 执行记录：工作流执行历史 + 日更运行留痕。@stable */
export default function ExecutionsPage() {
  const { data: execData, error, loading, refresh } = useApi(getExecutions, { interval: 30000 });
  const { data: runData } = useApi(() => getDailyRuns(20), { interval: 30000 });
  const [openRun, setOpenRun] = useState(null);
  const [runDetail, setRunDetail] = useState(null);

  const executions = execData?.executions || [];
  const runs = runData?.runs || [];

  const toggleRun = async (runId) => {
    if (openRun === runId) {
      setOpenRun(null);
      setRunDetail(null);
      return;
    }
    setOpenRun(runId);
    setRunDetail(null);
    try {
      const r = await getDailyRunDetail(runId);
      setRunDetail(r.run || null);
    } catch {
      setRunDetail({ error: "详情加载失败" });
    }
  };

  return (
    <>
      <PageHeader title="执行记录" desc="每次运行的完整留痕与失败详情" />

      <section className="min-w-0">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-xs font-semibold tracking-[0.02em] text-ink">工作流执行</h2>
          <span className="text-xs text-ink-3">{executions.length} 条</span>
        </div>
        {error ? (
          <ErrorState message="执行记录加载失败" detail={error} onRetry={refresh} />
        ) : loading ? (
          <LoadingState rows={4} />
        ) : executions.length ? (
          executions.slice(0, 15).map((r) => (
            <div key={r.id} className="border-t border-line py-3 first:border-t-0">
              <div className="flex flex-wrap items-center gap-2.5">
                <Badge tone={RUN_TONE[r.status] || "neutral"}>{RUN_LABEL[r.status] || r.status}</Badge>
                <span className="text-[13px] font-semibold text-ink">{r.workflow || "日更"}</span>
                <span className="text-xs text-ink-3">
                  {r.started_at} · 发布 {r.published ?? 0} 章
                </span>
                {r.error ? (
                  <span className="max-w-[380px] truncate font-mono text-[11px] text-bad" title={r.error}>
                    {r.error}
                  </span>
                ) : null}
              </div>
            </div>
          ))
        ) : (
          <EmptyState title="还没有执行记录" />
        )}
      </section>

      <section className="mt-8 min-w-0">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-xs font-semibold tracking-[0.02em] text-ink">日更运行留痕</h2>
          <span className="text-xs text-ink-3">
            {runData?.sync_error ? `同步说明：${runData.sync_error}` : `${runs.length} 条`}
          </span>
        </div>
        {runs.length ? (
          runs.map((r) => (
            <div key={r.run_id} className="border-t border-line py-3 first:border-t-0">
              <button
                type="button"
                onClick={() => toggleRun(r.run_id)}
                className="flex w-full flex-wrap items-center gap-2.5 text-left"
              >
                <Badge tone={RUN_TONE[r.status] || "neutral"}>{RUN_LABEL[r.status] || r.status}</Badge>
                <span className="text-[13px] font-semibold text-ink">
                  {r.trigger === "scheduled" ? "定时" : "手动"}运行
                </span>
                <span className="font-mono text-[11px] text-ink-3">{String(r.run_id).slice(0, 16)}</span>
                <span className="text-xs text-ink-3">
                  {r.started_at} · 发布 {r.published ?? 0} 章
                </span>
                <span className={cn("ml-auto text-xs", openRun === r.run_id ? "text-accent-ink" : "text-ink-3")}>
                  {openRun === r.run_id ? "收起" : "展开详情"}
                </span>
              </button>
              {openRun === r.run_id ? (
                <div className="mt-2 rounded-control border border-line bg-surface-2 p-3">
                  {(r.failed_nodes || []).length ? (
                    <div className="mb-2 text-xs">
                      <span className="text-ink-3">失败节点：</span>
                      <span className="text-bad">{r.failed_nodes.join("、")}</span>
                    </div>
                  ) : null}
                  <pre className="max-h-56 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-ink-2">
                    {runDetail?.error || r.error || "无错误详情"}
                  </pre>
                </div>
              ) : null}
            </div>
          ))
        ) : (
          <EmptyState title="还没有日更运行记录" hint="每次开工都会在这里留下完整运行痕迹。" />
        )}
      </section>
    </>
  );
}
