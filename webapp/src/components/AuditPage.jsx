import { useEffect, useState } from "react";
import { getAudit } from "../api.js";
import { fmtTime } from "./ui.jsx";

const CATEGORIES = [
  ["", "全部"],
  ["settings", "设置"],
  ["operation", "操作"],
  ["agent", "Agent"],
  ["export", "导出"],
  ["ending", "完结"],
  ["meeting", "周会"],
  ["publish", "发布"],
  ["knowledge", "知识"],
  ["preflight", "预检"],
];

const CATEGORY_LABEL = Object.fromEntries(CATEGORIES);

export default function AuditPage() {
  const [logs, setLogs] = useState([]);
  const [category, setCategory] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    getAudit(category)
      .then((r) => alive && setLogs(r.logs || []))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [category]);

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm text-red-400">
          留痕加载失败：{error}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        {CATEGORIES.map(([val, label]) => (
          <span
            key={val || "all"}
            className={`chip cursor-pointer ${category === val ? "!border-[var(--accent)] !text-[var(--accent-text)]" : ""}`}
            onClick={() => setCategory(val)}
          >
            {label}
          </span>
        ))}
        <span className="muted ml-auto text-xs">共 {logs.length} 条</span>
      </div>

      <div className="panel overflow-hidden">
        <div className="table-wrap max-h-[70vh] overflow-y-auto">
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>类别</th>
                <th>动作</th>
                <th>目标</th>
                <th>详情</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id}>
                  <td className="whitespace-nowrap tabular-nums text-xs">{fmtTime(l.created_at)}</td>
                  <td>
                    <span className="chip chip-info">{CATEGORY_LABEL[l.category] || l.category}</span>
                  </td>
                  <td className="font-medium">{l.action}</td>
                  <td className="text-xs text-slate-400">
                    {l.target_type ? `${l.target_type} #${l.target_id}` : "—"}
                  </td>
                  <td className="max-w-[380px]">
                    <pre className="code max-h-24 overflow-auto rounded-md bg-[var(--code-bg)] px-2 py-1 text-[11px] leading-relaxed">
                      {JSON.stringify(l.detail)}
                    </pre>
                  </td>
                </tr>
              ))}
              {!logs.length ? (
                <tr><td colSpan={5} className="empty">暂无留痕记录。流水线事件会自动写入，包括设置变更、手动操作、Agent 修改、周会落盘、发布与预检。</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
