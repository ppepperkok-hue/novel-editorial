import { useEffect, useMemo, useRef, useState } from "react";
import { postControl } from "../api.js";

const PAGE_CMDS = [
  { id: "dashboard", label: "打开仪表盘", group: "页面", icon: "◈" },
  { id: "works", label: "打开作品库", group: "页面", icon: "▤" },
  { id: "chapters", label: "打开章节管理", group: "页面", icon: "≡" },
  { id: "agents", label: "打开 Agent 管理", group: "页面", icon: "◇" },
  { id: "cost", label: "打开成本中心", group: "页面", icon: "¥" },
  { id: "executions", label: "打开执行记录", group: "页面", icon: "⏱" },
  { id: "reader", label: "打开阅读数据", group: "页面", icon: "◔" },
  { id: "settings", label: "打开系统设置", group: "页面", icon: "⚙" },
  { id: "meetings", label: "打开周会档案", group: "页面", icon: "▦" },
  { id: "audit", label: "打开留痕档案", group: "页面", icon: "≡" },
];

export default function CommandPalette({ onRefresh, pushToast, go, changeTheme, theme }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
        setQuery("");
        setIndex(0);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [open]);

  const runAction = async (cmd) => {
    setOpen(false);
    if (cmd.group === "页面") {
      go(cmd.id);
      return;
    }
    if (cmd.id === "refresh") {
      onRefresh();
      pushToast("已刷新数据", "ok");
      return;
    }
    if (cmd.id.startsWith("theme-")) {
      changeTheme(cmd.id.replace("theme-", ""));
      pushToast(`主题已切换为${cmd.id.replace("theme-", "") === "dark" ? "深色" : cmd.id.replace("theme-", "") === "light" ? "浅色" : "跟随系统"}`, "ok");
      return;
    }
    setBusy(true);
    try {
      if (cmd.id === "run-daily" || cmd.id === "run-weekly") {
        const r = await postControl({
          action: "run_now",
          workflow: cmd.id === "run-daily" ? "daily" : "weekly",
        });
        pushToast(
          r.ok
            ? `${cmd.id === "run-daily" ? "日更" : "周会"}已启动，后台执行中`
            : `启动失败：${r.error || "未知"}`,
          r.ok ? "ok" : "bad",
        );
        return;
      }
      const [action, workflow] = cmd.id.split("-");
      const r = await postControl({ action, workflow });
      pushToast(r.ok ? `操作成功：${workflow} ${action === "pause" ? "已暂停" : "已恢复"}` : `操作失败：${r.error || "未知"}`, r.ok ? "ok" : "bad");
      onRefresh();
    } finally {
      setBusy(false);
    }
  };

  const commands = useMemo(() => {
    const base = [
      ...PAGE_CMDS,
      { id: "refresh", label: "刷新全部数据", group: "操作", icon: "⟳" },
      { id: "run-daily", label: "立即补更（按当日章数，真实发布）", group: "操作", icon: "▶" },
      { id: "run-weekly", label: "立即跑架构师周会", group: "操作", icon: "▶" },
      { id: "pause-daily", label: "暂停日更工作流", group: "操作", icon: "⏸" },
      { id: "resume-daily", label: "恢复日更工作流", group: "操作", icon: "▶" },
      { id: "theme-dark", label: "切换到深色主题", group: "外观", icon: "◐" },
      { id: "theme-light", label: "切换到浅色主题", group: "外观", icon: "◑" },
      { id: "theme-system", label: "主题跟随系统", group: "外观", icon: "⚙" },
    ];
    const q = query.trim().toLowerCase();
    if (!q) return base;
    return base.filter(
      (c) =>
        c.label.toLowerCase().includes(q) ||
        c.group.toLowerCase().includes(q) ||
        c.id.includes(q),
    );
  }, [query]);

  useEffect(() => {
    setIndex(0);
  }, [query, open]);

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIndex((i) => Math.min(i + 1, commands.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const cmd = commands[index];
      if (cmd) runAction(cmd);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  if (!open) return null;

  return (
    <div className="modal-mask cmd-mask" onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
      <div className="cmd-palette">
        <div className="cmd-input-wrap">
          <span className="cmd-search-icon">⌕</span>
          <input
            ref={inputRef}
            className="cmd-input"
            placeholder="搜索命令：页面、刷新、运行、主题…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <kbd className="cmd-kbd">Esc</kbd>
        </div>
        <div className="cmd-list">
          {commands.map((c, i) => (
            <button
              key={c.id}
              className={`cmd-item ${i === index ? "active" : ""}`}
              onMouseEnter={() => setIndex(i)}
              onClick={() => runAction(c)}
              disabled={busy}
            >
              <span className="cmd-icon">{c.icon}</span>
              <span className="cmd-label">{c.label}</span>
              <span className="cmd-group">{c.group}</span>
            </button>
          ))}
          {!commands.length ? (
            <div className="cmd-empty">没有匹配「{query}」的命令</div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
