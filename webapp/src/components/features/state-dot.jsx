import { cn } from "../../lib/utils.js";

const dotTone = {
  ok: "bg-ok",
  warn: "bg-warn",
  bad: "bg-bad",
  idle: "bg-ink-3",
  accent: "bg-accent",
};

/** 语义状态圆点。@stable */
export function StateDot({ tone = "ok", className, ...props }) {
  return (
    <span
      aria-hidden="true"
      className={cn("inline-block size-2 rounded-pill", dotTone[tone], className)}
      {...props}
    />
  );
}
