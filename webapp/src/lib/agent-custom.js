/**
 * Agent 自定义资料（显示名 / 头像文字 / 头像颜色）。
 * 纯前端 localStorage 方案：不改后端契约，按 file 覆盖显示。
 * @stable
 */
const STORAGE_KEY = "agent_custom_v1";

export const AVATAR_COLORS = [
  "#5B8DB8",
  "#5B9B8C",
  "#8C9B5B",
  "#B8885B",
  "#A35B8C",
  "#B85B5B",
  "#7B7FB8",
  "#5BA8A8",
];

export function loadCustomAgents() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

export function getCustomAgent(file) {
  return loadCustomAgents()[file] || null;
}

export function saveCustomAgent(file, data) {
  const all = loadCustomAgents();
  all[file] = { displayName: data.displayName, avatarText: data.avatarText, avatarColor: data.avatarColor };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  return all[file];
}

export function avatarColorOf(file, index = 0) {
  const custom = getCustomAgent(file);
  if (custom?.avatarColor) return custom.avatarColor;
  return AVATAR_COLORS[Math.abs(index) % AVATAR_COLORS.length];
}

export function displayNameOf(agent, index = 0) {
  const custom = agent ? getCustomAgent(agent.file) : null;
  if (custom?.displayName) return custom.displayName;
  const key = String(agent?.file || "").replace(/\.md$/, "");
  return AGENT_DEFAULT_NAMES[key] || agent?.name || key || "编辑";
}

export function avatarTextOf(agent, index = 0) {
  const custom = agent ? getCustomAgent(agent.file) : null;
  if (custom?.avatarText) return custom.avatarText.slice(0, 1);
  return displayNameOf(agent, index).slice(0, 1);
}

export const AGENT_DEFAULT_NAMES = {
  planner: "文策",
  guard: "守界",
  writer: "墨白",
  editor: "润物",
  reviewer: "守正",
  reader: "阿读",
  memory: "录事",
  work_meta: "书案",
  eic: "掌印",
  ending_judge: "终局",
  knowledge_keeper: "博闻",
};
