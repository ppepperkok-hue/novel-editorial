# Phase 1 运行手册（半自动 → 自动日更）

> 配套代码：[novel-pipeline](novel-pipeline/README.md)　|　适用平台：番茄小说（首选）

---

## 0. 前置清单

- [ ] 番茄小号已注册、完成实名
- [ ] 每月 API 预算已定（入门档约 ¥10-60/月，日更两章）
- [ ] 已选模型：DeepSeek / OpenAI 兼容任意一家
- [ ] 已读《平台规则清单.md》，确认 AI 标注与红线要求

---

## 1. 安装与配置

```bash
cd outputs/novel-pipeline
pip install -e .          # 可选，装成包
python run_tests.py       # 应显示 29+ 个测试全绿
```

复制 `.env.example` 为 `.env` 并填写：

```text
LLM_API_KEY=你的密钥
LLM_BASE_URL=https://api.deepseek.com/v1   # 以实际服务商为准
LLM_MODEL_PLANNING=deepseek-chat
LLM_MODEL_WRITING=deepseek-chat            # 写作档用最强模型
LLM_MODEL_EDITING=deepseek-chat
LLM_MODEL_REVIEWING=deepseek-chat
LLM_MODEL_MEMORY=deepseek-chat
```

Windows PowerShell 里导入环境变量后即可试跑。

---

## 2. 首次试跑（建议按顺序）

先出大纲，人工过目：

```bash
python -m novel_pipeline.planner --premise "林舟重生回到高考前三个月。" --chapters 10
```

再生成一章看质量：

```bash
python -m novel_pipeline.pipeline --generate --db novel.db
```

最后跑完整连载（建议先 3-5 章）：

```bash
python -m novel_pipeline.novel_flow --premise "林舟重生回到高考前三个月。" --chapters 5 --db novel.db
```

**半自动阶段原则**：每章发布前人工过目，重点看人设、剧情走向、AI 味。

---

## 3. 番茄发布接入

1. 浏览器登录 [fanqienovel.com](https://fanqienovel.com) 作家后台。
2. F12 → Network，任选一个 `/api/author/...` 请求，复制 `Cookie` 和 `X-Secsdk-Csrf-Token`。
3. 写入环境变量 `TOMATO_COOKIE` / `TOMATO_CSRF_TOKEN`（约 1-2 个月失效）。
4. 生产发布建议复用开源 [tomato-writer-mcp](https://github.com/fuhei/tomato-writer-mcp)
   的 `publish_chapter`，把 `FanqieHttpAdapter` 从 stub 换成真实调用。
5. 发布时如实勾选「含 AI 生成内容」声明，遵守平台标注要求。

---

## 4. 日更自动化

一条命令跑完「生成 → 双门 → 发布调度 → 健康检查」：

```bash
python -m novel_pipeline.autopilot --premise "林舟重生回到高考前三个月。" --chapters 5 --daily 2 --db novel.db
```

注册 Windows 计划任务（每天定时跑）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_daily_task.ps1 `
  -Premise "林舟重生回到高考前三个月。" -Chapters 5 -Daily 2 -Time "08:00"
```

先加 `-DryRun` 查看命令，确认无误再去掉注册。删除任务：

```powershell
schtasks /Delete /TN NovelPipelineDaily /F
```

**注意**：日更量与存稿池联动——每日发布数必须 ≤ 当日新增存稿，
否则 `autopilot` 会返回「断更预警」，健康检查不通过。

---

## 5. 质量门与审稿

- 五维评分：字数 / 情节 / 文笔 / 规范 / 衔接，总分 ≥ 7 且单维 ≥ 5 才通过。
- LLM 审稿不过时自动重写，最多 3 轮，轮数记入 `quality_reports.revision_count`。
- 仍不达标的章节状态保持 `draft`，需要人工介入，不会误发。

---

## 6. 监控与告警

```bash
python -m novel_pipeline.monitor --db novel.db --spent 12.5 --budget 100
```

检查项：Cookie 失效 / 存稿池低于安全线 / 发布失败 / 成本超限。
告警写进 `alerts.log`，接入企业微信 / Telegram 只需替换 `AlertSink.send()`。

### 6.1 实时监控面板

```bash
python -m novel_pipeline.web_api --db novel.db --port 8000
```

浏览器打开 `http://127.0.0.1:8000/`：总览卡片、章节状态、发布日志、
健康问题、完读率柱图、热点选题，每 5 秒自动刷新。

### 6.2 热点选题

```bash
python -m novel_pipeline.hot_topics --refresh
```

抓取公开网文榜单（起点/番茄）并写 `hot_topics.json`；抓不到时用 CSV 兜底：

```bash
python -m novel_pipeline.hot_topics --from-csv topics.csv
```

热点关键词会显示在监控面板，也可作为 Planner 选题候选。

---

## 7. 数据反馈闭环

1. 从番茄后台导出各章完读率 / 追读率，整理为 CSV：

```text
chapter,finish_rate,follow_rate
1,0.28,0.41
2,0.15,0.22
```

2. 跑反馈分析：

```bash
python -m novel_pipeline.data_feedback --file reader_stats.csv
```

3. 低于阈值的章节反查大纲节奏与钩子，调整后续章纲；题材整体低迷则换选题。

---

## 8. 备份

```bash
python -m novel_pipeline.backup --db novel.db --backup-dir backups --keep 3
```

每次自动保留最近 3 份数据库，旧备份自动清理。

---

## 9. 合规红线（随时自查）

- 如实声明 AI 生成内容；平台在严打「批量低质 AI 文」。
- 先小号试错，别拿主号冒险。
- 不做水化、堆砌；敏感词库按平台规则清单维护。

---

## 10. Phase 1 验收标准

- 连续 10-20 章过质量门，通过率 ≥ 95%
- 平台审核过审率 100%
- 单章人工耗时 < 15 分钟
- 已记录完读率 / 追读率基线，供 Phase 3 对比
- 连续 7 天无人值守自动日更成功，断更率 0
