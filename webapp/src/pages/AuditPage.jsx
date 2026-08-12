import { useEffect, useState } from "react";
import { getAudit } from "../api.js";
import { EmptyState, ErrorState, LoadingState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { Badge } from "../components/ui/badge.jsx";
import { Button } from "../components/ui/button.jsx";
import { Input } from "../components/ui/input.jsx";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table.jsx";

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

function fmtTime(t) {
  return String(t || "").replace("T", " ").slice(0, 19);
}

/** 留痕档案：全量事件审计。@stable */
export default function AuditPage() {
  const [logs, setLogs] = useState(null);
  const [error, setError] = useState("");
  const [category, setCategory] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setLogs(null);
    getAudit(category, dateFrom, dateTo)
      .then((r) => {
        if (alive) {
          setLogs(r.logs || []);
          setError("");
        }
      })
      .catch((e) => {
        if (alive) {
          setLogs([]);
          setError(String(e));
        }
      });
    return () => {
      alive = false;
    };
  }, [category, dateFrom, dateTo, tick]);

  const exportLogs = () => {
    const blob = new Blob([JSON.stringify(logs || [], null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "audit-logs.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <PageHeader title="留痕档案" desc="编辑部全量事件审计" />
      <div className="flex flex-wrap items-center gap-2.5 border-t border-line py-3">
        <Input
          type="date"
          className="h-8 w-[140px] text-xs"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          aria-label="起始日期"
        />
        <span className="text-xs text-ink-3">至</span>
        <Input
          type="date"
          className="h-8 w-[140px] text-xs"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          aria-label="结束日期"
        />
        <div className="flex flex-wrap gap-1.5">
          {CATEGORIES.map(([val, label]) => (
            <button
              key={val || "all"}
              type="button"
              onClick={() => setCategory(val)}
              className={
                category === val
                  ? "inline-flex h-5 items-center rounded-pill bg-accent-soft px-2 text-[10.5px] font-semibold text-accent-ink"
                  : "inline-flex h-5 items-center rounded-pill border border-line bg-surface-2 px-2 text-[10.5px] text-ink-2 hover:text-ink"
              }
            >
              {label}
            </button>
          ))}
        </div>
        <span className="ml-auto flex items-center gap-2 text-xs text-ink-3">
          共 {logs?.length ?? 0} 条
          <Button variant="outline" size="sm" onClick={() => setTick((t) => t + 1)}>
            刷新
          </Button>
          <Button variant="outline" size="sm" disabled={!logs?.length} onClick={exportLogs}>
            导出 JSON
          </Button>
        </span>
      </div>

      {error ? (
        <ErrorState message="留痕加载失败" detail={error} onRetry={() => setTick((t) => t + 1)} />
      ) : logs === null ? (
        <LoadingState rows={6} />
      ) : logs.length ? (
        <div className="rounded-card border border-line bg-surface px-4 py-1">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>时间</TableHead>
                <TableHead>类别</TableHead>
                <TableHead>动作</TableHead>
                <TableHead>目标</TableHead>
                <TableHead>详情</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.slice(0, 300).map((l) => (
                <TableRow key={l.id}>
                  <TableCell className="whitespace-nowrap font-mono text-[11px] text-ink-3">
                    {fmtTime(l.created_at)}
                  </TableCell>
                  <TableCell>
                    <Badge tone="accent">{CATEGORY_LABEL[l.category] || l.category}</Badge>
                  </TableCell>
                  <TableCell className="text-[13px] font-medium text-ink">{l.action}</TableCell>
                  <TableCell className="text-xs text-ink-3">
                    {l.target_type ? `${l.target_type} #${l.target_id}` : "—"}
                  </TableCell>
                  <TableCell className="max-w-[360px]">
                    <pre className="max-h-20 overflow-auto whitespace-pre-wrap rounded-[4px] bg-surface-2 px-2 py-1 font-mono text-[11px] leading-relaxed text-ink-2">
                      {JSON.stringify(l.detail)}
                    </pre>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <EmptyState
          title="暂无留痕记录"
          hint="设置变更、手动操作、Agent 修改、周会落盘、发布与预检都会自动写入。"
        />
      )}
    </>
  );
}
