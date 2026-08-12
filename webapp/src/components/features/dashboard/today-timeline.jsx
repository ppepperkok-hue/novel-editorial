import { Badge } from "../../ui/badge.jsx";
import { EmptyState } from "../states.jsx";

function localDate(t) {
  return String(t || "").slice(0, 10);
}

function localToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** 今日记录：发布时间线 + 执行摘要。@stable */
export function TodayTimeline({ publishLogs, executions }) {
  const today = localToday();
  const logs = (publishLogs || [])
    .filter((l) => localDate(l.created_at) === today)
    .slice(0, 6);
  const runs = (executions || []).filter((r) => localDate(r.started_at) === today).slice(0, 3);

  if (!logs.length && !runs.length) {
    return (
      <EmptyState
        title="今天还没有记录"
        hint="开工后，发布、会议与预检都会出现在这里。"
        className="border-x-0 border-b-0 border-t border-dashed px-0 py-6"
      />
    );
  }

  const items = [
    ...runs.map((r) => ({
      time: String(r.started_at || "").slice(11, 16),
      text: (
        <>
          <strong>{r.trigger === "scheduled" ? "定时" : "手动"}运行</strong> · {r.published ?? 0} 章发布
        </>
      ),
      tone: r.status === "failed" || r.status === "error" ? "bad" : "ok",
      label: r.status === "failed" || r.status === "error" ? "失败" : r.status === "partial" ? "部分" : "成功",
    })),
    ...logs.map((l) => ({
      time: String(l.created_at || "").slice(11, 16),
      text: (
        <>
          <strong>#{l.chapter_id}</strong> {l.action === "publish" ? "已发布" : l.action}
        </>
      ),
      tone: l.result === "failed" ? "bad" : "ok",
      label: l.result === "failed" ? "失败" : "成功",
    })),
  ]
    .sort((a, b) => (a.time < b.time ? 1 : -1))
    .slice(0, 8);

  return (
    <div className="border-t border-line">
      {items.map((item, i) => (
        <div
          key={`${item.time}-${i}`}
          className="flex items-baseline gap-3.5 border-b border-line py-[9px] text-xs last:border-b-0"
        >
          <span className="w-[52px] shrink-0 font-mono text-[11.5px] text-ink-3">{item.time}</span>
          <span className="min-w-0 flex-1 truncate text-ink-2">{item.text}</span>
          <Badge tone={item.tone === "bad" ? "bad" : "ok"} className="ml-auto shrink-0">
            {item.label}
          </Badge>
        </div>
      ))}
    </div>
  );
}
