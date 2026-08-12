import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getCost, getDashboard } from "../api.js";
import { EmptyState, ErrorState, LoadingState } from "../components/features/states.jsx";
import { KpiCard } from "../components/features/kpi-card.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table.jsx";
import { useApi } from "../lib/use-api.js";

/** 成本中心：预算、每日成本与节点明细。@stable */
export default function CostPage() {
  const { data: cost, error, loading, refresh } = useApi(getCost, { interval: 30000 });
  const { data: dashboard } = useApi(getDashboard, { interval: 60000 });

  const budget = dashboard?.cost_budget ?? 100;
  const used = dashboard?.summary?.monthly_cost ?? 0;
  const pct = budget > 0 ? Math.min(100, Math.round((used / budget) * 100)) : 0;
  const byDay = (cost?.by_day || []).map((d) => ({
    day: String(d.day || "").slice(5),
    cost: Number(d.cost || 0),
  }));
  const byNode = cost?.by_node || [];
  const totalTokens = byNode.reduce(
    (acc, n) => acc + (n.prompt_tokens || 0) + (n.completion_tokens || 0),
    0,
  );

  return (
    <>
      <PageHeader title="成本中心" desc="API 花费与预算控制" />
      {error ? (
        <ErrorState message="成本数据加载失败" detail={error} onRetry={refresh} />
      ) : loading ? (
        <LoadingState rows={4} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard label="本月已用" value={`¥${used}`} sub={`预算 ¥${budget}`} tone={used >= budget ? "bad" : "ok"} />
            <KpiCard
              label="预算使用率"
              value={`${pct}%`}
              sub={used >= budget ? "已超支" : `还可使用 ¥${Math.max(0, budget - used).toFixed(1)}`}
              tone={used >= budget ? "bad" : "accent"}
            />
            <KpiCard label="累计 Token" value={totalTokens.toLocaleString()} sub="prompt + completion" />
            <KpiCard label="成本节点" value={byNode.length} sub="按节点聚合" />
          </div>

          <section className="mt-7 min-w-0">
            <h2 className="mb-3 text-xs font-semibold tracking-[0.02em] text-ink">每日成本（本月）</h2>
            {byDay.length ? (
              <div className="h-64 rounded-card border border-line bg-surface p-4">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={byDay} margin={{ top: 8, right: 8, bottom: 0, left: -14 }}>
                    <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="day" stroke="var(--ink-3)" fontSize={11} tickLine={false} axisLine={{ stroke: "var(--line)" }} />
                    <YAxis stroke="var(--ink-3)" fontSize={11} tickLine={false} axisLine={false} />
                    <Tooltip
                      cursor={{ fill: "var(--accent-soft)" }}
                      contentStyle={{
                        background: "var(--surface)",
                        border: "1px solid var(--line)",
                        borderRadius: 6,
                        fontSize: 12,
                      }}
                      labelStyle={{ color: "var(--ink)" }}
                      formatter={(v) => [`¥${v}`, "成本"]}
                    />
                    <Bar dataKey="cost" fill="var(--accent)" radius={[5, 5, 0, 0]} maxBarSize={26} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyState title="本月暂无成本记录" hint="流水线执行后自动写入。" />
            )}
          </section>

          <section className="mt-7 min-w-0">
            <h2 className="mb-3 text-xs font-semibold tracking-[0.02em] text-ink">按节点成本</h2>
            <div className="rounded-card border border-line bg-surface px-4 py-1">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>节点</TableHead>
                    <TableHead>模型</TableHead>
                    <TableHead className="text-right">Prompt Tokens</TableHead>
                    <TableHead className="text-right">Completion Tokens</TableHead>
                    <TableHead className="text-right">成本</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {byNode.map((n) => (
                    <TableRow key={n.node_name}>
                      <TableCell className="text-[13px] font-medium text-ink">{n.node_name}</TableCell>
                      <TableCell className="font-mono text-xs text-accent-ink">{n.model || "—"}</TableCell>
                      <TableCell className="text-right tabular-nums text-xs text-ink-2">
                        {Number(n.prompt_tokens || 0).toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs text-ink-2">
                        {Number(n.completion_tokens || 0).toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs text-ink">
                        ¥{Number(n.cost || 0).toFixed(4)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
