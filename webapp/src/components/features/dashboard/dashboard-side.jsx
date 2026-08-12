import { Badge } from "../../ui/badge.jsx";
import { EmptyState } from "../states.jsx";

/** 首页侧栏：待您决定 / 本月 / 最近会议 / 热点。@stable */
export function DashboardSide({ data, drafts, meeting, workdayAwaiting, budget }) {
  const summary = data?.summary || {};
  const healthIssues = data?.health?.issues?.length || 0;
  const passRate = summary.quality_total
    ? Math.round((summary.quality_passed / summary.quality_total) * 100)
    : null;
  const hot = data?.hot_topics;
  const cost = summary.monthly_cost ?? 0;
  const costPct = budget > 0 ? Math.min(100, Math.round((cost / budget) * 100)) : 0;

  const decisions = [];
  if (workdayAwaiting) {
    decisions.push({ title: "今日主产出已完成", desc: "收工、开会或继续补跑，等您决定。" });
  }
  (drafts || []).slice(0, 3).forEach((d) => {
    decisions.push({ title: `经验卡草案：${d.title || "未命名"}`, desc: `来自 ${d.agent || "未知"} · 待采纳` });
  });

  return (
    <div className="flex min-w-0 flex-col gap-7">
      <section className="min-w-0">
        <h2 className="mb-2.5 text-xs font-semibold text-ink">需要您决定</h2>
        {decisions.length ? (
          decisions.map((d, i) => (
            <div key={i} className="border-t border-line py-2.5 first:border-t-0">
              <div className="text-[13px] font-semibold text-ink">{d.title}</div>
              <div className="mt-0.5 text-xs text-ink-2">{d.desc}</div>
            </div>
          ))
        ) : (
          <p className="text-xs leading-relaxed text-ink-3">暂无待决定事项，编辑部运行平稳。</p>
        )}
      </section>

      <section className="min-w-0">
        <h2 className="mb-2.5 text-xs font-semibold text-ink">本月</h2>
        <div className="flex items-baseline justify-between">
          <span className="text-lg font-bold tracking-[-0.02em] text-ink">¥{cost}</span>
          <span className="text-xs text-ink-3">
            预算 ¥{budget} · {costPct}%
          </span>
        </div>
        <div className="mt-2.5 h-[5px] overflow-hidden rounded-[3px] border border-line bg-surface-2">
          <div className="h-full rounded-[3px] bg-accent" style={{ width: `${costPct}%` }} />
        </div>
        <div className="mt-1 flex justify-between border-t border-line py-2 text-xs first:border-t-0">
          <span className="text-ink-2">质量通过率</span>
          <span className={`font-semibold ${passRate !== null && passRate < 70 ? "text-warn" : "text-ok"}`}>
            {passRate !== null ? `${passRate}%` : "—"}
          </span>
        </div>
        <div className="flex justify-between border-t border-line py-2 text-xs">
          <span className="text-ink-2">健康问题</span>
          <span className={`font-semibold ${healthIssues ? "text-bad" : "text-ok"}`}>{healthIssues}</span>
        </div>
        <div className="flex justify-between border-t border-line py-2 text-xs">
          <span className="text-ink-2">发布失败（近 7 天）</span>
          <span className={`font-semibold ${summary.publish_failed ? "text-bad" : "text-ok"}`}>
            {summary.publish_failed ?? 0}
          </span>
        </div>
      </section>

      {meeting ? (
        <section className="min-w-0">
          <h2 className="mb-2.5 text-xs font-semibold text-ink">最近会议</h2>
          <div className="py-2.5">
            <div className="text-[13px] font-semibold text-ink">
              #{meeting.id} · {(meeting.summary || "会议纪要").slice(0, 18)}
            </div>
            <div className="mt-0.5 text-xs leading-relaxed text-ink-2">{meeting.summary}</div>
            <div className="mt-0.5 text-[11.5px] text-ink-3">
              {meeting.held_at} · {meeting.attendees?.length || 0} 人参会
            </div>
            <a href="#/meetings" className="mt-1 inline-block text-xs text-accent-ink hover:underline">
              查看纪要
            </a>
          </div>
        </section>
      ) : null}

      <section className="min-w-0">
        <h2 className="mb-2.5 text-xs font-semibold text-ink">热点选题</h2>
        {hot?.present ? (
          <>
            <div className="flex flex-wrap gap-1.5">
              {(hot.top_keywords || []).slice(0, 5).map(([k, n]) => (
                <span
                  key={k}
                  className="inline-flex h-[22px] items-center rounded-pill bg-accent-soft px-2.5 text-[11px] text-accent-ink"
                >
                  {k} ×{n}
                </span>
              ))}
            </div>
            <p className="mt-2 text-[11.5px] text-ink-3">
              {(hot.sources || []).map((s) => s.source).join(" / ")} · 更新于 {hot.updated_at}
            </p>
          </>
        ) : (
          <p className="text-xs text-ink-3">暂无热点数据，等采集任务写入。</p>
        )}
      </section>
    </div>
  );
}
