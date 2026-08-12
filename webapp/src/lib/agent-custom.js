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
  all[file] = {
    displayName: data.displayName,
    avatarText: data.avatarText,
    avatarColor: data.avatarColor,
    avatarImage: data.avatarImage || "",
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  return all[file];
}

/** 导出全部自定义资料为 JSON 字符串。@stable */
export function exportCustomAgents() {
  return JSON.stringify(loadCustomAgents(), null, 2);
}

/**
 * 从 JSON 字符串导入自定义资料；非法条目跳过并计数，失败显式返回。
 * @returns {{ok: boolean, count: number, skipped: number, error?: string}}
 */
export function importCustomAgents(json) {
  let parsed;
  try {
    parsed = JSON.parse(json);
  } catch {
    return { ok: false, count: 0, skipped: 0, error: "不是有效的 JSON" };
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, count: 0, skipped: 0, error: "导入内容必须是对象" };
  }
  const all = loadCustomAgents();
  let count = 0;
  let skipped = 0;
  for (const [file, data] of Object.entries(parsed)) {
    if (
      !file ||
      typeof data !== "object" ||
      typeof data.displayName !== "string" ||
      typeof data.avatarText !== "string" ||
      typeof data.avatarColor !== "string"
    ) {
      skipped += 1;
      continue;
    }
    all[file] = {
      displayName: data.displayName.slice(0, 40),
      avatarText: data.avatarText.slice(0, 1),
      avatarColor: data.avatarColor,
      avatarImage: typeof data.avatarImage === "string" ? data.avatarImage : "",
    };
    count += 1;
  }
  if (count === 0) {
    return { ok: false, count: 0, skipped, error: "没有可导入的有效条目" };
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  return { ok: true, count, skipped };
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

/**
 * 把图片文件压缩为 96×96 的头像 DataURL（JPEG，背景用头像色填充）。
 * @returns {Promise<string>} data URL
 */
export function compressAvatarImage(file, bgColor) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      try {
        const size = 96;
        const canvas = document.createElement("canvas");
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = bgColor || "#5B8DB8";
        ctx.fillRect(0, 0, size, size);
        const scale = Math.max(size / img.width, size / img.height);
        const w = img.width * scale;
        const h = img.height * scale;
        ctx.drawImage(img, (size - w) / 2, (size - h) / 2, w, h);
        resolve(canvas.toDataURL("image/jpeg", 0.85));
      } catch (err) {
        reject(err);
      } finally {
        URL.revokeObjectURL(url);
      }
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("图片读取失败"));
    };
    img.src = url;
  });
}
