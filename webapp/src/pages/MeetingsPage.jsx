import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  advanceSession,
  cancelMeeting,
  getActiveSession,
  getMeetings,
  getSession,
  startMeeting,
} from "../api.js";
import { AgentAvatar } from "../components/features/agent-avatar.jsx";
import { EmptyState, ErrorState, LoadingState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { Badge } from "../components/ui/badge.jsx";
import { Button } from "../components/ui/button.jsx";
import { Input } from "../components/ui/input.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select.jsx";
import { displayNameOf } from "../lib/agent-custom.js";
import { useApi } from "../lib/use-api.js";

const AGENT_NAMES = {
  planner: "文策",
  guard: "守界",
  writer: "墨白",
  editor: "润物",
  reviewer: "守正",
  reader: "阿读",
  memory: "录事",
  work_meta: "书案",
  eic: "掌印",
  ending_judge: "终局",
  knowledge_keeper: "博闻",
};

const KIND_LABELS = {
  weekly: "编辑部例会",
  topic: "剧情碰头会",
  planning: "选题会",
  critique: "单章会诊",
  retro: "数据复盘会",
  review: "收尾会",
  incident: "危机处理会",
  learning: "知识分享会",
  free: "茶水间闲聊",
};

const agentName = (id) => displayNameOf({ file: `${id}.md`, name: AGENT_NAMES[id] || id });

function speechText(raw) {
  if (typeof raw !== "string") return "";
  try {
    const obj = JSON.parse(raw);
    if (obj && typeof obj === "object") {
      return obj.speech || obj.opinion || obj.weekly_summary || JSON.stringify(obj, null, 2);
    }
  } catch {
    /* keep raw */
  }
  return raw;
}

function statusMeta(status, round) {
  if (status === "running") return { text: `第 ${round || 1} 轮讨论中`, tone: "accent" };
  if (status === "awaiting_input") return { text: "等待您的指示", tone: "warn" };
  if (status === "finished") return { text: "已完成", tone: "ok" };
  return { text: "失败", tone: "bad" };
}

/** 会议中心：发起、直播围观、历史纪要。@stable */
export default function MeetingsPage() {
  const { data: meetingsData, error, loading, refresh } = useApi(getMeetings, { interval: 30000 });
  const [session, setSession] = useState(null);
  const [topic, setTopic] = useState("");
  const [kind, setKind] = useState("topic");
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [pollTick, setPollTick] = useState(0);

  useEffect(() => {
    getActiveSession()
      .then((r) => r?.session && setSession(r.session))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!session?.id) return;
    let alive = true;
    let timer = null;
    const load = async () => {
      try {
        const s = await getSession(session.id);
        if (!alive) return;
        setSession((prev) =>
          prev && prev.id === s.id && JSON.stringify(prev) === JSON.stringify(s) ? prev : s,
        );
        if (s.status === "finished" || s.status === "failed") {
          clearInterval(timer);
          refresh();
        }
      } catch {
        /* keep polling */
      }
    };
    load();
    timer = setInterval(load, 2500);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [pollTick, session?.id]);

  const start = async () => {
    if (!topic.trim() || busy) return;
    setBusy(true);
    try {
      const r = await startMeeting(topic.trim(), kind);
      if (r.ok) {
        setSession({ id: r.session_id, topic: topic.trim(), status: "running", kind });
        setTopic("");
        toast.success("会议已启动");
      } else {
        toast.error(r.error || "启动失败");
      }
    } finally {
      setBusy(false);
    }
  };

  const advance = async (finish) => {
    if (!session || busy) return;
    setBusy(true);
    try {
      const r = await advanceSession(session.id, finish ? "" : instruction, finish);
      if (r.ok) {
        setInstruction("");
        setPollTick((t) => t + 1);
        if (finish) toast.success("会议已结束");
      } else {
        toast.error(r.error || "推进失败");
      }
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!session || busy) return;
    setBusy(true);
    try {
      const r = await cancelMeeting(session.id);
      if (r.ok) {
        setSession(null);
        refresh();
      } else {
        toast.error(r.error || "取消失败");
      }
    } finally {
      setBusy(false);
    }
  };

  const meta = session ? statusMeta(session.status, session.current_round) : null;
  const meetings = meetingsData?.meetings || [];

  return (
    <>
      <PageHeader title="会议中心" desc="发起专题会议、围观讨论、查看纪要" />

      {!session ? (
        <section className="rounded-card border border-line bg-surface px-5 py-4">
          <h2 className="text-xs font-semibold tracking-[0.02em] text-ink">发起会议</h2>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Input
              className="h-9 min-w-[220px] flex-1 text-[13px]"
              placeholder="会议主题，如：讨论下一卷的剧情走向"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && start()}
            />
            <Select value={kind} onValueChange={setKind}>
              <SelectTrigger className="h-9 w-[150px]">
                <SelectValue placeholder="会议类型" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(KIND_LABELS).map(([k, label]) => (
                  <SelectItem key={k} value={k}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button disabled={busy || !topic.trim()} onClick={start}>
              {busy ? "启动中…" : "发起"}
            </Button>
          </div>
        </section>
      ) : (
        <section className="rounded-card border border-line bg-surface">
          <div className="flex flex-wrap items-center gap-2.5 border-b border-line px-5 py-3.5">
            <span className="text-sm font-bold text-ink">
              会议直播 · {session.topic || KIND_LABELS[session.kind] || "专题会议"}
            </span>
            <Badge tone={meta.tone}>{meta.text}</Badge>
            {session.status === "running" && session.current_agent ? (
              <span className="flex items-center gap-1.5 text-xs text-ink-2">
                <span className="size-1.5 animate-pulse rounded-full bg-accent" />
                {agentName(session.current_agent)} 正在思考…
              </span>
            ) : null}
            <span className="text-xs text-ink-3">
              参会：{(session.attendees || []).map(agentName).join("、") || "—"}
            </span>
            <Button variant="ghost" size="sm" className="ml-auto" onClick={cancel} disabled={busy}>
              取消会议
            </Button>
          </div>

          <div className="max-h-[420px] overflow-y-auto bg-surface-2 px-5 py-4">
            {(session.transcript || []).length ? (
              session.transcript.map((m, i) => (
                <div key={i} className="mb-4 flex gap-2.5">
                  <AgentAvatar file={`${m.agent}.md`} name={m.agent} />
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex items-baseline gap-2">
                      <span className="text-[13px] font-semibold text-ink">{agentName(m.agent)}</span>
                      <span className="font-mono text-[10.5px] text-ink-3">
                        第 {m.round || session.current_round || 1} 轮 · {m.created_at || ""}
                      </span>
                    </div>
                    <p className="whitespace-pre-wrap rounded-md border border-line bg-surface p-2.5 text-xs leading-relaxed text-ink-2">
                      {speechText(m.speech ?? m.raw ?? "")}
                    </p>
                  </div>
                </div>
              ))
            ) : (
              <EmptyState title="讨论还没开始" hint="Agent 们正在准备发言，稍等片刻。" />
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2.5 border-t border-line px-5 py-3.5">
            <Input
              className="h-9 min-w-[200px] flex-1 text-[13px]"
              placeholder="插入您的指示，如：让守正先回应墨白的提案"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && advance(false)}
            />
            <Button variant="outline" size="sm" disabled={busy} onClick={() => advance(false)}>
              推进下一轮
            </Button>
            <Button size="sm" disabled={busy} onClick={() => advance(true)}>
              结束会议
            </Button>
          </div>
        </section>
      )}

      <section className="mt-7 min-w-0">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-xs font-semibold tracking-[0.02em] text-ink">最近会议</h2>
          <span className="text-xs text-ink-3">{meetings.length} 次</span>
        </div>
        {error ? (
          <ErrorState message="纪要加载失败" detail={error} onRetry={refresh} />
        ) : loading ? (
          <LoadingState rows={3} />
        ) : meetings.length ? (
          meetings.slice(0, 8).map((m) => (
            <div key={m.id} className="border-t border-line py-3.5 first:border-t-0">
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="text-[13.5px] font-semibold text-ink">#{m.id}</span>
                <span className="text-xs text-ink-2">
                  {m.held_at} · {(m.attendees || []).length} 人参会
                </span>
                <Badge tone={m.status === "finished" || m.status === "completed" ? "ok" : "neutral"}>
                  {m.status || "completed"}
                </Badge>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-ink-3">{m.summary}</p>
            </div>
          ))
        ) : (
          <EmptyState title="还没有会议记录" hint="发起第一场会，让编辑们开始讨论吧。" />
        )}
      </section>
    </>
  );
}
