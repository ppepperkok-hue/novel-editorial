import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const wf = JSON.parse(
  fs.readFileSync(path.resolve(here, "../n8n/novel_workflow.json"), "utf-8"),
);
const nodes = wf.nodes;
const names = new Set(nodes.map((n) => n.name));
const issues = [];

// 1. JS syntax of every code node
for (const n of nodes) {
  if (n.type === "n8n-nodes-base.code") {
    const code = n.parameters.jsCode || "";
    try {
      // eslint-disable-next-line no-new-func
      new Function(code);
    } catch (e) {
      issues.push(`JS syntax error in ${n.name}: ${e.message}`);
    }
  }
}

// 2. node references in expressions
const refRe = /\$\('([^']+)'\)/g;
for (const n of nodes) {
  const hay = JSON.stringify(n.parameters);
  let m;
  while ((m = refRe.exec(hay)) !== null) {
    if (!names.has(m[1])) issues.push(`Missing node ref '${m[1]}' in ${n.name}`);
  }
}

// 3. connections
const conns = wf.connections || {};
for (const [src, v] of Object.entries(conns)) {
  if (!names.has(src)) issues.push(`Connection source missing: ${src}`);
  for (const arr of v.main || []) {
    for (const t of arr || []) {
      if (!names.has(t.node)) issues.push(`Connection target missing: ${t.node} (from ${src})`);
    }
  }
}
for (const n of nodes) {
  const terminals = new Set(["记录作品资料", "结束", "采集阅读数据"]);
  if (!conns[n.name] && n.type !== "n8n-nodes-base.scheduleTrigger" && !terminals.has(n.name)) {
    issues.push(`Node without outgoing connection: ${n.name}`);
  }
}

if (issues.length) {
  console.log("ISSUES:");
  for (const i of issues) console.log(" -", i);
  process.exit(1);
}
console.log(`OK: ${nodes.length} nodes, all JS/refs/connections valid`);
