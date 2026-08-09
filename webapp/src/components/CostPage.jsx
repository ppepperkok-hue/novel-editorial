import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getCost } from "../api.js";

export default function CostPage({ data }) {
  const [cost, setCost] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await getCost();
        if (alive) setCost(r);
      } catch (e) {
        if (alive) setCost(null);
        if (alive) setError(String(e));
      }
    };
    load();
    const t = setInterval(load, 30000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const s = data?.summary || {};
  const budget = data?.cost_budget ?? 100;
  const used = s.monthly_cost ?? 0;
  const pct = Math.min(100, Math.round((used / budget) * 100));
  const byDay = (cost?.by_day || []).map((d) => ({
    day: (d.day || "").slice(5),
    cost: Number(d.cost || 0),
  }));
  const byNode = cost?.by_node || [];
  const totalTokens = byNode.reduce((acc, n) => acc + (n.prompt_tokens || 0) + (n.completion_tokens || 0), 0);

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm text-red-400">
          成本数据加载失败：{error}
        </div>
      ) : null}
      <div className="kpi-grid">
        <div className="card kpi">
          <div className="kpi-label">本月已用</div>
          <div className="kpi-value badge-ok">¥{used}</div>
          <div className="kpi-sub">预算 ¥{budget}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">预算使用率</div>
          <div className="kpi-value">{pct}%</div>
          <div className="kpi-sub">{used >= budget ? "已超支" : `还可使用 ¥${Math.max(0, budget - used)}`}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">累计 Token</div>
          <div className="kpi-value">{totalTokens.toLocaleString()}</div>
          <div className="kpi-sub">prompt + completion</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">成本节点数</div>
          <div className="kpi-value">{byNode.length}</div>
          <div className="kpi-sub">按节点聚合</div>
        </div>
      </div>

      <div className="panel p-4">
        <div className="section-title !mb-3">预算进度</div>
        <div className="progress mb-3" style={{ height: 10 }}>
          <div style={{ width: `${pct}%` }} />
        </div>
        <div className="muted text-xs">可在「系统设置」中调整月度预算，超支时面板会标红提醒。</div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="panel p-4">
          <div className="section-title !mb-3">每日成本（本月）</div>
          {byDay.length ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byDay} margin={{ top: 8, right: 8, bottom: 0, left: -14 }}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="day" stroke="#64748b" fontSize={11} />
                  <YAxis stroke="#64748b" fontSize={11} />
                  <Tooltip
                    cursor={{ fill: "rgba(56,189,248,0.06)" }}
                    contentStyle={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 8 }}
                    labelStyle={{ color: "#e2e8f0" }}
                    formatter={(v) => [`¥${v}`, "成本"]}
                  />
                  <Bar dataKey="cost" fill="#38bdf8" radius={[5, 5, 0, 0]} maxBarSize={26} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="empty">本月暂无成本记录，流水线执行后自动写入。</div>
          )}
        </section>

        <section className="panel overflow-hidden">
          <div className="section-title !mb-3 px-4 pt-4">按节点成本</div>
          <div className="table-wrap max-h-72 overflow-y-auto">
            <table>
              <thead>
                <tr>
                  <th>节点</th>
                  <th>模型</th>
                  <th>Prompt Tokens</th>
                  <th>Completion Tokens</th>
                  <th>成本</th>
                </tr>
              </thead>
              <tbody>
                {byNode.map((n) => (
                  <tr key={n.node_name}>
                    <td className="font-medium">{n.node_name}</td>
                    <td className="code text-xs text-sky-400">{n.model || "—"}</td>
                    <td className="tabular-nums">{Number(n.prompt_tokens || 0).toLocaleString()}</td>
                    <td className="tabular-nums">{Number(n.completion_tokens || 0).toLocaleString()}</td>
                    <td className="tabular-nums text-amber-400">¥{Number(n.cost || 0).toFixed(4)}</td>
                  </tr>
                ))}
                {!byNode.length ? (
                  <tr><td colSpan={5} className="empty">暂无节点成本</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
