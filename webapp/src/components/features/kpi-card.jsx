import { cn } from "../../lib/utils.js";

const valueTone = {
  ok: "text-ok",
  warn: "text-warn",
  bad: "text-bad",
  accent: "text-accent-ink",
};

/** 轻量指标块（无卡片容器，靠留白与分割线）。@stable */
export function KpiCard({ label, value, sub, tone, className, ...props }) {
  return (
    <div className={cn("min-w-0", className)} {...props}>
      <div className="text-[11.5px] text-ink-2">{label}</div>
      <div
        className={cn(
          "mt-0.5 text-[22px] font-bold leading-tight tracking-[-0.02em] text-ink",
          tone && valueTone[tone],
        )}
      >
        {value}
      </div>
      {sub && <div className="mt-0.5 text-[11.5px] text-ink-3">{sub}</div>}
    </div>
  );
}
