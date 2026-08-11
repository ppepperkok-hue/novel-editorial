# 去 n8n 迁移映射表（66 节点 → Python 调度器）

日期：2026-08-11
基线：`e024e80`（n8n 66 节点日更工作流 `SkLUnm3uRyBSY84F` 为唯一跑通基线）
原则：业务逻辑已在 Python 侧，n8n 只是编排壳；调度器逐步等价复刻节点语义，n8n JSON 保留为回退备份。

## 1. 工作流构成

| 类型 | 数量 | 作用 |
| --- | --- | --- |
| httpRequest | 25 | 15 个调本地 `/api/agent/run`（LLM agent），8 个调番茄接口，1 个作品资料保存，1 个章节列表 |
| code | 22 | JSON 解析、质量门、排版、标题序号、汇总、兜底、失败留痕 |
| executeCommand | 13 | 调本地 Python 工具（预检/读资料/记录/备份/发布/日记/知识库/行动项/锁） |
| switch | 3 | 预检通过? / 需要更新作品资料? / 存稿充足? |
| scheduleTrigger | 1 | 每日定时（将被 Windows 计划任务替代） |
| webhook | 1 | 手动触发（将被面板 control action 替代） |
| set | 1 | 设定题材（当前书参数） |

## 2. 节点逐项映射

### 2.1 触发与预检

| n8n 节点 | 作用 | Python 等价 | 备注 |
| --- | --- | --- | --- |
| 每日触发 / 手动触发 | 定时/手动入口 | Windows 计划任务 + `daily(trigger="scheduled"\|"manual")` | 计划任务由 `install_daily_task.ps1` 管理 |
| 备份数据库 | 运行前备份 | `novel_editorial/backup.py --db demo.db --backup-dir backups` | 保持 subprocess 调用 |
| 预检 | cookie/当日已发/预算/有效作品/锁 | `tools/preflight.py` 的 `check_cookie/check_already_ran/check_budget/check_active_book/acquire_lock` | 调度器进程内调用，锁路径与 n8n 共用（`n8n_tmp/<db>.lock`），过渡期互斥 |
| 预检通过? | 分支 | Python `if` | 预检失败 → 显式 failed 留痕，不进入生成 |
| 读当前书 | 当前活跃作品 | `tools/current_book.py`（novel_id/book_id/volume_id） | 从 novels 表 `status IN ('publishing','finishing')` 取最新 |
| 查存稿 / 存稿充足? | 存稿池判定 | `tools/check_stock.py`（stock/target/need） | need<=0 → 直接发布存稿 |
| 发布存稿 | 存稿发布三步走 | `tools/publish_stock.py`（new_article→cover_article→publish_article+校验） | 复用函数/CLI |

### 2.2 现造分支：作品资料与章节号

| n8n 节点 | 作用 | Python 等价 | 备注 |
| --- | --- | --- | --- |
| 设定题材 | 组装 premise/platform/daily/keywords/genre/book_id/book_name | `check_stock` 输出 + `current_book` 输出 | 不再从 `--premise` 参数取，改读库 |
| 查章节号 | 番茄 book_list 取章节号/书名/简介 | `publish_stock.http_form` 或新增 `fetch_book_list(env, book_id)` | `start_num = chapter_number + 1` |
| 算章节号 | 计算 start_num/meta_needed | 同上（Python 直接算） | `meta_needed = 书名为"用户*" 或 abstract<50 或书名不一致` |
| 读本地资料 / 解析本地资料 | 读记忆包 + 构造 writing_context | `tools/get_meta.py` + `build_writing_context(prev)` | 复刻 code 节点的 writing_context 拼接（17 个字段） |
| 生成作品资料 / 解析作品资料 | work_meta agent 生成书名/简介/主角/分类 | `agent_tool_loop.run("生成作品资料", task)` + 解析 | 分类映射（都市124/玄幻258/科幻8/悬疑10/历史273/默认259） |
| 需要更新作品资料? | meta_needed 分支 | Python `if` | true → 提交作品资料；false → 跳过 |
| 提交作品资料 / 过桥 | modify_book 保存简介/主角/标签 | `publish_stock.http_form` POST modify_book（字段见 n8n bodyParameters） | 失败仅记录 `modify_result`，不阻塞主线 |

### 2.3 大纲与守护

