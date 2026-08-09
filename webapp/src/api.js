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
