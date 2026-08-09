import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function ReaderPage({ data }) {
  const stats = data?.reader_stats;
  const rows = stats?.rows || [];
  const report = stats?.report;

  const chart = rows.map((r) => ({
    name: "第" + r.chapter + "章",
    完读率: Number((r.finish_rate * 100).toFixed(1)),
    追读率: Number((r.follow_rate * 100).toFixed(1)),
  }));

  const low = report?.low_chapters || [];

  return (
    <div className="flex flex-col gap-4">
      {!stats?.present ? (
        <div className="panel">
          <div className="empty">
            暂无真实阅读数据。每日「采集阅读数据」节点会把番茄作家后台的完读率/追读率写入
            demo_data/reader_stats.csv，写入后此处自动展示。
          </div>
        </div>
      ) : (
        <>
          <div className="kpi-grid">
            <div className="card kpi">
              <div className="kpi-label">已统计章节</div>
              <div className="kpi-value">{report?.chapters ?? rows.length}</div>
            </div>
            <div className="card kpi">
              <div className="kpi-label">平均完读率</div>
              <div className="kpi-value badge-ok">{(report?.avg_finish ?? 0) * 100}%</div>
            </div>
            <div className="card kpi">
              <div className="kpi-label">平均追读率</div>
              <div className="kpi-value badge-ok">{(report?.avg_follow ?? 0) * 100}%</div>
            </div>
            <div className="card kpi">
              <div className="kpi-label">低表现章节</div>
              <div className="kpi-value badge-warn">{low.length}</div>
              <div className="kpi-sub">低于阈值，应反查节奏与钩子</div>
            </div>
          </div>

          <section className="panel p-4">
            <div className="section-title !mb-3">完读率 / 追读率趋势</div>
            {chart.length ? (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chart} margin={{ top: 8, right: 16, bottom: 4, left: -14 }}>
                    <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                    <XAxis dataKey="name" stroke="#64748b" fontSize={11} />
                    <YAxis stroke="#64748b" fontSize={11} unit="%" domain={[0, 100]} />
                    <Tooltip
                      contentStyle={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 8 }}
                      labelStyle={{ color: "#e2e8f0" }}
                      formatter={(v) => [`${v}%`, ""]}
                    />
                    <Line type="monotone" dataKey="完读率" stroke="#34d399" strokeWidth={2.5} dot={{ r: 3.5 }} activeDot={{ r: 5 }} />
                    <Line type="monotone" dataKey="追读率" stroke="#60a5fa" strokeWidth={2.5} dot={{ r: 3.5 }} activeDot={{ r: 5 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="empty">数据源已接入，但还没有有效读数。</div>
            )}
          </section>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <section className="panel overflow-hidden">
              <div className="section-title !mb-3 px-4 pt-4">逐章数据</div>
              <div className="table-wrap max-h-80 overflow-y-auto">
                <table>
                  <thead>
                    <tr>
                      <th>章节</th>
                      <th>完读率</th>
                      <th>追读率</th>
                      <th>状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.chapter}>
                        <td>第 {r.chapter} 章</td>
                        <td className="tabular-nums">{(r.finish_rate * 100).toFixed(1)}%</td>
                        <td className="tabular-nums">{(r.follow_rate * 100).toFixed(1)}%</td>
                        <td>
                          {r.finish_rate < 0.4 || r.follow_rate < 0.4 ? (
                            <span className="chip chip-bad">偏低</span>
                          ) : (
                            <span className="chip chip-ok">健康</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="panel p-4">
              <div className="section-title !mb-3">反馈报告</div>
              {low.length ? (
                <div className="flex flex-col gap-2">
                  {low.map((l, i) => (
                    <div key={i} className="rounded-lg border border-red-900/60 bg-red-950/25 px-3 py-2 text-xs leading-relaxed text-red-300">
                      {typeof l === "object" ? JSON.stringify(l) : l}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-emerald-400">全部章节表现健康，无需干预。</div>
              )}
              {report?.note ? (
                <div className="muted mt-3 text-xs leading-relaxed">{report.note}</div>
              ) : null}
              <div className="muted mt-4 text-xs leading-relaxed">
                低表现章节的反查建议：先看章节开头钩子是否在 200 字内出现、中段是否拖沓、结尾是否有下一章悬念。
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
