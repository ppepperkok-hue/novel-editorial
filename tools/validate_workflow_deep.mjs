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
  // 0. no duplicate edges anywhere
  for (const [src, v] of Object.entries(conns)) {
    for (const [port, arrays] of Object.entries(v)) {
      for (const arr of arrays || []) {
        const seen = new Set();
        for (const e of arr || []) {
          const key = `${e.node}|${e.type}|${e.index}`;
          if (seen.has(key)) {
            issues.push(`${file}: duplicate ${port} edge ${src} -> ${e.node}`);
          }
          seen.add(key);
        }
      }
    }
  }
  for (const [src, v] of Object.entries(conns)) {
    if (!names.has(src)) issues.push(`${file}: Connection source missing: ${src}`);
    for (const arr of v.main || []) {
      for (const t of arr || []) {
        if (!names.has(t.node)) issues.push(`${file}: Connection target missing: ${t.node} (from ${src})`);
      }
    }
  }
  for (const n of nodes) {
    const terminals = new Set([
      "记录作品资料", "结束", "采集阅读数据", "发布存稿", "全员写日记",
      "解析复核A", "解析复核B", "失败留痕",
    ]);
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
      ["同步设定知识库", "回填行动项"],
      ["回填行动项", "结束"],
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
      ["合并兜底", "非空兜底"],
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
    // live book binding: 预检通过? -> 读当前书 -> 查存稿; 设定题材 must read
    // the book from the database (n8n env does not refresh on bind).
    for (const [src, dst] of [
      ["预检通过?", "读当前书"],
      ["读当前书", "查存稿"],
    ]) {
      const targets = (conns[src]?.main?.[0] || []).map((x) => x.node);
      if (!targets.includes(dst)) {
        issues.push(`${file}: current-book chain broken ${src} -> ${dst}`);
      }
    }
    const topicNode = nodes.find((n) => n.name === "设定题材");
    if (topicNode) {
      const topicJson = JSON.stringify(topicNode.parameters);
      if (!/JSON\.parse\(\(\$\('读当前书'\)/.test(topicJson)) {
        issues.push(`${file}: 设定题材 book_id does not read 读当前书`);
      }
    }
    // reviewing/memory agents must see the bible (characters/relations/world)
    // in their task; otherwise first-run OOC/setting checks are blind.
    for (const name of [
      "读者审稿A", "读者审稿B", "主编终审A", "主编终审B",
      "提炼剧情A", "提炼剧情B",
    ]) {
      const node = nodes.find((n) => n.name === name);
      if (node && !/角色卡：/.test(node.parameters.jsonBody || "")) {
        issues.push(`${file}: ${name} task does not reference the bible characters`);
      }
    }
    // target_words must flow from settings (get_meta) through 解析本地资料;
    // otherwise the settings page target-word config silently stays 2000.
    const parsedLocal = nodes.find((n) => n.name === "解析本地资料");
    if (parsedLocal && !/target_words: \(pm\.target_words \|\| 2000\)/.test(
      parsedLocal.parameters.jsCode || "",
    )) {
      issues.push(`${file}: 解析本地资料 does not expose target_words`);
    }
    // final walkthrough guards: quality gates fail softly on bad JSON,
    // verification nodes tolerate non-JSON bodies, editors get max_tokens.
    for (const name of ["质量门A", "质量门B"]) {
      const node = nodes.find((n) => n.name === name);
      if (node && !/审稿输出非JSON|review = null/.test(node.parameters.jsCode || "")) {
        issues.push(`${file}: ${name} must fail softly on non-JSON review`);
      }
    }
    for (const name of ["解析复核A", "解析复核B"]) {
      const node = nodes.find((n) => n.name === name);
      if (node && !/复核响应非JSON/.test(node.parameters.jsCode || "")) {
        issues.push(`${file}: ${name} must tolerate non-JSON API bodies`);
      }
    }
    for (const name of ["润色A", "润色B"]) {
      const node = nodes.find((n) => n.name === name);
      if (node && !/max_tokens:(4000|8000)/.test(node.parameters.jsonBody || "")) {
        issues.push(`${file}: ${name} is missing max_tokens (truncation risk)`);
      }
    }
    // H3/H7: memory/整理 nodes must tolerate errors so one track does not
    // kill the other; merge fallback must read quality gates; 算章节号 must
    // fail loudly when the active book is missing.
    // J1/J2: LLM failures must flow to the error branch -> 失败留痕, and the
    // summary must consume the trace (no silent lost chapters).
    const errorNodes = [
      "写手A", "写手B", "润色A", "润色B", "审稿A", "审稿B",
      "读者审稿A", "读者审稿B", "主编终审A", "主编终审B",
      "提炼剧情A", "提炼剧情B", "整理剧情A", "整理剧情B",
      "质量门A", "质量门B", "守护细纲", "新建草稿A", "新建草稿B",
    ];
    for (const name of errorNodes) {
      const node = nodes.find((n) => n.name === name);
      if (node && node.onError !== "continueErrorOutput") {
        issues.push(`${file}: ${name} must route errors to the error branch`);
      }
      const errTargets = (conns[name]?.error?.[0] || []).map((x) => x.node);
      if (node && !errTargets.includes("失败留痕")) {
        issues.push(`${file}: ${name} error edge must reach 失败留痕`);
      }
    }
    if (!nodes.some((n) => n.name === "失败留痕")) {
      issues.push(`${file}: missing 失败留痕 node`);
    }
    const traceNode = nodes.find((n) => n.name === "失败留痕");
    if (traceNode && !/\$input\.all\(\)/.test(traceNode.parameters.jsCode || "")) {
      issues.push(`${file}: 失败留痕 must collect all error items`);
    }
    const collector = nodes.find((n) => n.name === "合并兜底");
    if (collector && !/失败留痕/.test(collector.parameters.jsCode || "")) {
      issues.push(`${file}: 合并兜底 must reference 失败留痕`);
    }
    const fallback = nodes.find((n) => n.name === "合并兜底");
    if (fallback && (!/质量门A/.test(fallback.parameters.jsCode || "") || !/质量门B/.test(fallback.parameters.jsCode || ""))) {
      issues.push(`${file}: 合并兜底 must read both quality gates`);
    }
    const seqNode = nodes.find((n) => n.name === "算章节号");
    if (seqNode && !/未找到活跃作品/.test(seqNode.parameters.jsCode || "")) {
      issues.push(`${file}: 算章节号 must fail loudly without an active book`);
    }
    if (!/failNames/.test(summary?.parameters.jsCode || "")) {
      issues.push(`${file}: 汇总运行结果 must consume 失败留痕 (no silent failures)`);
    }
    if (!/质量门通过但草稿创建\/发布链中断/.test(summary?.parameters.jsCode || "")) {
      issues.push(`${file}: 汇总运行结果 must record gate-passed-but-draft-missing`);
    }
  }

  // 5. executeCommand nodes: parameterized command + args + relative cwd.
  // n8n 2.x ships ExecuteCommand v1 (single `command` string; commandArguments
  // and options.cwd are ignored). Newer n8n versions support the split form,
  // so both shapes are accepted here.
  for (const n of nodes) {
    if (n.type !== "n8n-nodes-base.executeCommand") continue;
    const p = n.parameters || {};
    const command = String(p.command || "");
    const args = p.commandArguments;
    const cwd = (p.options && p.options.cwd) || "";
    const legacy = !args || args === "";
    if (!command.includes("$env.PYTHON_EXE")) {
      issues.push(`${file}: executeCommand ${n.name} command is not parameterized with $env.PYTHON_EXE`);
    }
    if (legacy) {
      if (!command.includes("$env.PIPELINE_ROOT")) {
        issues.push(`${file}: executeCommand ${n.name} command does not parameterize cwd with $env.PIPELINE_ROOT`);
      }
      if (!command.includes(".join(' ')")) {
        issues.push(`${file}: executeCommand ${n.name} v1 command must join its argument array`);
      }
      if (/E:[/\\]code|Python311/.test(command)) {
        issues.push(`${file}: executeCommand ${n.name} contains hardcoded paths`);
      }
      const withoutInterp = command.replace(/\$env\.PYTHON_EXE/g, "");
      if (/\bpython(\.exe)?\b/i.test(withoutInterp)) {
        issues.push(`${file}: executeCommand ${n.name} repeats the interpreter in command`);
      }
    } else {
      if (!cwd.includes("$env.PIPELINE_ROOT")) {
        issues.push(`${file}: executeCommand ${n.name} cwd is not parameterized with $env.PIPELINE_ROOT`);
      }
      const hay = command + JSON.stringify(args || "") + cwd;
      if (/E:[/\\]code|Python311|&/.test(hay)) {
        issues.push(`${file}: executeCommand ${n.name} contains hardcoded paths or shell '&'`);
      }
      if (typeof args === "string" && args.includes("$env.PYTHON_EXE")) {
        issues.push(`${file}: executeCommand ${n.name} repeats the interpreter in commandArguments`);
      }
    }
  }

  // 6. agent proxy nodes must hit the unified local port.
  for (const n of nodes) {
    if (n.type !== "n8n-nodes-base.httpRequest") continue;
    const url = String(n.parameters.url || "");
    if (url.includes("/api/agent/run") && !url.startsWith("http://127.0.0.1:8000/api/agent/run")) {
      issues.push(`${file}: agent node ${n.name} targets ${url}; expected unified port 8000`);
    }
    if (url.includes("/api/agent/run") && !/novel_id:\(/.test(n.parameters.jsonBody || "")) {
      issues.push(`${file}: agent node ${n.name} does not carry novel_id (book isolation)`);
    }
    // expression syntax of agent proxy bodies (protects against broken
    // task string concatenations that render/validate used to miss).
    const body = n.parameters.jsonBody || "";
    const m = body.match(/^=\{\{ JSON\.stringify\((.*)\) \}\}$/s);
    if (url.includes("/api/agent/run") && m) {
      try {
        // eslint-disable-next-line no-new-func
        new Function("return " + m[1]);
      } catch (e) {
        issues.push(`${file}: ${n.name} jsonBody expression syntax error: ${e.message}`);
      }
    }
  }

  // 7. book isolation: daily diaries and weekly meetings bind to a novel/book.
  if (file === "novel_workflow.json") {
    const cmdText = (node) =>
      JSON.stringify(
        (node && node.parameters && (node.parameters.commandArguments || node.parameters.command)) || ""
      );
    const diary = nodes.find((n) => n.name === "全员写日记");
    if (diary && !/--novel-id/.test(cmdText(diary))) {
      issues.push(`${file}: 全员写日记 does not bind --novel-id`);
    }
    if (diary && /解析本地资料/.test(cmdText(diary))) {
      issues.push(`${file}: 全员写日记 must read 读当前书, not 解析本地资料 (stock branch)`);
    }
  }
  if (file === "architect_weekly.json") {
    if (!nodes.some((n) => n.name === "读当前书")) {
      issues.push(`${file}: missing 读当前书 node`);
    }
    const cmdText = (node) =>
      JSON.stringify(
        (node && node.parameters && (node.parameters.commandArguments || node.parameters.command)) || ""
      );
    for (const name of ["读上下文", "开会"]) {
      const node = nodes.find((n) => n.name === name);
      if (node && !/JSON\.parse\(\$\('读当前书'\)/.test(cmdText(node))) {
        issues.push(`${file}: ${name} must read book from 读当前书, not n8n env`);
      }
    }
  }
}

if (issues.length) {
  console.log("ISSUES:");
  for (const i of issues) console.log(" -", i);
  process.exit(1);
}
console.log(`OK: all workflows valid`);
