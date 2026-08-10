const API_BASE =
  location.protocol === "file:" || !location.host ? "http://localhost:8000" : "";

export async function getDashboard() {
  const r = await fetch(API_BASE + "/api/dashboard");
  if (!r.ok) throw new Error("dashboard " + r.status);
  return r.json();
}

export async function getControl() {
  const r = await fetch(API_BASE + "/api/control");
  if (!r.ok) throw new Error("control " + r.status);
  return r.json();
}

export async function postControl(payload) {
  const r = await fetch(API_BASE + "/api/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

export async function getAgents() {
  const r = await fetch(API_BASE + "/api/agents");
  if (!r.ok) throw new Error("agents " + r.status);
  return r.json();
}

export async function postAgents(payload) {
  const r = await fetch(API_BASE + "/api/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

export async function getCost() {
  const r = await fetch(API_BASE + "/api/cost");
  if (!r.ok) throw new Error("cost " + r.status);
  return r.json();
}

export async function getExecutions() {
  const r = await fetch(API_BASE + "/api/executions");
  if (!r.ok) throw new Error("executions " + r.status);
  return r.json();
}

export async function getChapterContent(chapterId) {
  const r = await fetch(API_BASE + "/api/chapter_content?chapter_id=" + chapterId);
  if (!r.ok) throw new Error("chapter_content " + r.status);
  return r.json();
}

export function subscribeEvents(onSnapshot) {
  const es = new EventSource(API_BASE + "/api/events");
  es.onmessage = (e) => {
    try {
      onSnapshot(JSON.parse(e.data));
    } catch {
      // ignore malformed frames
    }
  };
  return es;
}

export async function exportNovels() {
  const r = await fetch(API_BASE + "/api/export/novels");
  if (!r.ok) throw new Error("export " + r.status);
  return r.json();
}

export async function getMeetings() {
  const r = await fetch(API_BASE + "/api/meetings");
  if (!r.ok) throw new Error("meetings " + r.status);
  return r.json();
}

export async function startMeeting(topic) {
  const r = await fetch(API_BASE + "/api/meetings/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic }),
  });
  return r.json();
}

export async function getSession(id) {
  const r = await fetch(API_BASE + "/api/meetings/session?id=" + id);
  if (!r.ok) throw new Error("session " + r.status);
  return r.json();
}

export async function advanceSession(id, instruction) {
  const r = await fetch(API_BASE + "/api/meetings/advance", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: id, instruction }),
  });
  return r.json();
}

export async function getAiTaste(chapterId) {
  const r = await fetch(API_BASE + "/api/ai_taste?chapter_id=" + chapterId);
  if (!r.ok) throw new Error("ai_taste " + r.status);
  return r.json();
}

export async function getEndingStatus() {
  const r = await fetch(API_BASE + "/api/ending/status");
  if (!r.ok) throw new Error("ending " + r.status);
  return r.json();
}

export async function confirmNextBook(novelId) {
  const r = await fetch(API_BASE + "/api/ending/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ novel_id: novelId }),
  });
  return r.json();
}

export async function bindBook(novelId, bookId, volumeId) {
  const r = await fetch(API_BASE + "/api/ending/bind", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ novel_id: novelId, book_id: bookId, volume_id: volumeId }),
  });
  return r.json();
}

export async function getAudit(category) {
  const q = category ? "?category=" + encodeURIComponent(category) : "";
  const r = await fetch(API_BASE + "/api/audit" + q);
  if (!r.ok) throw new Error("audit " + r.status);
  return r.json();
}

export async function refreshHotTopics() {
  const r = await fetch(API_BASE + "/api/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "refresh_hot_topics" }),
  });
  return r.json();
}

export async function getKnowledge() {
  const r = await fetch(API_BASE + "/api/knowledge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "list" }),
  });
  return r.json();
}

export async function readKnowledge(file) {
  const r = await fetch(API_BASE + "/api/knowledge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "read", file }),
  });
  return r.json();
}

export async function saveKnowledge(file, meta, body) {
  const r = await fetch(API_BASE + "/api/knowledge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "save", file, meta, body }),
  });
  return r.json();
}

export async function getKnowledgeDrafts(status) {
  const r = await fetch(API_BASE + "/api/knowledge_drafts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "list", status }),
  });
  return r.json();
}

export async function actOnDraft(id, action) {
  const r = await fetch(API_BASE + "/api/knowledge_drafts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, id }),
  });
  return r.json();
}

export async function distillLessons(meetingId, sessionId) {
  const r = await fetch(API_BASE + "/api/knowledge_drafts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "distill", meeting_id: meetingId, session_id: sessionId }),
  });
  return r.json();
}

export async function getCharacterEvolution(novelId) {
  const r = await fetch(API_BASE + "/api/characters/evolution?novel_id=" + novelId);
  if (!r.ok) throw new Error("evolution " + r.status);
  return r.json();
}

export async function getDiaries(agent, type) {
  const q = new URLSearchParams();
  if (agent) q.set("agent", agent);
  if (type) q.set("type", type);
  const r = await fetch(API_BASE + "/api/diaries?" + q.toString());
  if (!r.ok) throw new Error("diaries " + r.status);
  return r.json();
}

export async function getAgentStates() {
  const r = await fetch(API_BASE + "/api/agent_states");
  if (!r.ok) throw new Error("states " + r.status);
  return r.json();
}

export async function updateDiary(id, content) {
  const r = await fetch(API_BASE + "/api/diaries/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, content }),
  });
  return r.json();
}

export async function updateAgentState(agent, novelId, mood) {
  const r = await fetch(API_BASE + "/api/agent_states/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent, novel_id: novelId, mood }),
  });
  return r.json();
}
