# GitHub 开源项目复用调研（2026-08-09）

> 数据来源：GitHub REST API（stars / 语言 / 协议 / 最近更新），均为公开仓库。
> 用途：为「自动生成小说并发布到番茄小说（副业定位）」挑选可复用组件。

---

## 一、发布链路（番茄）

| 项目 | Stars | 语言 | 协议 | 更新 | 能力 | 复用建议 |
|---|---|---|---|---|---|---|
| [fuhei/tomato-writer-mcp](https://github.com/fuhei/tomato-writer-mcp) | 5 | TypeScript | 无协议 | 2026-06 | 番茄作者后台 HTTP 接口：列书、看数据、发布/定时发布（Cookie + CSRF） | 直接参考其接口调用方式，作为 `FanqieHttpAdapter` 实现依据 |
| [hchcx/fanqie_auto_publish](https://github.com/hchcx/fanqie_auto_publish) | 235 | Python | 无协议 | 2026-04 | Playwright 全自动网页端发文，断点续检、弹窗斩杀 | 作为浏览器兜底通道参考 |

**注意**：这两个仓库都没有开源协议，代码只能「参考思路」，不能整段复制进自己的项目，否则有授权风险。

---

## 二、完整生成流水线

| 项目 | Stars | 协议 | 更新 | 能力 | 复用建议 |
|---|---|---|---|---|
| [Deng-m1/MaliangAINovalWriter](https://github.com/Deng-m1/MaliangAINovalWriter) | 851 | 无协议 | 2026-07 | 多智能体网文平台：三级大纲、知识图谱一致性、30 万字连载 | 功能最强且活跃，但无协议，参考其「三级大纲 + 知识图谱」设计 |
| [MJbae/awesome-novel-studio](https://github.com/MJbae/awesome-novel-studio) | 141 | Apache-2.0 | 2026-04 | Claude Code 插件，18 个专职 Agent，propose→design→create→polish→rewrite | 协议宽松，可放心借鉴 Agent 分工设计 |
| [Cppys/OpenNovel](https://github.com/Cppys/OpenNovel) | 25 | MIT | 2026-03 | LangGraph 多智能体 + ChromaDB 记忆 + 五维审稿 + 一键发布番茄 | 与我们脚手架同构且 MIT，可直接 fork 或对照改进 |
| [aswansong/novelagent](https://github.com/aswansong/novelagent) | 9 | 无协议 | 2026-05 | Human-in-the-loop + LangChain/LangGraph + RAG，缓解上下文遗忘与角色崩坏 | 参考「关键节点人工介入」设计 |
| [starMagic/webnovel-writer-hermes](https://github.com/starMagic/webnovel-writer-hermes) | 7 | GPL-3.0 | 2026-06 | 12 技能 + 5 子 Agent + 故事合同引擎 | GPL 传染性强，仅参考，不合入商业闭源项目 |
| [ricky-theseus/DaisyWriter](https://github.com/ricky-theseus/DaisyWriter) | 64 | GPL-3.0 | 2026-07 | 网文扫描 / 拆解 / 卷级 beat sheet | GPL，参考选题与拆书流程 |
| [cjyyx/AI_Gen_Novel](https://github.com/cjyyx/AI_Gen_Novel) | 424 | MIT | 2024-09 | 多智能体写作实验 | 较旧，作历史参考 |
| [BlinkDL/AI-Writer](https://github.com/BlinkDL/AI-Writer) | 3842 | Apache-2.0 | 2025-05 | RWKV 中文网文生成模型 | 想要完全本地、零 API 费用时可评估，但生成质量一般弱于商用 API |

---

## 三、写作工作台与记忆

| 项目 | Stars | 协议 | 更新 | 能力 | 复用建议 |
|---|---|---|---|---|
| [MemMachine/MemMachine](https://github.com/MemMachine/MemMachine) | 3352 | Apache-2.0 | 2026-08 | Agent 通用记忆层（存储/检索/追踪） | 30 万字以上连载时，把我们的 `chapter_summaries` 升级为 MemMachine |
| [xiaoshengxianjun/51mazi](https://github.com/xiaoshengxianjun/51mazi) | 431 | MIT | 2026-07 | 桌面写作软件：关系图谱、人物档案、时间线、AI 写作 | 半自动阶段人工过目时可搭配使用 |
| [idiomc/webnovel-reverse-analysis](https://github.com/idiomc/webnovel-reverse-analysis) | 0 | 无协议 | 2026-07 | 逆向分析网文结构（人物矩阵/风格指纹/卖点） | 参考其思路做选题与竞品分析 |

---

## 四、结论与建议（副业定位）

1. **编排底座**：继续用我们自己的 [novel-editorial](novel-editorial/README.md)（测试全绿、零依赖），不整盘迁移。
2. **发布接入**：按 `tomato-writer-mcp` 的 HTTP 接口方式实现 `FanqieHttpAdapter`；浏览器自动化（`fanqie_auto_publish` 思路）做兜底。**只借鉴思路，不复制无协议代码。**
3. **质量与记忆**：Agent 分工参考 `awesome-novel-studio`（Apache-2.0）；长篇记忆后期升级 `MemMachine`（Apache-2.0）。
4. **选题**：参考 `DaisyWriter` / `webnovel-reverse-analysis` 的拆书与结构分析思路，强化我们的 Planner。
5. **成本**：副业求持续盈利，起步用 DeepSeek 档（单章约 ¥0.1-0.5）；RWKV 本地生成只在想零 API 成本时再评估。

---

## 五、协议红线提醒

- **无协议仓库**（tomato-writer-mcp、fanqie_auto_publish、MaliangAINovalWriter、novelagent 等）：默认「保留所有权利」，只参考、不复制。
- **GPL-3.0**（DaisyWriter、webnovel-writer-hermes）：传染性强，除非整个项目开源，否则不合入。
- **MIT / Apache-2.0**（OpenNovel、awesome-novel-studio、MemMachine、51mazi、AI-Writer）：可放心参考与使用，注意保留版权声明。
