import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import type { TalkMessage } from "../../api/client";
import EventStreamStatus from "../../components/EventStreamStatus";
import {
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "../../components/StateViews";
import { useEventStream } from "../../hooks/useEventStream";
import { useWorkspaceSelection } from "../../hooks/useWorkspaceSelection";
import { formatDateTime } from "../../utils/format";
import { useSendTalk, useTalk } from "./useTalkQueries";

const ROLE_LABELS: Record<string, string> = {
  author: "作者",
  agent: "伙伴",
  system: "系统",
};

function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

type MarkKind =
  | "disagreement"
  | "discussion"
  | "collaboration"
  | "proactive"
  | "other";

function markKind(mark: string): MarkKind {
  if (mark.includes("分歧")) {
    return "disagreement";
  }
  if (mark.includes("讨论")) {
    return "discussion";
  }
  if (mark.includes("互委")) {
    return "collaboration";
  }
  if (mark.includes("主动")) {
    return "proactive";
  }
  return "other";
}

function TalkItem({ message }: { message: TalkMessage }) {
  const roleClass = ROLE_LABELS[message.role] !== undefined ? `--${message.role}` : "";
  return (
    <li
      className={`talk-item${roleClass}`}
      data-testid="talk-item"
      data-role={message.role}
    >
      <div className="talk-item-head">
        <span className="talk-actor">{message.actor}</span>
        <span className="talk-role">{roleLabel(message.role)}</span>
        {message.mark ? (
          <span
            className={`talk-mark talk-mark--${markKind(message.mark)}`}
            data-testid="talk-mark"
          >
            {message.mark}
          </span>
        ) : null}
        <span className="talk-time">{formatDateTime(message.created_at)}</span>
      </div>
      <p className="talk-content">{message.content}</p>
    </li>
  );
}

export default function TalkPage() {
  const { workspaceId } = useParams();
  useWorkspaceSelection(workspaceId);
  const talk = useTalk(workspaceId);
  const stream = useEventStream(workspaceId);
  const sendTalkMutation = useSendTalk(workspaceId);
  const [message, setMessage] = useState("");

  const canSend = message.trim().length > 0 && !sendTalkMutation.isPending;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = message.trim();
    if (!content || sendTalkMutation.isPending) {
      return;
    }
    sendTalkMutation.mutate(
      { message: content },
      {
        onSuccess: () => setMessage(""),
      },
    );
  }

  return (
    <section className="talk-page" data-testid="talk-page">
      <header className="page-header">
        <h2>对话</h2>
        <div className="workspace-toolbar">
          <EventStreamStatus status={stream.status} notice={stream.notice} />
          <Link className="text-link" to={`/works/${workspaceId ?? ""}`}>
            返回作品
          </Link>
        </div>
      </header>
      <section className="panel talk-panel" data-testid="talk-panel">
        <header className="panel-header">
          <h3>编辑部对话</h3>
        </header>
        <div className="panel-body">
          {talk.isPending ? <SkeletonRows count={4} /> : null}
          {talk.isError ? (
            <ErrorState
              source={`/works/${workspaceId ?? ""}/talk`}
              message={talk.error.message}
              onRetry={() => void talk.refetch()}
            />
          ) : null}
          {talk.isSuccess && talk.data.length === 0 ? (
            <EmptyState
              title="还没有对话"
              hint="给编辑部发第一句话，对话会从这里展开"
            />
          ) : null}
          {talk.isSuccess && talk.data.length > 0 ? (
            <ul className="talk-list" data-testid="talk-list">
              {talk.data.map((item) => (
                <TalkItem key={item.id} message={item} />
              ))}
            </ul>
          ) : null}
        </div>
      </section>
      <form className="talk-form" onSubmit={handleSubmit}>
        <label className="form-label" htmlFor="talk-message-input">
          发一句话给编辑部
        </label>
        <textarea
          id="talk-message-input"
          className="talk-input"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="例如：@写手 第一章的结尾再磨一磨"
          data-testid="talk-message-input"
        />
        {sendTalkMutation.isError ? (
          <p className="inline-error" data-testid="talk-send-error">
            {sendTalkMutation.error.message}
          </p>
        ) : null}
        <button
          type="submit"
          className="primary-button"
          disabled={!canSend}
          data-testid="talk-send-button"
        >
          {sendTalkMutation.isPending ? "发送中…" : "发送"}
        </button>
      </form>
    </section>
  );
}
