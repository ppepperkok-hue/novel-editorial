import { cn } from "../../lib/utils.js";

/** 分割线分组的页面区块（不套卡片容器）。@stable */
export function SectionBlock({ title, action, className, children, ...props }) {
  return (
    <section className={cn("min-w-0", className)} {...props}>
      {(title || action) && (
        <div className="mb-3 flex items-baseline justify-between">
          {title && <h2 className="text-xs font-semibold tracking-[0.02em] text-ink">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

/** 区块头部的文字链接动作。 */
export function BlockLink({ className, ...props }) {
  return (
    <button
      type="button"
      className={cn("bg-transparent p-0 text-xs text-accent-ink hover:underline", className)}
      {...props}
    />
  );
}
