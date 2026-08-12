/** 测试共享数据夹具：与后端返回结构保持一致。@internal */
export const dashboardPayload = {
  updated_at: "2026-08-12 18:00:00",
  summary: {
    novels: 1,
    chapters_total: 42,
    chapters_published: 40,
    chapters_ready: 2,
    chapters_draft: 0,
    quality_total: 50,
    quality_passed: 48,
    publish_failed: 0,
    monthly_cost: 12.4,
  },
  executions: [
    {
      id: 1,
      workflow: "日更",
      status: "completed",
      started_at: "2026-08-12 08:03:00",
      published: 2,
    },
  ],
  cost_budget: 100,
  novels: [
    {
      id: 1,
      title: "雾港怪谈",
      genre: "规则怪谈",
      status: "publishing",
      abstract: "临海小城每逢雾夜，规则会改写现实。",
      selling_point: "规则系怪谈",
      premise: "主角凭借记录规则的手账寻找失踪的妹妹。",
      volume_goal: "三卷完",
      tags: ["怪谈", "悬疑"],
      protagonists: [{ name: "沈雾", desc: "手账持有者" }],
      outline: { 卷1: "雾起" },
      characters: [{ name: "沈雾", role: "主角", traits: "冷静", goals: "找妹妹" }],
      chapters: 42,
      published: 40,
    },
  ],
  chapters: [
    { id: 42, novel_id: 1, seq: 42, title: "雾夜来客", status: "published", words: 2480, score: 96 },
    { id: 43, novel_id: 1, seq: 43, title: "手账第一页", status: "reviewed", words: 2512, score: 93 },
  ],
  publish_logs: [
    {
      id: 1,
      chapter_id: 42,
      platform: "番茄",
      action: "publish",
      result: "success",
      ai_declared: true,
      created_at: "2026-08-12 08:03:00",
    },
  ],
  health: { issues: [], log_tail: [] },
  reader_stats: {
    present: true,
    rows: [
      { chapter: 1, finish_rate: 0.62, follow_rate: 0.41 },
      { chapter: 2, finish_rate: 0.65, follow_rate: 0.43 },
    ],
  },
  hot_topics: {
    present: true,
    updated_at: "08:00",
    top_keywords: [["规则怪谈", 12]],
    sources: [{ source: "番茄", count: 40, method: "browser" }],
  },
};

export const controlPayload = {
  scheduler: {
    enabled: true,
    scheduled_time: "08:00",
    last_run: { status: "completed", published: 2, started_at: "2026-08-12 08:03:00" },
    workday: null,
  },
  settings: {
    monthly_budget: 100,
    target_words: 2000,
    daily_chapters: 2,
    target_chapters: 0,
    novel_keywords: "规则怪谈",
  },
};

export const meetingsPayload = {
  meetings: [
    {
      id: 17,
      held_at: "2026-08-11 20:00",
      attendees: ["eic", "planner", "writer"],
      status: "completed",
      summary: "决定继续规则怪谈方向，开篇三连击方案通过。",
    },
  ],
};

export const agentsPayload = {
  agents: [
    {
      file: "eic.md",
      name: "主编终审",
      description: "仲裁逻辑审稿与读者审稿",
      model: "deepseek-v4-pro",
      temperature: "0.2",
      prompt: "你是掌印，编辑部的主编。",
      nodes: ["主编终审A"],
      synced: true,
    },
    {
      file: "writer.md",
      name: "写手",
      description: "正文初稿",
      model: "deepseek-v4-flash",
      temperature: "0.8",
      prompt: "你是墨白。",
      nodes: ["写稿A"],
      synced: false,
    },
  ],
};

export const costPayload = {
  by_day: [
    { day: "2026-08-11", cost: 1.2 },
    { day: "2026-08-12", cost: 0.4 },
  ],
  by_node: [
    { node_name: "写稿A", model: "flash", prompt_tokens: 1200, completion_tokens: 800, cost: 0.21 },
  ],
};

export const executionsPayload = {
  executions: [
    {
      id: 9,
      workflow: "日更",
      status: "partial",
      started_at: "2026-08-11 08:00:00",
      stopped_at: "2026-08-11 08:15:00",
      published: 1,
      error: "质量门 B 失败",
    },
  ],
};

