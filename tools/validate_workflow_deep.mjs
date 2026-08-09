import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const files = ["novel_workflow.json", "architect_weekly.json"];
const issues = [];

for (const file of files) {
  const wf = JSON.parse(
    fs.readFileSync(path.resolve(here, "../n8n/" + file), "utf-8"),
  );
  const nodes = wf.nodes;
  const names = new Set(nodes.map((n) => n.name));

  // 1. JS syntax of every code node
  for (const n of nodes) {
    if (n.type === "n8n-nodes-base.code") {
      const code = n.parameters.jsCode || "";
      try {
        // eslint-disable-next-line no-new-func
        new Function(code);
      } catch (e) {
        issues.push(`${file}: JS syntax error in ${n.name}: ${e.message}`);
      }
    }
  }

  // 2. node references in expressions
  const refRe = /\$\('([^']+)'\)/g;
  for (const n of nodes) {
    const hay = JSON.stringify(n.parameters);
    let m;
    while ((m = refRe.exec(hay)) !== null) {
      if (!names.has(m[1])) issues.push(`${file}: Missing node ref '${m[1]}' in ${n.name}`);
    }
  }

  // 3. connections
  const conns = wf.connections || {};
  for (const [src, v] of Object.entries(conns)) {
    if (!names.has(src)) issues.push(`${file}: Connection source missing: ${src}`);
    for (const arr of v.main || []) {
      for (const t of arr || []) {
        if (!names.has(t.node)) issues.push(`${file}: Connection target missing: ${t.node} (from ${src})`);
      }
    }
  }
  for (const n of nodes) {
    const terminals = new Set(["记录作品资料", "结束", "采集阅读数据", "发布存稿", "全员写日记"]);
    if (!conns[n.name] && n.type !== "n8n-nodes-base.scheduleTrigger" && !terminals.has(n.name)) {
      issues.push(`${file}: Node without outgoing connection: ${n.name}`);
    }
  }
}

if (issues.length) {
  console.log("ISSUES:");
  for (const i of issues) console.log(" -", i);
  process.exit(1);
}
console.log(`OK: both workflows valid`);
