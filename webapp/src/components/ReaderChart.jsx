import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function ReaderChart({ stats }) {
  if (!stats?.present) {
    return (
      <div className="muted text-sm leading-relaxed">
        暂无真实阅读数据。完读率/追读率由每日「采集阅读数据」自动写入。
      </div>
    );
  }
  const data = (stats.rows || []).map((r) => ({
    name: "第" + r.chapter + "章",
    完读率: Number((r.finish_rate * 100).toFixed(1)),
    追读率: Number((r.follow_rate * 100).toFixed(1)),
  }));
  if (!data.length) {
    return <div className="muted text-sm">已接入数据源，暂无有效读数（新书或数据未更新）。</div>;
  }
  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -18 }}>
          <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
          <XAxis dataKey="name" stroke="#6b7280" fontSize={11} />
          <YAxis stroke="#6b7280" fontSize={11} unit="%" />
          <Tooltip
            contentStyle={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 8 }}
            labelStyle={{ color: "#e5e9f0" }}
          />
          <Line type="monotone" dataKey="完读率" stroke="#34d399" strokeWidth={2} dot={{ r: 3 }} />
          <Line type="monotone" dataKey="追读率" stroke="#60a5fa" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