export const dailyRunsPayload = {
  runs: [
    {
      run_id: "run-1",
      trigger: "manual",
      status: "completed",
      started_at: "2026-08-12 08:03:00",
      published: 2,
      failed_nodes: [],
      error: "",
    },
  ],
  sync_error: "",
};

export const editorialPayload = {
  updated_at: "2026-08-12 18:00:00",
  agents: [{ file: "writer.md", name: "写手" }],
  relations: [],
  unread: { writer: 1 },
  actions: [{ id: 1, task: "整理规则台账模板", status: "pending", assignee: "writer", due_at: "2026-08-20" }],
  today_activity: [],
};

export const mailboxPayload = {
  ok: true,
  messages: [
    {
      id: 1,
      from_agent: "reviewer",
      to_agent: "writer",
      kind: "review_feedback",
      subject: "审稿打回 · 第 42 章",
      body: "逻辑承接生硬",
      status: "unread",
      created_at: "2026-08-12 09:12:00",
    },
  ],
};

export const flowPayload = {
  nodes: [
    { id: "trigger", label: "触发（手动/定时）", group: "trigger" },
    { id: "preflight", label: "预检", group: "preflight" },
  ],
  edges: [{ source: "trigger", target: "preflight" }],
  failed_ids: [],
  node_status: {},
  last_run: { status: "completed", published: 2, run_id: "run-1" },
};

export const auditPayload = {
  logs: [
    {
      id: 1,
      created_at: "2026-08-12 08:03:00",
      category: "publish",
      action: "publish",
      target_type: "chapter",
      target_id: 42,
      detail: { result: "success" },
    },
  ],
};

export const draftsPayload = {
  ok: true,
  drafts: [
    {
      id: 3,
      kind: "lesson",
      agent: "knowledge_keeper",
      title: "开篇三连击经验",
      status: "draft",
      created_at: "2026-08-11 20:00:00",
    },
  ],
};

export const chapterContentPayload = {
  chapter_id: 42,
  content: "雾夜，灯塔的光第三次熄灭。",
  updated_at: "",
};

/** 按 URL 返回对应夹具的 mock fetch。@internal */
export function jsonResponse(data) {
  return { ok: true, json: async () => data };
}

export function mockFetchFor(overrides = {}) {
  return async (url, options = {}) => {
    const path = String(url).split("?")[0];
    if (path.endsWith("/api/dashboard")) return jsonResponse(overrides.dashboard ?? dashboardPayload);
    if (path.endsWith("/api/control")) return jsonResponse(overrides.control ?? controlPayload);
    if (path.endsWith("/api/meetings")) return jsonResponse(overrides.meetings ?? meetingsPayload);
    if (path.endsWith("/api/agents")) return jsonResponse(overrides.agents ?? agentsPayload);
    if (path.endsWith("/api/cost")) return jsonResponse(overrides.cost ?? costPayload);
    if (path.endsWith("/api/executions")) return jsonResponse(overrides.executions ?? executionsPayload);
    if (path.endsWith("/api/daily_runs")) return jsonResponse(overrides.dailyRuns ?? dailyRunsPayload);
    if (path.endsWith("/api/editorial/overview")) return jsonResponse(overrides.editorial ?? editorialPayload);
    if (path.endsWith("/api/agents/mailbox")) return jsonResponse(overrides.mailbox ?? mailboxPayload);
    if (path.endsWith("/api/flow")) return jsonResponse(overrides.flow ?? flowPayload);
    if (path.endsWith("/api/audit")) return jsonResponse(overrides.audit ?? auditPayload);
    if (path.endsWith("/api/knowledge_drafts")) return jsonResponse(overrides.drafts ?? draftsPayload);
    if (path.endsWith("/api/chapter_content")) return jsonResponse(overrides.chapterContent ?? chapterContentPayload);
    if (path.endsWith("/api/meetings/active")) return jsonResponse({ session: null });
    if (path.endsWith("/api/meetings/session")) return jsonResponse({ status: "running", transcript: [] });
    if (path.endsWith("/api/daily_runs/detail")) return jsonResponse({ run: { error: "" } });
    if (options.method === "POST") return jsonResponse({ ok: true });
    return jsonResponse({ ok: true });
  };
}
