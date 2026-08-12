import { Minus, Play, Plus } from "@phosphor-icons/react";
import { useState } from "react";
import { toast } from "sonner";
import { postControl } from "../../../api.js";
import { cn } from "../../../lib/utils.js";
import { Button } from "../../ui/button.jsx";
import { Input } from "../../ui/input.jsx";

const MODES = [
  { id: "write", label: "写稿" },
  { id: "org", label: "整理日" },
  { id: "meeting", label: "开会日" },
  { id: "free", label: "自由安排" },
];

/** 开工指令行：模式分段 + 章数步进 + 老板指令 + 开工按钮。@stable */
export function OpenWorkday({ workday, onChanged }) {
  const [mode, setMode] = useState("write");
  const [chapters, setChapters] = useState(2);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);

  const awaitingClose = workday?.phase === "awaiting_close";
  const working = workday?.phase && !["completed", "completed_with_pending", "partial", "failed"].includes(workday.status || "");

  const run = async (payload, okText) => {
    setBusy(true);
    try {
      const r = await postControl(payload);
      if (r.ok) {
        toast.success(okText);
        onChanged?.();
      } else {
        toast.error(`失败：${r.error || "未知"}`);
      }
    } finally {
      setBusy(false);
    }
  };

  const openWorkday = () =>
    run(
      {
        action: "run_now",
        mode,
        chapters: mode === "write" ? chapters : undefined,
        boss_instruction: instruction || undefined,
      },
      `编辑部已开工（${MODES.find((m) => m.id === mode)?.label}）`,
    );

  const closeWorkday = () => run({ action: "close_workday", run_id: workday.run_id }, "收工流程已启动");
  const resumeWorkday = () => run({ action: "resume_workday", run_id: workday.run_id }, "继续补跑已启动");
  const weekly = () => run({ action: "run_now", workflow: "weekly" }, "周会已启动");

  return (
    <section className="min-w-0">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-xs font-semibold tracking-[0.02em] text-ink">编辑部开工</h2>
        <a href="#/flow" className="text-xs text-accent-ink hover:underline">
          查看运行链路
        </a>
      </div>

      {awaitingClose ? (
        <div className="flex items-center gap-3 border-t border-line py-4">
          <span className="text-sm text-ink-2">主产出已完成，接下来：</span>
          <Button variant="default" size="sm" disabled={busy} onClick={closeWorkday}>
            收工
          </Button>
          <Button variant="outline" size="sm" disabled={busy} onClick={weekly}>
            开会（周会）
          </Button>
          <Button variant="outline" size="sm" disabled={busy} onClick={resumeWorkday}>
            继续补跑
          </Button>
        </div>
      ) : working ? (
        <div className="flex items-center gap-3 border-t border-line py-4">
          <span className="status-dot size-2 animate-pulse rounded-full bg-accent" />
          <span className="text-sm text-ink">编辑部正在工作中</span>
          <span className="text-xs text-ink-3">主产出结束后会回到这里等您决策</span>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3 border-t border-line py-4">
          <div className="inline-flex overflow-hidden rounded-control border border-line bg-surface">
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setMode(m.id)}
                className={cn(
                  "h-9 border-r border-line px-3.5 text-[13px] transition-colors last:border-r-0",
                  mode === m.id
                    ? "bg-ink font-semibold text-canvas"
                    : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
          {mode === "write" && (
            <div className="inline-flex h-9 items-center rounded-control border border-line bg-surface">
              <button
                type="button"
                aria-label="减少章数"
                onClick={() => setChapters((v) => Math.max(1, v - 1))}
                className="grid size-8 place-items-center text-ink-2 hover:bg-surface-2 hover:text-ink"
              >
                <Minus className="size-3.5" weight="bold" />
              </button>
              <span className="min-w-[34px] text-center text-sm font-semibold tabular-nums text-ink">
                {chapters}
              </span>
              <span className="mr-1.5 text-[11px] text-ink-3">章</span>
              <button
                type="button"
                aria-label="增加章数"
                onClick={() => setChapters((v) => Math.min(8, v + 1))}
                className="grid size-8 place-items-center text-ink-2 hover:bg-surface-2 hover:text-ink"
              >
                <Plus className="size-3.5" weight="bold" />
              </button>
            </div>
          )}
          <Input
            className="h-9 min-w-[150px] flex-1 text-[13px]"
            placeholder="老板指令（可选），如：今天赶两章"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
          />
          <Button disabled={busy} onClick={openWorkday}>
            <Play weight="fill" className="size-3.5" />
            开工
          </Button>
        </div>
      )}
      <p className="text-[11.5px] text-ink-3">开工即上班：晨会 → 主产出 → 决策点（收工 / 开会 / 继续）</p>
    </section>
  );
}
