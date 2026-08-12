import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getDashboard } from "../api.js";
import { EmptyState, ErrorState, LoadingState } from "../components/features/states.jsx";
import { KpiCard } from "../components/features/kpi-card.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { useApi } from "../lib/use-api.js";

/** 阅读数据：读者表现指标与完读率趋势。@stable */
export default function ReaderPage() {
  const { data, error, loading, refresh } = useApi(getDashboard, { interval: 60000 });
  const stats = data?.reader_stats || null;
  const rows = stats?.rows || [];
  const chartData = rows.map((r) => ({
    name: `第${r.chapter}章`,
    完读率: Number((r.finish_rate * 100).toFixed(1)),
    追读率: Number((r.follow_rate * 100).toFixed(1)),
  }));
  const latest = rows[rows.length - 1] || null;

  return (
    <>
      <PageHeader title="阅读数据" desc="读者表现与反馈" />
      {error ? (
        <ErrorState message="阅读数据加载失败" detail={error} onRetry={refresh} />
      ) : loading ? (
        <LoadingState rows={4} />
      ) : !stats?.present ? (
        <EmptyState
          title="暂无真实阅读数据"
          hint="完读率 / 追读率由每日「采集阅读数据」自动写入，新书发布后会陆续出现。"
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard label="样本章节" value={rows.length} sub={`截至第 ${latest?.chapter || 0} 章`} />
            <KpiCard
              label="完读率"
              value={latest ? `${(latest.finish_rate * 100).toFixed(1)}%` : "—"}
              tone="accent"
              sub="最新一章"
            />
            <KpiCard
              label="追读率"
              value={latest ? `${(latest.follow_rate * 100).toFixed(1)}%` : "—"}
              tone="ok"
              sub="最新一章"
            />
            <KpiCard label="数据覆盖" value={`${rows.length} 章`} sub="自动采集" />
          </div>

          <section className="mt-7 min-w-0">
            <div className="mb-3 flex items-baseline justify-between">
              <h2 className="text-xs font-semibold tracking-[0.02em] text-ink">完读率 / 追读率趋势</h2>
              <span className="text-xs text-ink-3">第 1 – {latest?.chapter || rows.length} 章</span>
            </div>
            <div className="h-[260px] rounded-card border border-line bg-surface p-4">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: -14 }}>
                  <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" stroke="var(--ink-3)" fontSize={11} tickLine={false} axisLine={{ stroke: "var(--line)" }} />
                  <YAxis stroke="var(--ink-3)" fontSize={11} tickLine={false} axisLine={false} unit="%" domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{
                      background: "var(--surface)",
                      border: "1px solid var(--line)",
                      borderRadius: 6,
                      fontSize: 12,
                    }}
                    labelStyle={{ color: "var(--ink)" }}
                    itemStyle={{ color: "var(--ink-2)" }}
                  />
                  <Line
                    type="monotone"
                    dataKey="完读率"
                    stroke="var(--accent)"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 3 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="追读率"
                    stroke="var(--ok)"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 3 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>
        </>
      )}
    </>
  );
}
