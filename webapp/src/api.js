const API_BASE =
  location.protocol === "file:" || !location.host ? "http://localhost:8000" : "";

async function getJSON(path) {
  const r = await fetch(API_BASE + path);
  if (!r.ok) throw new Error(path.split("?")[0] + " " + r.status);
  return r.json();
}

async function postJSON(path, body) {
  const r = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  return r.json();
}

export const getDashboard = () => getJSON("/api/dashboard");
export const getControl = () => getJSON("/api/control");
export const postControl = (payload) => postJSON("/api/control", payload);
export const getAgents = () => getJSON("/api/agents");
export const postAgents = (payload) => postJSON("/api/agents", payload);
export const getCost = () => getJSON("/api/cost");
export const getExecutions = () => getJSON("/api/executions");
export const getChapterContent = (chapterId) =>
  getJSON("/api/chapter_content?chapter_id=" + chapterId);

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

export const exportNovels = () => getJSON("/api/export/novels");
export const getMeetings = () => getJSON("/api/meetings");
export const startMeeting = (topic) => postJSON("/api/meetings/start", { topic });
export const getSession = (id) => getJSON("/api/meetings/session?id=" + id);
export const getActiveSession = () => getJSON("/api/meetings/active");
export const advanceSession = (id, instruction, finish = false) =>
  postJSON("/api/meetings/advance", { session_id: id, instruction, finish });
export const getAiTaste = (chapterId) => getJSON("/api/ai_taste?chapter_id=" + chapterId);
export const getEndingStatus = () => getJSON("/api/ending/status");
export const confirmNextBook = (novelId) =>
  postJSON("/api/ending/confirm", { novel_id: novelId });
export const bindBook = (novelId, bookId, volumeId) =>
  postJSON("/api/ending/bind", { novel_id: novelId, book_id: bookId, volume_id: volumeId });
export const createBookOnFanqie = (novelId) =>
  postJSON("/api/ending/create_book", { novel_id: novelId });
export const getAudit = (category) =>
  getJSON("/api/audit" + (category ? "?category=" + encodeURIComponent(category) : ""));
export const refreshHotTopics = () =>
  postJSON("/api/control", { action: "refresh_hot_topics" });
export const getKnowledge = () => postJSON("/api/knowledge", { action: "list" });
export const readKnowledge = (file) => postJSON("/api/knowledge", { action: "read", file });
export const saveKnowledge = (file, meta, body) =>
  postJSON("/api/knowledge", { action: "save", file, meta, body });
export const getKnowledgeDrafts = (status) =>
  postJSON("/api/knowledge_drafts", { action: "list", status });
export const actOnDraft = (id, action) =>
  postJSON("/api/knowledge_drafts", { action, id });
export const distillLessons = (meetingId, sessionId) =>
  postJSON("/api/knowledge_drafts", {
    action: "distill",
    meeting_id: meetingId,
    session_id: sessionId,
  });
export const getNovelKnowledge = (novelId, category) =>
  getJSON(
    "/api/novel_knowledge?novel_id=" +
      novelId +
      (category ? "&category=" + encodeURIComponent(category) : ""),
  );
export const upsertNovelKnowledge = (payload) =>
  postJSON("/api/novel_knowledge", { action: "upsert", ...payload });
export const getCharacterEvolution = (novelId) =>
  getJSON("/api/characters/evolution?novel_id=" + novelId);
export const getDiaries = (agent, type) => {
  const q = new URLSearchParams();
  if (agent) q.set("agent", agent);
  if (type) q.set("type", type);
  return getJSON("/api/diaries?" + q.toString());
};
export const getAgentStates = () => getJSON("/api/agent_states");
export const updateDiary = (id, content) =>
  postJSON("/api/diaries/update", { id, content });
export const updateAgentState = (agent, novelId, mood) =>
  postJSON("/api/agent_states/update", { agent, novel_id: novelId, mood });
