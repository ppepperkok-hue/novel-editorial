import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const files = ["novel_workflow.json", "architect_weekly.json", "knowledge_keeper.json"];
const issues = [];

const upstreamOf = (conns, name) => {
  const ups = [];
  for (const [src, v] of Object.entries(conns)) {
    for (const arr of v.main || []) {
      for (const t of arr || []) {
        if (t.node === name) ups.push(src);
      }
    }
  }
  return ups;
};

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
      if (/E:\/code|Python311|C:\/Users\/Administrator/.test(code)) {
        issues.push(`${file}: code node ${n.name} contains a hardcoded machine path`);
      }
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

  // 4. semantic data-flow checks
  if (file === "novel_workflow.json") {
    // layout nodes must be fed directly by their 整理剧情 node, which carries
    // the quality-gate editedText payload; otherwise the chapter vanishes.
    for (const [layout, source] of [
      ["排版A", "整理剧情A"],
      ["排版B", "整理剧情B"],
    ]) {
      const ups = upstreamOf(conns, layout);
      if (!ups.includes(source)) {
        issues.push(`${file}: ${layout} upstream is ${JSON.stringify(ups)}; expected ${source} (editedText data flow)`);
      }
    }
    // 同步设定知识库 must not sit on the B track.
    if (upstreamOf(conns, "同步设定知识库").includes("整理剧情B")) {
      issues.push(`${file}: 同步设定知识库 still sits on the B track; move it to the tail`);
    }
    // publish chain
    const chain = [
      ["排版A", "新建草稿A"], ["新建草稿A", "解析草稿A"], ["解析草稿A", "保存内容A"],
      ["保存内容A", "提交发布A"], ["提交发布A", "校验发布A"],
      ["校验发布A", "复核发布A"],
      ["排版B", "新建草稿B"], ["新建草稿B", "解析草稿B"], ["解析草稿B", "保存内容B"],
      ["保存内容B", "提交发布B"], ["提交发布B", "校验发布B"],
      ["校验发布B", "复核发布B"],
    ];
    for (const [src, dst] of chain) {
      const targets = (conns[src]?.main?.[0] || []).map((x) => x.node);
      if (!targets.includes(dst)) issues.push(`${file}: publish chain broken ${src} -> ${dst}`);
    }
    // tail chain
    for (const [src, dst] of [
      ["发布存稿", "采集阅读数据"],
      ["采集阅读数据", "全员写日记"],
      ["全员写日记", "同步设定知识库"],
      ["同步设定知识库", "结束"],
    ]) {
      const targets = (conns[src]?.main?.[0] || []).map((x) => x.node);
      if (!targets.includes(dst)) issues.push(`${file}: tail chain broken ${src} -> ${dst}`);
    }
    // idempotency: summary must mark direct publishes as published/draft.
    const summary = nodes.find((n) => n.name === "汇总运行结果");
    const sumCode = summary ? summary.parameters.jsCode || "" : "";
    if (!/aOk \? 'published' : 'reviewed'/.test(sumCode)) {
      issues.push(`${file}: 汇总运行结果 must keep publish failures as 'reviewed' for retry`);
    }
    if (!/qa\.passed === false/.test(sumCode)) {
      issues.push(`${file}: 汇总运行结果 must record quality-gate failures explicitly`);
    }
    if (!/qb\.passed === false/.test(sumCode)) {
      issues.push(`${file}: 汇总运行结果 must record B-track quality-gate failures explicitly`);
    }
    // both-tracks-failed runs must still reach the summary via the fallback.
    for (const [src, dst] of [
      ["整理剧情A", "合并兜底"],
      ["合并兜底", "合并发布结果"],
    ]) {
      const targets = (conns[src]?.main?.[0] || []).map((x) => x.node);
      if (!targets.includes(dst)) {
        issues.push(`${file}: merge fallback chain broken ${src} -> ${dst}`);
      }
    }
    // bible init chain: 解析大纲 -> 初始化设定知识库 -> 守护细纲
    for (const [src, dst] of [
      ["解析大纲", "初始化设定知识库"],
      ["初始化设定知识库", "守护细纲"],
    ]) {
      const targets = (conns[src]?.main?.[0] || []).map((x) => x.node);
      if (!targets.includes(dst)) {
        issues.push(`${file}: bible init chain broken ${src} -> ${dst}`);
      }
    }
  }

  // 5. executeCommand nodes: parameterized command + args + relative cwd.
  for (const n of nodes) {
    if (n.type !== "n8n-nodes-base.executeCommand") continue;
    const p = n.parameters || {};
    const command = String(p.command || "");
    const args = p.commandArguments;
    const cwd = (p.options && p.options.cwd) || "";
    if (!command.includes("$env.PYTHON_EXE")) {
      issues.push(`${file}: executeCommand ${n.name} command is not parameterized with $env.PYTHON_EXE`);
    }
    if (!args || args === "") {
      issues.push(`${file}: executeCommand ${n.name} has no commandArguments`);
    }
    if (!cwd.includes("$env.PIPELINE_ROOT")) {
      issues.push(`${file}: executeCommand ${n.name} cwd is not parameterized with $env.PIPELINE_ROOT`);
    }
    const hay = command + JSON.stringify(args || "") + cwd;
    if (/E:\/code|Python311|&/.test(hay)) {
      issues.push(`${file}: executeCommand ${n.name} contains hardcoded paths or shell '&'`);
    }
    if (typeof args === "string" && args.includes("$env.PYTHON_EXE")) {
      issues.push(`${file}: executeCommand ${n.name} repeats the interpreter in commandArguments`);
    }
  }

  // 6. agent proxy nodes must hit the unified local port.
  for (const n of nodes) {
    if (n.type !== "n8n-nodes-base.httpRequest") continue;
    const url = String(n.parameters.url || "");
    if (url.includes("/api/agent/run") && !url.startsWith("http://127.0.0.1:8000/api/agent/run")) {
      issues.push(`${file}: agent node ${n.name} targets ${url}; expected unified port 8000`);
    }
  }
}

if (issues.length) {
  console.log("ISSUES:");
  for (const i of issues) console.log(" -", i);
  process.exit(1);
}
console.log(`OK: all workflows valid`);
