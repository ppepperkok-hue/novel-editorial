import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { NAV_GROUPS } from "../../lib/nav.js";
import { cn } from "../../lib/utils.js";
import { StateDot } from "../features/state-dot.jsx";

/** 五区两级侧边栏。@stable */
export function Sidebar({ schedulerOnline }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [mini, setMini] = useState(false);
  const current = pathname.replace(/^\//, "") || "dashboard";

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-r border-line bg-surface py-3.5 transition-[width] duration-150",
        mini ? "w-[56px] px-2" : "w-[216px] px-2.5",
      )}
    >
      <nav className="min-h-0 flex-1 overflow-y-auto">
        {NAV_GROUPS.map((group) => (
          <div key={group.id} className="mb-4">
            {!mini && (
              <div className="px-2 pb-1.5 text-[10.5px] uppercase tracking-[0.08em] text-ink-3">
                {group.label}
              </div>
            )}
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = current === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => navigate(`/${item.id}`)}
                  title={mini ? item.label : undefined}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "mb-0.5 flex w-full items-center gap-2.5 rounded-[6px] px-2 py-[5px] text-left text-[13px] transition-colors",
                    mini && "justify-center px-0",
                    active
                      ? "bg-accent-soft font-semibold text-accent-ink"
                      : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                  )}
                >
                  <Icon className="size-4 shrink-0" weight={active ? "fill" : "regular"} />
                  {!mini && item.label}
                </button>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="mt-auto flex items-center gap-2 border-t border-line px-2 pt-2.5 text-xs text-ink-2">
        <StateDot tone={schedulerOnline ? "ok" : "bad"} />
        {!mini && <span>{schedulerOnline ? "调度器在线" : "调度器离线"}</span>}
        {mini && (
          <button
            type="button"
            onClick={() => setMini(false)}
            className="ml-auto text-ink-3 hover:text-ink"
            aria-label="展开侧边栏"
          >
            →
          </button>
        )}
        {!mini && (
          <button
            type="button"
            onClick={() => setMini(true)}
            className="ml-auto text-ink-3 hover:text-ink"
            aria-label="收起侧边栏"
          >
            ←
          </button>
        )}
      </div>
    </aside>
  );
}
