# 前端完全重构：决策记录与技术评估（2026-08-12）

## 1. 背景与目标

webapp 前端自多轮迭代后结构膨胀：巨型组件、单文件全局样式、页面各自轮询、组件抽象缺失。本次按用户决策「几乎重做」执行：

- 视觉方向：minimalist 编辑部（taste-skill minimalist 变体），双主题完整打磨。
- 信息架构：12 页重组为五区两级导航（总览 / 编辑部 / 创作 / 运营 / 系统）。
- 组件体系：shadcn 基础组件 + 自建业务组件；动效用 framer-motion（低强度）。
- 技术栈：React 19 / Vite 7 / recharts 3 / react-router（HashRouter），保留 zustand 与 @xyflow/react。
- 边界：后端 40 个 API 契约与 `webapp/dist` 构建路径冻结；Electron 壳不改造，仅作验收环境。

## 2. 现状证据锚点（技术评估依据）

| 问题 | 证据 | 影响 |
| --- | --- | --- |
| 巨型组件超硬上限 | DashboardPage.jsx 608 行 / 26.2KB、WorksPage.jsx 540、agent-panels.jsx 546、SettingsPage.jsx 494、AgentsPage.jsx 475、MeetingLive.jsx 425（execution-gates 硬上限 500 行） | 维护困难、职责混杂、测试颗粒粗 |
| 全局样式单文件 | index.css 987 行，类名体系与 Tailwind 工具类混用，页面内大量 `!px-3 !py-1` 覆写 | token 不成体系、双主题难打磨、样式无法复用 |
| 路由手写 | App.jsx 用 location.hash + NAV 数组手工路由，12 页平铺 | 无嵌套导航、深链语义弱 |
| 数据层重复 | stores.js 仅 3 个全局字段；各页各自 fetch + setInterval（DashboardPage 内 3 处轮询） | loading/error 四态不统一、轮询混乱 |
| 构建契约 | desktop/main.js:190 `win.loadURL("http://127.0.0.1:8000/")`；novel_editorial/web_api.py:1077/1096 优先伺服 `webapp/dist` | 重构后构建产物路径与伺服方式不得变更 |
| API 契约 | api.js 共 49 个导出（40+ 数据接口） | 全部保留返回结构，前端只改消费层 |

## 3. 影响范围与风险

**影响范围**：仅 `webapp/` 前端源码、依赖清单与前端测试；不触碰 `novel_editorial/`、`tools/`、`desktop/`、`scripts/`（审查脚本除外，本次不修改）。

**风险**：

1. React 19 / Vite 7 / recharts 3 升级引入兼容问题（@xyflow/react 12 支持 React 19；recharts 3 API 有调整）。→ 回退策略：记录决策后回退 React 18，其余重构继续。
2. 前端测试 20 用例全部重写，回归覆盖依赖新测试质量。→ 每页冒烟 + 核心交互用例兜底。
3. shadcn init 与 Tailwind 4 版本组合需实测。→ 阶段 2 先做最小骨架验证再铺开。
4. impeccable 安装写 `.codex/hooks.json`。→ 若 hook 干扰工作流，保留技能、移除 hook 并记录。
5. 重构期间 `webapp/dist` 不可用会短暂影响桌面壳。→ 阶段 8 联调时重新构建；本地开发用 vite dev 端口。

**回退方式**：分支 `codex/frontend-redesign` 与 main 隔离；任意阶段可丢弃分支回退到 `ee9b3a3`。

## 4. 工程表（分步实施 / 验收 / 审查）

