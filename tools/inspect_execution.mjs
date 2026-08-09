import { createRequire } from "module";

const require = createRequire(import.meta.url);
const { parse } = require("C:/Users/Administrator/AppData/Roaming/npm/node_modules/n8n/node_modules/flatted");

const BASE = "http://localhost:5678";
const EMAIL = process.env.N8N_EMAIL || "";
const PASSWORD = process.env.N8N_TMP_PW;
const execId = process.argv[2] || "8";

const login = await fetch(BASE + "/rest/login", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ emailOrLdapLoginId: EMAIL, password: PASSWORD }),
});
const setCookie = login.headers.getSetCookie().find((c) => c.startsWith("n8n-auth="));
if (!setCookie) throw new Error("login failed");
const cookie = setCookie.split(";", 1)[0];

const res = await fetch(BASE + "/rest/executions/" + execId, {
  headers: { Cookie: cookie },
});
const body = await res.json();
const d = body.data;
const data = typeof d.data === "string" ? parse(d.data) : d.data;
const list = Array.isArray(data) ? data : [data];
console.log("status:", d.status);
console.log("parsed entries:", list.length);
for (let i = 0; i < list.length; i++) {
  const rd = list[i]?.resultData || {};
  const err = rd.error || {};
  console.log("---- entry", i, "----");
  console.log("lastNodeExecuted:", rd.lastNodeExecuted);
  console.log("error name:", err.name);
  console.log("error message:", err.message);
  console.log("error node:", err.node);
  console.log("runData keys:", Object.keys(rd.runData || {}));
  if (err.context) console.log("context:", JSON.stringify(err.context).slice(0, 2000));
}

const targets = process.argv.slice(3);
if (targets.length) {
  const rd = (Array.isArray(data) ? data : [data])[0]?.resultData || {};
  for (const name of targets) {
    const runs = rd.runData?.[name] || [];
    console.log("===== " + name + " =====");
    for (const r of runs) {
      for (const item of r.data?.main?.[0] || []) {
        const j = item.json;
        const s = JSON.stringify(j);
        console.log(s.length > 1500 ? s.slice(0, 1500) + " ...(truncated)" : s);
      }
    }
  }
}
