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
