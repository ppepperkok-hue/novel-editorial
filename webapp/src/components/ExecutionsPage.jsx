import { useEffect, useState } from "react";
import { getExecutions } from "../api.js";

const STATUS = {
  success: ["成功", "chip-ok"],
  failed: ["失败", "chip-bad"],
  running: ["运行中", "chip-warn"],
  waiting: ["等待中", "chip-warn"],
  canceled: ["已取消", "chip-bad"],
  crashed: ["崩溃", "chip-bad"],
};

export default function ExecutionsPage() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await getExecutions();
        if (alive) {
          setRows(r.executions || []);
          setError("");
        }
      } catch (e) {
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

  const fmt = (t) => (t ? String(t).replace("T", " ").slice(5, 19) : "—");
  const duration = (start, stop) => {
    if (!start || !stop) return "—";
    return ((new Date(stop) - new Date(start)) / 1000).toFixed(1) + "s";
  };

  const success = rows.filter((r) => r.status === "success").length;
  const failed = rows.filter((r) => r.status === "failed" || r.status === "crashed").length;

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm text-red-400">
          n8n 执行记录不可达：{error}
        </div>
      ) : null}

      <div className="kpi-grid">
        <div className="card kpi">
          <div className="kpi-label">近 30 次执行</div>
          <div className="kpi-value">{rows.length}</div>
          <div className="kpi-sub">日更 + 周会</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">成功</div>
          <div className="kpi-value badge-ok">{success}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">失败 / 崩溃</div>
          <div className="kpi-value badge-bad">{failed}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">成功率</div>
          <div className="kpi-value">{rows.length ? Math.round((success / rows.length) * 100) : "—"}%</div>
        </div>
      </div>

      <div className="panel overflow-hidden">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>工作流</th>
                <th>执行 ID</th>
                <th>状态</th>
                <th>开始时间</th>
                <th>结束时间</th>
                <th>耗时</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const meta = STATUS[r.status] || [r.status, "chip-warn"];
                return (
                  <tr key={r.workflow + r.id}>
                    <td className="font-medium">{r.workflow}</td>
                    <td className="code text-xs">{r.id}</td>
                    <td><span className={`chip ${meta[1]}`}>{meta[0]}</span></td>
                    <td className="tabular-nums">{fmt(r.started_at)}</td>
                    <td className="tabular-nums">{fmt(r.stopped_at)}</td>
                    <td className="tabular-nums">{duration(r.started_at, r.stopped_at)}</td>
                  </tr>
                );
              })}
              {!rows.length && !error ? (
                <tr><td colSpan={6} className="empty">暂无执行记录（n8n 可能未运行过工作流）</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
