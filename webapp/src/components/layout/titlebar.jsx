import { useEffect, useState } from "react";
import { MoonStars, Sun } from "@phosphor-icons/react";

/** Electron 窗口控制条；web 环境自动降级为纯展示。@stable */
export const desktopApi =
  typeof window !== "undefined" ? window.desktopApi || null : null;

export function TitleBar({ theme, onToggleTheme }) {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    desktopApi?.isMaximized?.().then(setMaximized).catch(() => {});
  }, []);

  const win = (action) => () => {
    if (action === "minimize") desktopApi?.minimize?.();
    if (action === "maximize") {
      desktopApi?.maximize?.();
      desktopApi?.isMaximized?.().then(setMaximized).catch(() => {});
    }
    if (action === "close") desktopApi?.close?.();
  };

  return (
    <header className="flex h-10 shrink-0 items-center justify-between border-b border-line bg-surface px-3.5 pl-4 select-none">
      <div className="flex items-center gap-2.5">
        <span className="grid size-[22px] place-items-center rounded-[6px] bg-ink text-[12px] font-bold text-canvas">
          笔
        </span>
        <span className="text-[13px] font-semibold tracking-[0.01em] text-ink">文学编辑部</span>
        <span className="font-mono text-[11px] text-ink-3">Novel Editorial Console</span>
      </div>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onToggleTheme}
          aria-label="切换主题"
          className="grid size-7 place-items-center rounded-[5px] text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
        >
          {theme === "dark" ? <Sun className="size-3.5" /> : <MoonStars className="size-3.5" />}
        </button>
        <button
          type="button"
          onClick={win("minimize")}
          aria-label="最小化"
          className="grid size-7 place-items-center rounded-[5px] text-[13px] text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
        >
          ─
        </button>
        <button
          type="button"
          onClick={win("maximize")}
          aria-label={maximized ? "还原" : "最大化"}
          className="grid size-7 place-items-center rounded-[5px] text-[13px] text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
        >
          {maximized ? "❐" : "□"}
        </button>
        <button
          type="button"
          onClick={win("close")}
          aria-label="关闭"
          className="grid size-7 place-items-center rounded-[5px] text-[13px] text-ink-2 transition-colors hover:bg-bad hover:text-white"
        >
          ✕
        </button>
      </div>
    </header>
  );
}
