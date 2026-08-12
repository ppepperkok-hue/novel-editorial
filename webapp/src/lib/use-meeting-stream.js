import { useEffect, useRef, useState } from "react";
import { API_BASE, getMeetingMessages } from "../api.js";

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
  const aliveRef = useRef(true);

  useEffect(() => {
    if (!sessionId) return undefined;
    aliveRef.current = true;
    setMessages([]);
    setThinking({});
    setApprovals([]);
    setError("");

    getMeetingMessages(sessionId)
      .then((r) => {
        if (aliveRef.current) setMessages(r.messages || []);
      })
      .catch(() => {
        if (aliveRef.current) setError("消息加载失败，请刷新页面");
      });

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
        }
      } catch {
        /* 忽略无法解析的事件 */
      }
    };
    es.onerror = () => {
      if (aliveRef.current) setError("实时连接中断，正在重连…");
    };
    return () => {
      aliveRef.current = false;
      es.close();
    };
  }, [sessionId]);

  const removeApproval = (interactionId) =>
    setApprovals((prev) => prev.filter((a) => Number(a.id) !== Number(interactionId)));

  return { messages, thinking, approvals, error, removeApproval };
}
