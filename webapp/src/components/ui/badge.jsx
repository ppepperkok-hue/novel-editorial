import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils.js";

export const badgeVariants = cva(
  "inline-flex h-5 items-center rounded-pill px-2 text-[10.5px] font-semibold uppercase tracking-[0.05em] whitespace-nowrap",
  {
    variants: {
      tone: {
        neutral: "bg-surface-2 text-ink-2 border border-line",
        ok: "bg-ok-soft text-ok",
        warn: "bg-warn-soft text-warn",
        bad: "bg-bad-soft text-bad",
        accent: "bg-accent-soft text-accent-ink",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({ className, tone, ...props }) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