| n8n 节点 | 作用 | Python 等价 | 备注 |
| --- | --- | --- | --- |
| Planner出大纲 / 解析大纲 | planner agent 出两章细纲 + bible | `agent_tool_loop.run("Planner出大纲", task)` + `parse_planner_outline` | 复刻容错 JSON 解析；章纲不足 2 章显式报错；bible 合并（角色/关系/规则增量）；写 `n8n_tmp/bible.json` |
| 初始化设定知识库 | bible 灌入设定知识库 | `tools/novel_knowledge.py --sync-bible n8n_tmp/bible.json` | 保持 subprocess |
| 守护细纲 / 解析守护 | guard agent 检查设定一致性 | `agent_tool_loop.run("守护细纲", task)` + 解析 | 输出 constraints/character_beats；解析失败降级为空，不阻塞 |

### 2.4 A/B 双轨生成

| n8n 节点 | 作用 | Python 等价 | 备注 |
| --- | --- | --- | --- |
| 写手A / 写手B | 按章纲写正文 | `agent_tool_loop.run("写手A"\|"写手B", task, target_words=...)` | task 复刻节点表达式（主角/情绪/定位/章纲/角色卡/守护约束/前情） |
| 润色A / 润色B | 去 AI 味润色 | `agent_tool_loop.run("润色A"\|"润色B", ...)` | 初稿来自写手输出 |
| 审稿A / 审稿B | 逻辑审稿 | `agent_tool_loop.run("审稿A"\|"审稿B", ...)` | B 轨额外带上 A 章结尾 300 字核对承接 |
| 读者审稿A / B | 读者视角 | `agent_tool_loop.run("读者审稿A"\|"读者审稿B", ...)` | 缺失时质量门降级通过（复刻） |
| 主编终审A / B | 主编裁决 | `agent_tool_loop.run("主编终审A"\|"主编终审B", ...)` | 缺失时按双审降级（复刻） |
| 质量门A / B | 机械质量判定 | `build_quality_gate(track)` | 复刻：AI 高频词（ai_words.json）、突然×1、感叹号×8、省略号×5、连续问号感叹号、字数≥75%目标；reader/editor 判定；失败返回 `passed:false, errors[]` |
| 提炼剧情A / B + 整理剧情A / B | memory agent 提炼 summary | `agent_tool_loop.run("提炼剧情A"\|"提炼剧情B", ...)` + 解析 | summary 默认结构 `{summary, character_updates, plot_events, foreshadowing_planted, foreshadowing_recovered}` |
| 排版A / B | 正文转 HTML | `publish_stock.to_html(text)` | 段落拆分规则一致（单段按 80 字 + 标点切分） |

### 2.5 发布链（现造路径）

| n8n 节点 | 作用 | Python 等价 | 备注 |
| --- | --- | --- | --- |
| 新建草稿A/B | new_article 拿 item_id | `publish_stock.http_form` | 字段完全一致（book_id/need_reuse/aid/app_name） |
| 解析草稿A/B | 组装标题/卷/内容 | `build_draft_payload(track)` | 标题 `第 N 章 + 去前缀`, start_num 递增；volume 从 new_article 响应取 |
| 保存内容A/B | cover_article 存正文 | `publish_stock.http_form` | |
| 提交发布A/B | publish_article 提交审核 | `publish_stock.http_form` | 含 use_ai=2/timer_status=0 等全字段 |
| 校验发布A/B | 校验 code==0 | `parse_publish_response` | 失败记 `published:false,error`，该章留 reviewed/draft |
| 复核发布A/B + 解析复核A/B | chapter_list 复核 | `publish_stock` 内置 best-effort 校验 | 找不到仅告警不阻塞 |

### 2.6 汇总与收尾

