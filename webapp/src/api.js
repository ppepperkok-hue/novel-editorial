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
