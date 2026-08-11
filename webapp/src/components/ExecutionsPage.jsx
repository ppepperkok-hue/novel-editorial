import { useEffect, useState } from "react";
import { getDailyRunDetail, getDailyRuns, getExecutions } from "../api.js";
import { fmtRelative } from "./ui.jsx";

const STATUS = {
  success: ["成功", "chip-ok"],
  completed: ["成功", "chip-ok"],
  partial: ["部分成功", "chip-warn"],
  failed: ["失败", "chip-bad"],
  error: ["失败", "chip-bad"],
  running: ["运行中", "chip-warn"],
  waiting: ["等待中", "chip-warn"],
  canceled: ["已取消", "chip-bad"],
  crashed: ["崩溃", "chip-bad"],
};

const RUN_STATUS = {
  success: ["成功", "chip-ok"],
  completed: ["成功", "chip-ok"],
  partial: ["部分成功", "chip-warn"],
  failed: ["失败", "chip-bad"],
  error: ["失败", "chip-bad"],
  crashed: ["崩溃", "chip-bad"],
  running: ["运行中", "chip-warn"],
  waiting: ["等待中", "chip-warn"],
  canceled: ["已取消", "chip-bad"],
};

export default function ExecutionsPage({ snapshot }) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);
  const [runs, setRuns] = useState([]);
  const [openRun, setOpenRun] = useState(null);
  const [runDetail, setRunDetail] = useState(null);

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

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await getDailyRuns(20);
        if (alive) setRuns(r.runs || []);
      } catch (e) {
        /* backend offline: local records stay visible; ignore here */
      }
    };
    load();
    const t = setInterval(load, 30000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const toggleRun = async (runId) => {
    if (openRun === runId) {
      setOpenRun(null);
      setRunDetail(null);
      return;
    }
    setOpenRun(runId);
    try {
      const r = await getDailyRunDetail(runId);
      setRunDetail(r.run || null);
    } catch (e) {
      setRunDetail(null);
    }
  };

  const fmt = (t) => (t ? String(t).replace("T", " ").slice(5, 19) : "-");
  const duration = (start, stop) => {
    if (!start || !stop) return "—";
    return ((new Date(stop) - new Date(start)) / 1000).toFixed(1) + "s";
  };
  const failedRows = rows.filter((r) => r.status === "failed" || r.status === "crashed" || r.status === "error");
  const runningRows = rows.filter((r) => r.status === "running" || r.status === "waiting");

  const success = rows.filter((r) => r.status === "success").length;
  const failed = rows.filter((r) => ["failed", "crashed", "error"].includes(r.status)).length;
  const finished = success + failed;

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm text-red-400">
          执行记录不可达：{error}
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
          <div className="kpi-value">{finished ? Math.round((success / finished) * 100) : "—"}%</div>
          <div className="kpi-sub">按已完成执行计算</div>
        </div>
      </div>

      <div className="panel p-4">
        <div className="mb-2 flex items-center justify-between">
          <div className="text-sm font-bold">日更运行留痕</div>
          <div className="flex items-center gap-2">
            <span className="muted text-xs">本地持久化，离线也可回看</span>
            <a className="btn !px-3 !py-1 text-xs" href="#flow">⬡ 链路</a>
          </div>
        </div>
        {runs.length ? (
          <div className="flex flex-col gap-1.5">
            {runs.map((r) => {
              const meta = RUN_STATUS[r.status] || [r.status, "chip-warn"];
              return (
                <div key={r.run_id} className="rounded-lg border border-[var(--line)] bg-[var(--bg-soft)]">
                  <button
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs"
                    onClick={() => toggleRun(r.run_id)}
                  >
                    <span className={`chip ${meta[1]}`}>{meta[0]}</span>
                    <span className="code">{r.run_id}</span>
                    <span className="muted">
                      {r.started_at ? String(r.started_at).slice(5, 16) : "-"}
                      {r.finished_at ? " → " + String(r.finished_at).slice(11, 19) : ""}
                    </span>
                    <span className="muted">发布 {r.published} 章</span>
                    {(r.failed_nodes || []).length ? (
                      <span className="chip chip-bad">{r.failed_nodes[0]}</span>
                    ) : null}
                    <span className="muted ml-auto">{openRun === r.run_id ? "▲" : "▼"}</span>
                  </button>
                  {openRun === r.run_id && runDetail ? (
                    <div className="border-t border-[var(--line-soft)] px-3 py-2">
                      <div className="muted mb-1 text-xs">
                        触发 {runDetail.trigger} · 失败节点 {(runDetail.failed_nodes || []).join("、") || "无"}
                      </div>
                      {runDetail.error ? (
                        <pre className="code max-h-40 overflow-auto rounded-lg bg-[var(--code-bg)] p-2.5 text-xs leading-relaxed text-red-300">
                          {runDetail.error}
                        </pre>
                      ) : (
                        <div className="muted text-xs">本次运行无错误详情</div>
                      )}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="muted text-xs">暂无本地运行留痕，日更执行后自动写入。</div>
        )}
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
                <th>耗时</th>
                <th>失败详情</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const meta = STATUS[r.status] || [r.status, "chip-warn"];
                const hasError = r.error && r.status !== "success";
                return (
                  <tr key={r.workflow + r.id} className={`${hasError ? "cursor-pointer" : ""} align-middle`} onClick={hasError ? () => setDetail(r) : undefined}>
                    <td className="font-medium">{r.workflow}</td>
                    <td className="code text-xs">{r.id}</td>
                    <td><span className={`chip ${meta[1]}`}>{meta[0]}</span></td>
                    <td className="whitespace-nowrap tabular-nums">{fmtRelative(r.started_at)}</td>
                    <td className="whitespace-nowrap tabular-nums">{duration(r.started_at, r.stopped_at)}</td>
                    <td>
                      {hasError ? (
                        <span className="whitespace-nowrap chip chip-bad">查看原因</span>
                      ) : (
                        <span className="muted text-xs">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {!rows.length && !error ? (
                <tr><td colSpan={7} className="empty">暂无执行记录，日更运行后自动写入</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      <div className="kpi-grid !grid-cols-2">
        <div className="card kpi">
          <div className="kpi-label">运行中 / 等待</div>
          <div className="kpi-value badge-warn">{runningRows.length}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">失败待排查</div>
          <div className="kpi-value badge-bad">{failedRows.length}</div>
        </div>
      </div>

      {detail ? (
        <div className="modal-mask" onMouseDown={(e) => e.target === e.currentTarget && setDetail(null)}>
          <div className="modal confirm-modal">
            <div className="modal-head">
              <div className="text-sm font-bold">
                执行 #{detail.id} 失败详情（{detail.workflow}）
              </div>
              <button className="btn !px-2 !py-0.5 text-sm" onClick={() => setDetail(null)}>✕</button>
            </div>
            <div className="modal-body">
              <pre className="code max-h-80 overflow-auto rounded-lg bg-[var(--code-bg)] p-3 text-xs leading-relaxed text-red-300">
                {detail.error}
              </pre>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
