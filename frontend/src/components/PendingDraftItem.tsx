import { useCallback, useEffect, useRef, useState } from "react";

import { postDecision, type PendingDraft } from "../api/client";

const CONFIRM_RESET_MS = 3000;

type DecisionAction = "accept" | "reject" | "note";

interface PendingDraftItemProps {
  workspaceId: string;
  workspaceTitle: string;
  draft: PendingDraft;
  onOpenWorkspace: () => void;
  onDecided: () => void;
}

export default function PendingDraftItem({
  workspaceId,
  workspaceTitle,
  draft,
  onOpenWorkspace,
  onDecided,
}: PendingDraftItemProps) {
  const [confirming, setConfirming] = useState<DecisionAction | null>(null);
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const resetTimer = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (resetTimer.current !== null) {
        window.clearTimeout(resetTimer.current);
      }
    };
  }, []);

  const clearConfirm = useCallback(() => {
    if (resetTimer.current !== null) {
      window.clearTimeout(resetTimer.current);
      resetTimer.current = null;
    }
    setConfirming(null);
  }, []);

  const execute = useCallback(
    async (action: DecisionAction) => {
      if (submitting) {
        return;
      }
      setSubmitting(true);
      setError(null);
      try {
        await postDecision(workspaceId, {
          draft_id: draft.id,
          action,
          content: action === "note" ? note.trim() : undefined,
        });
        setNote("");
        setNoteOpen(false);
        onDecided();
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)));
      } finally {
        setSubmitting(false);
        clearConfirm();
      }
    },
    [clearConfirm, draft.id, note, onDecided, submitting, workspaceId],
  );

  const armOrExecute = useCallback(
    (action: DecisionAction) => {
      setError(null);
      if (confirming === action) {
        void execute(action);
        return;
      }
      setConfirming(action);
      if (resetTimer.current !== null) {
        window.clearTimeout(resetTimer.current);
      }
      resetTimer.current = window.setTimeout(() => {
        resetTimer.current = null;
        setConfirming(null);
      }, CONFIRM_RESET_MS);
    },
    [confirming, execute],
  );

  const toggleNote = useCallback(() => {
    setError(null);
    clearConfirm();
    setNoteOpen((open) => !open);
  }, [clearConfirm]);

  return (
    <li className="pending-item" data-testid="pending-item">
      <button
        type="button"
        className="pending-item-open"
        onClick={onOpenWorkspace}
        aria-label={`打开作品：${workspaceTitle}`}
      >
        <span className="pending-item-title">{draft.title}</span>
        <span className="pending-item-workspace">{workspaceTitle}</span>
        <span className="pending-item-meta">
          v{draft.current_version} · {draft.status}
        </span>
      </button>
      <div className="pending-actions">
        <button
          type="button"
          className={`pending-action pending-action--accept${
            confirming === "accept" ? " pending-action--confirm" : ""
          }`}
          onClick={() => armOrExecute("accept")}
          disabled={submitting}
        >
          {confirming === "accept" ? "确认接受？" : "接受"}
        </button>
        <button
          type="button"
          className={`pending-action pending-action--reject${
            confirming === "reject" ? " pending-action--confirm" : ""
          }`}
          onClick={() => armOrExecute("reject")}
          disabled={submitting}
        >
          {confirming === "reject" ? "确认拒绝？" : "拒绝"}
        </button>
        <button
          type="button"
          className="pending-action pending-action--note"
          onClick={toggleNote}
          disabled={submitting}
          aria-expanded={noteOpen}
        >
          指示
        </button>
      </div>
      {noteOpen ? (
        <div className="pending-note">
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="给编辑部的指示"
            aria-label="拍板指示内容"
            disabled={submitting}
          />
          <button
            type="button"
            className={`pending-action pending-action--note-submit${
              confirming === "note" ? " pending-action--confirm" : ""
            }`}
            onClick={() => armOrExecute("note")}
            disabled={!note.trim() || submitting}
          >
            {confirming === "note" ? "确认提交？" : "提交指示"}
          </button>
        </div>
      ) : null}
      {error ? (
        <p className="pending-error" role="alert" data-testid="pending-error">
          操作失败：{error.message}
        </p>
      ) : null}
    </li>
  );
}