| 阶段 | 内容 | 验收 | 审查 |
| --- | --- | --- | --- |
| 0 | 决策记录、归档旧计划、开分支 | 本文档 + archive 迁移完成、分支就绪 | 主 agent 逐条核对无分歧 |
| 1 | 安装 taste-skill / impeccable；概念图（亮/暗）；锁定设计刻度盘 | 概念图经用户确认；刻度盘写入决策记录 | impeccable critique 反 AI-slop |
| 2 | 升级 React 19 / Vite 7 / recharts 3；新增 react-router / motion / shadcn 依赖；重建 src 目录骨架 | `npm run build` 通过；依赖无重复 React | 步间增量审查 |
| 3 | tokens.css 双主题 token；shadcn 基础件初始化；业务基础件（KpiCard/StateDot/ProcessCard/四态） | 双主题切换无硬编码色；刻度一致；a11y 底线 | impeccable detect 清零 |
| 4 | HashRouter 五区导航；标题栏/命令面板/快捷键/全局状态条；framer-motion 过渡 | 深链可用；五区折叠；Electron 控制正常 | 快捷键用例先写后过 |
| 5 | useApi hook + 按域 zustand store；消灭各页重复轮询 | 40 个接口零改动；数据组件四态完整 | 与旧 api.js 逐函数对照 |
| 6 | 12 页按五批重写，巨型文件全部拆解 | 每页冒烟 + 空态用例；单文件 ≤500 行；无 `!` 覆写 | 每批一次增量审查 |
| 7 | framer-motion 动效统一；prefers-reduced-motion | 低强度、不阻塞交互 | 截图对比概念图 |
| 8 | 测试重写（30+ 用例）、npm test / build、impeccable detect、后端 511 全绿、桌面壳联调截图 | 全部门禁通过；成品可运行 | 前端分片审查出临时报告 |
| 9（收尾，待用户确认） | 审查报告归档、README 更新、合并 main、推送 | 用户验收后执行 | — |

## 5. 验收标准（最终）

- `npm test` 全绿（新测试 30+ 用例）、`npm run build` 成功、`impeccable detect` 无未豁免 P0/P1。
- 后端 `python run_tests.py` 511 用例全绿。
- 桌面壳通过 8000 端口加载新 dist；五区导航、双主题、命令面板、快捷键可用。
- 12 页业务功能全部保留；无 `!` 覆写类名；无装饰性 emoji；四态完整。

## 6. 假设与默认

- 12 页功能不砍；热点采集留在首页。
- API 契约与 `webapp/dist` 路径冻结；Electron 壳不改造。
- 开发过程本地提交到 `codex/frontend-redesign`，不推送、不合并、不写 README，直到用户确认成品。
- 敏感信息（路径、账号、密钥）不进任何新增文档。

## 7. 阶段 1 结果（2026-08-12）

**技能**：taste-skill（`~/.codex/skills/taste-skill`）、minimalist-skill（`~/.codex/skills/minimalist-skill`）、impeccable（`~/.codex/skills/impeccable` + `~/.agents/skills/impeccable`）已安装到用户级；impeccable 的 `.codex/hooks.json` 因 Windows shell 兼容性暂缓启用，用 CLI `detect` 代替，记录在案。

**概念稿**：`docs/design/concept.html` 多页可交互概念（12 页 + 亮暗主题），截图在 `docs/design/shots/`。图像生成内置工具与 OpenAI key 不可用，改用「可运行 HTML 概念稿 + Edge headless 截图 + qwen-vl 视觉验收」流程，等价达到概念确认目的。

**用户确认的设计决策**：
- 首页为「编辑部工作台」：状态带 + 主列（开工指令行 / 今日记录 / 行动项）+ 侧栏（待您决定 / 本月 / 最近会议 / 热点）。
- 开工模块为「指令行」：模式分段（写稿/整理日/开会日/自由安排）+ 章数步进 + 老板指令输入 + 单一「开工」按钮。
- 首页不放完读率折线图（泛化要求，网文专属指标移入阅读数据页）。
- 全部 12 页统一设计语言：分割线分组 > 卡片容器、单一主操作、不对称主从布局。
- 图标用 @phosphor-icons/react（taste-skill 约束，弃用 lucide）；字体禁用 Inter，拉丁用 Geist 自托管、中文走系统 UI 栈；无 emoji、无重阴影、无渐变、单一 accent（深蓝 #1f6c9f / 暗色 #7fb0d9）。

**待实现时吸收的验收反馈**：统一圆角刻度（卡片 10px / 控件 6px / 标签 pill）、KPI 与表格列头对齐、表单保存反馈、图表坐标轴、链路节点状态标注与间距、四态完整。
