import { createRequire } from "module";

const require = createRequire(import.meta.url);
const { parse } = require("C:/Users/Administrator/AppData/Roaming/npm/node_modules/n8n/node_modules/flatted");

const BASE = "http://localhost:5678";
const EMAIL = process.env.N8N_EMAIL || "";
const PASSWORD = process.env.N8N_TMP_PW;
const execId = process.argv[2];

const login = await fetch(BASE + "/rest/login", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ emailOrLdapLoginId: EMAIL, password: PASSWORD }),
});
const setCookie = login.headers.getSetCookie().find((c) => c.startsWith("n8n-auth="));
const cookie = setCookie.split(";", 1)[0];
const res = await fetch(BASE + "/rest/executions/" + execId, {
  headers: { Cookie: cookie },
});
const body = await res.json();
const d = body.data;
const parsed = typeof d.data === "string" ? parse(d.data) : d.data;
const fs = await import("node:fs");
fs.writeFileSync("work/exec_" + execId + ".parsed.json", JSON.stringify(parsed, null, 2), "utf-8");
console.log("saved", Array.isArray(parsed) ? parsed.length + " entries" : "object");
