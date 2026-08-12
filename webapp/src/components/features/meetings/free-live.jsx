import { useMemo, useRef, useState } from "react";
import { PaperPlaneTilt } from "@phosphor-icons/react";
import { toast } from "sonner";
import { advanceSession, cancelMeeting, respondInteraction } from "../../../api.js";
import { AgentAvatar } from "../agent-avatar.jsx";
import { Badge } from "../../ui/badge.jsx";
import { Button } from "../../ui/button.jsx";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../../ui/dialog.jsx";
import { Input } from "../../ui/input.jsx";
import { displayNameOf } from "../../../lib/agent-custom.js";
import { useMeetingStream } from "../../../lib/use-meeting-stream.js";
import { cn } from "../../../lib/utils.js";

/**
 * 自由会议直播：实时消息流 + @插入 + 审批弹窗 + 思考状态。
 * @stable
 */
export function FreeLive({ session, onEnded }) {
  const { messages, thinking, approvals, error, removeApproval, summary, compressing } =
    useMeetingStream(session.id);
  const [text, setText] = useState("");
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);

  const attendees = session.attendees || [];
  const mentionCandidates = useMemo(() => {
    const q = mentionQuery.trim().toLowerCase();
    return attendees.filter((a) =>
      displayNameOf({ file: `${a}.md`, name: a }).toLowerCase().includes(q),
    );
  }, [attendees, mentionQuery]);

  const handleChange = (value) => {
    setText(value);
    const at = value.lastIndexOf("@");
    if (at !== -1 && !value.slice(at + 1).includes(" ")) {
      setMentionOpen(true);
      setMentionQuery(value.slice(at + 1));
    } else {
      setMentionOpen(false);
    }
  };

  const insertMention = (agent) => {
    const at = text.lastIndexOf("@");
    const name = displayNameOf({ file: `${agent}.md`, name: agent });
    setText(`${text.slice(0, at)}@${name} `);
    setMentionOpen(false);
    inputRef.current?.focus();
  };

  const send = async () => {
    const content = text.trim();
    if (!content || busy) return;
    setBusy(true);
    try {
      const r = await advanceSession(session.id, content);
      if (r.ok) {
        setText("");
      } else {
        toast.error(r.error || "发送失败");
      }
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    setBusy(true);
    try {
      const r = await advanceSession(session.id, "", true);
      if (r.ok) {
        toast.success("会议已结束");
        onEnded?.();
      } else {
        toast.error(r.error || "结束失败");
      }
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    setBusy(true);
    try {
      const r = await cancelMeeting(session.id);
      if (r.ok) {
        onEnded?.();
      } else {
        toast.error(r.error || "取消失败");
      }
    } finally {
      setBusy(false);
    }
  };

  const activeApproval = approvals[0] || null;

  return (
    <section className="overflow-hidden rounded-card border border-line bg-surface">
      <div className="flex flex-wrap items-center gap-2.5 border-b border-line px-5 py-3.5">
        <span className="text-sm font-bold text-ink">
          自由讨论 · {session.topic}
        </span>
        <Badge tone="accent">实时</Badge>
        {Object.entries(thinking).filter(([, v]) => v).map(([agent]) => (
          <span key={agent} className="flex items-center gap-1.5 text-xs text-ink-2">
            <AgentAvatar file={`${agent}.md`} name={agent} size="sm" className="animate-pulse" />
            {displayNameOf({ file: `${agent}.md`, name: agent })} 正在思考…
          </span>
        ))}
        {error ? <Badge tone="warn">{error}</Badge> : null}
        <div className="ml-auto flex gap-2">
          <Button variant="ghost" size="sm" disabled={busy} onClick={cancel}>
            取消
          </Button>
          <Button size="sm" disabled={busy} onClick={finish}>
            结束并总结
          </Button>
        </div>
      </div>

      <div className="max-h-[480px] overflow-y-auto bg-surface-2/60 px-5 py-4">
        {summary ? (
          <div className="mb-4 rounded-md border border-accent/40 bg-accent-soft/50 p-2.5">
            <div className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-accent-ink">
              会议摘要锚点
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ink-2">{summary}</p>
          </div>
        ) : null}
        {compressing ? (
          <div className="mb-4 flex items-center gap-2 rounded-md border border-line bg-surface p-2 text-xs text-ink-2">
            <span className="size-1.5 animate-pulse rounded-full bg-accent" />
            正在压缩长历史，稍后继续…
          </div>
        ) : null}
        {messages.length ? (
          messages.map((m) => (
            <div key={m.id} className="mb-4 flex gap-2.5">
              <AgentAvatar file={`${m.from_agent}.md`} name={m.from_agent} />
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex items-baseline gap-2">
                  <span className="text-[13px] font-semibold text-ink">
                    {displayNameOf({ file: `${m.from_agent}.md`, name: m.from_agent })}
                  </span>
                  <span className="font-mono text-[10.5px] text-ink-3">{m.created_at}</span>
                </div>
                <div className="rounded-md border border-line bg-surface p-2.5">
                  <p className="whitespace-pre-wrap text-xs leading-relaxed text-ink-2">{m.body}</p>
                </div>
              </div>
            </div>
          ))
        ) : (
          <p className="py-8 text-center text-xs text-ink-3">
            会议已开始，编辑们正在进入状态…
          </p>
        )}
      </div>

      <div className="relative flex items-center gap-2.5 border-t border-line px-5 py-3.5">
        <Input
          ref={inputRef}
          className="h-9 min-w-[180px] flex-1 text-[13px]"
          placeholder="发言或 @某位编辑…"
          value={text}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
        />
        <Button disabled={busy || !text.trim()} onClick={send}>
          <PaperPlaneTilt className="size-3.5" />
          发送
        </Button>
        {mentionOpen && mentionCandidates.length ? (
          <div className="absolute bottom-full left-5 mb-1 w-52 overflow-hidden rounded-control border border-line bg-surface shadow-pop">
            {mentionCandidates.map((agent) => (
              <button
                key={agent}
                type="button"
                onClick={() => insertMention(agent)}
                className={cn(
                  "flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-ink-2",
                  "hover:bg-surface-2 hover:text-ink",
                )}
              >
                <AgentAvatar file={`${agent}.md`} name={agent} size="sm" />
                {displayNameOf({ file: `${agent}.md`, name: agent })}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <Dialog open={Boolean(activeApproval)} onOpenChange={(v) => !v && removeApproval(activeApproval?.id)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-sm font-bold text-ink">需要您决定</DialogTitle>
          </DialogHeader>
          {activeApproval ? (
            <div>
              <p className="text-sm leading-relaxed text-ink">
                {displayNameOf({ file: `${activeApproval.agent}.md`, name: activeApproval.agent })}
                ：{activeApproval.question}
              </p>
              {activeApproval.expires_at ? (
                <p className="mt-1 text-[11px] text-ink-3">
                  过期时间：{activeApproval.expires_at}
                </p>
              ) : null}
              <DialogFooter>
                {(activeApproval.choices || ["同意", "拒绝"]).map((choice) => (
                  <Button
                    key={choice}
                    variant={choice === "拒绝" ? "danger" : "default"}
                    onClick={async () => {
                      const r = await respondInteraction(activeApproval.id, choice);
                      if (r.ok) removeApproval(activeApproval.id);
                      else toast.error(r.error || "响应失败");
                    }}
                  >
                    {choice}
                  </Button>
                ))}
              </DialogFooter>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </section>
  );
}
