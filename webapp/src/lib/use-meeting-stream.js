import { useEffect, useRef, useState } from "react";
import { API_BASE, getMeetingMessages, getSession } from "../api.js";

/**
 * 自由会议实时流：SSE 事件 + 初始全量消息拉取。
 * EventSource 断线自动重连；重连后依赖消息表为真相（SSE 只做增量）。
 * @stable
 */
export function useMeetingStream(sessionId) {
  const [messages, setMessages] = useState([]);
  const [thinking, setThinking] = useState({});
  const [approvals, setApprovals] = useState([]);
  const [error, setError] = useState("");
  const [summary, setSummary] = useState("");
  const [compressing, setCompressing] = useState(false);
  const aliveRef = useRef(true);

  const loadAll = () => {
    return getMeetingMessages(sessionId)
      .then((r) => {
        if (!aliveRef.current) return;
        const fresh = r.messages || [];
        setMessages((prev) => {
          const byId = new Map(fresh.map((m) => [Number(m.id), m]));
          for (const m of prev) {
            if (!byId.has(Number(m.id))) byId.set(Number(m.id), m);
          }
          return [...byId.values()].sort((a, b) => Number(a.id) - Number(b.id));
        });
      })
      .catch(() => {
        if (aliveRef.current) setError("消息加载失败，请刷新页面");
      });
  };

  useEffect(() => {
    if (!sessionId) return undefined;
    aliveRef.current = true;
    setMessages([]);
    setThinking({});
    setApprovals([]);
    setError("");

    loadAll();
    getSession(sessionId)
      .then((r) => {
        if (aliveRef.current) setSummary(r.meeting_summary || "");
      })
      .catch(() => {});

    const es = new EventSource(`${API_BASE}/api/meetings/events?session_id=${sessionId}`);
    es.onmessage = (e) => {
      if (!aliveRef.current) return;
      try {
        const ev = JSON.parse(e.data);
        if (ev.type === "message") {
          setMessages((prev) => {
            if (prev.some((m) => Number(m.id) === Number(ev.message_id))) return prev;
            return [
              ...prev,
              {
                id: ev.message_id,
                session_id: ev.session_id,
                from_agent: ev.agent,
                role: "assistant",
                kind: "speech",
                body: ev.speech,
                status: "active",
                created_at: "",
              },
            ];
          });
        } else if (ev.type === "status") {
          setThinking((prev) => ({ ...prev, [ev.agent]: ev.status === "thinking" }));
        } else if (ev.type === "approval") {
          setApprovals((prev) => [
            ...prev.filter((a) => Number(a.id) !== Number(ev.interaction.id)),
            ev.interaction,
          ]);
        } else if (ev.type === "compress") {
          setCompressing(ev.status === "compressing");
          if (ev.status === "done") {
            getSession(sessionId)
              .then((r) => aliveRef.current && setSummary(r.meeting_summary || ""))
              .catch(() => {});
          }
        }
      } catch {
        /* 忽略无法解析的事件 */
      }
    };
    es.onerror = () => {
      if (aliveRef.current) setError("实时连接中断，正在重连…");
    };
    es.onopen = () => {
      // EventSource 自动重连成功：拉全量合并，补上断线期间可能丢失的事件。
      if (aliveRef.current) {
        setError("");
        loadAll();
      }
    };
    return () => {
      aliveRef.current = false;
      es.close();
    };
  }, [sessionId]);

  const removeApproval = (interactionId) =>
    setApprovals((prev) => prev.filter((a) => Number(a.id) !== Number(interactionId)));

  return { messages, thinking, approvals, error, removeApproval, summary, compressing };
}
