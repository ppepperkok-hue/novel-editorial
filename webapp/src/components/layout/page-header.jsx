import { cn } from "../../lib/utils.js";

/** 页面头：标题 + 描述 + 右侧操作。@stable */
export function PageHeader({ title, desc, actions, className }) {
  return (
    <div className={cn("mb-6 flex items-end justify-between", className)}>
      <div>
        <h1 className="text-[22px] font-bold tracking-[-0.015em] text-ink">{title}</h1>
        {desc && <p className="mt-1 text-[13px] text-ink-2">{desc}</p>}
      </div>
      {actions && <div className="flex items-center gap-3 text-xs text-ink-2">{actions}</div>}
    </div>
  );
}