| n8n 节点 | 作用 | Python 等价 | 备注 |
| --- | --- | --- | --- |
| 合并兜底 / 非空兜底 | 汇总双轨结果防空 | `build_payload(...)`（见补偿逻辑） | 不再需要 n8n 节点，逻辑并入调度器 |
| 汇总运行结果 | 构造 daily_result payload + costs | `build_payload(...)` | run_id=`<execution_id>-<book_id>` 改为 `scheduler-<ts>-<book_id>`；写 `n8n_tmp/daily_result.json` |
| 记录作品资料 | 落库 novel/chapters/summaries/costs | `tools/record_work.py --file n8n_tmp/daily_result.json` | 复用 CLI，幂等（按 novel_id+seq upsert） |
| 采集阅读数据 | 阅读反馈 | `tools/collect_reader_stats.py --db demo.db` | 保持 subprocess |
| 全员写日记 | daily 日记 | `tools/write_diaries.py --mode daily --db demo.db --novel-id N` | 保持 subprocess |
| 同步设定知识库 | 设定知识库同步 | `tools/novel_knowledge.py --sync-latest --db demo.db` | 保持 subprocess |
| 回填行动项 | 周会行动项回填 | `tools/auto_fill_actions.py --db demo.db` | 保持 subprocess |
| 结束 | 释放锁 | `preflight.release_lock`（进程内 finally） | 所有退出路径必须释放 |
| 失败留痕 | LLM/链路失败记录 | 调度器异常捕获 → `failed_nodes`/`error` 落 `daily_runs` + audit | 复刻 `llm_failure` 语义 |

## 3. 补偿逻辑清单（必须逐条等价）

| # | n8n 补偿 | 语义 | 调度器实现 |
| --- | --- | --- | --- |
| K1 | 质量门失败 | 该轨章不发布，状态 draft + error（质量门未通过: ...），正文仍落库 | 同：payload.chapters 状态 draft，quality_passed=false |
| K2 | 失败留痕补位 | 任何 LLM/链路失败时，未覆盖的轨补 draft+error 行，防止章节静默消失 | 同：异常捕获后按轨补记录 |
| K3 | 读者/主编审缺失降级 | reader/editor 缺失时按 `review.passed` 降级 | 同 |
| K4 | 发布失败 | 章状态 reviewed（非 published），error 记录，次日可补发 | 同 |
| K5 | 质量门通过但草稿/发布链中断 | 补 draft+error「质量门通过但草稿创建/发布链中断」 | 同 |
| K6 | 过桥 | modify_book 失败只记录不阻塞 | 同 |
| K7 | 守护解析失败 | guard 输出降级为空约束 | 同 |
| K8 | 空内容兜底 | 润色正文为空 → 质量门失败 | 同 |
| K9 | 标题序号 | 从番茄 chapter_number+1 起，章号不重复 | 同 |
| K10 | 锁 | 原子锁 + 2h 陈旧回收 + 全路径释放 | 复用 `preflight.acquire_lock/release_lock`，与 n8n 共用锁文件 |

## 4. 状态机映射

| n8n 隐式状态 | 调度器 daily_runs.status | 判定 |
| --- | --- | --- |
| 预检拦截 | failed | 无产出，error=reasons |
| 全部发布成功 | completed | published == target 且无 failed_nodes |
| 部分发布/部分失败 | partial | published>0 且 published<target，或有 failed_nodes 但仍有产出 |
| 整批失败无产出 | failed | published==0 且存在失败 |
| 运行中 | running | started_at 已写、finished_at 为空 |

## 5. 面板控制依赖清单（阶段 B 改造）

| 依赖点 | 现状 | 改造后 |
| --- | --- | --- |
| `run_now` | POST n8n webhook | 调 `editorial_daily.daily(trigger="manual")` |
| `apply_schedule` | 改 n8n scheduleTrigger + deploy | 改 Windows 计划任务（`install_daily_task.ps1`） |
| `pause/resume` | n8n workflow activate/deactivate | 读写 `daily_enabled` 开关 |
| `load_control` | n8n workflow_status×3 | 调度器状态 + 计划任务状态 |
| `daily_runs.sync_from_n8n` | 读 n8n execution_entity | 主路径调度器自写；n8n 同步保留为 legacy 兼容 |
| `watch_daily.py` | 读 n8n execution | 退役或改读 daily_runs |
| 开机自启 | n8n + web_api | 仅 web_api；n8n 归档可手动回退 |

## 6. 验收标准（阶段 A）

- `python run_tests.py` 全绿（202 旧 + 新增调度器测试）
- dry-run（mock LLM + 临时库）全链跑通：预检→存稿/现造→双轨→发布→汇总→收尾
- 四态推导与锁并发测试通过
- `node tools/validate_workflow_deep.mjs` 保持全绿（n8n JSON 零改动）
