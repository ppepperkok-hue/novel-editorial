import { WarningCircle } from "@phosphor-icons/react";
import { Button } from "../ui/button.jsx";
import { Skeleton } from "../ui/skeleton.jsx";

/** 数据区四态：加载骨架。@stable */
export function LoadingState({ rows = 3, className }) {
  return (
    <div className={className} aria-busy="true" aria-label="加载中">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="mb-2 h-10 w-full" />
      ))}
    </div>
  );
}

/** 数据区四态：空态（带引导文案）。@stable */
export function EmptyState({ title = "暂无数据", hint, className }) {
  return (
    <div className={cnEmpty(className)}>
      <p className="text-sm text-ink-2">{title}</p>
      {hint && <p className="mt-1 text-xs leading-relaxed text-ink-3">{hint}</p>}
    </div>
  );
}

/** 数据区四态：错误态（可重试 + 显式错误码）。@stable */
export function ErrorState({ message = "加载失败", detail, onRetry, className }) {
  return (
    <div className={cnEmpty(className)} role="alert">
      <WarningCircle className="mb-2 size-5 text-bad" />
      <p className="text-sm font-medium text-bad">{message}</p>
      {detail && <p className="mt-1 max-w-md break-words font-mono text-xs text-ink-3">{detail}</p>}
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
          重试
        </Button>
      )}
    </div>
  );
}

function cnEmpty(className) {
  return `flex flex-col items-start justify-center rounded-control border border-dashed border-line px-4 py-8 ${className ?? ""}`;
}
