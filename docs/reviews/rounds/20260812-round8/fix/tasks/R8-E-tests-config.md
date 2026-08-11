# 修复任务包 · R8-E 测试配置与打包

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第八轮审查修复（新发现 + 遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round8/slices/slices-summary.md`；第七轮总结遗留节：`docs/reviews/rounds/20260812-round7/00-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `README.md`
- `run_tests.py`
- `ai_words.json`
- `desktop/package.json`
- `.env.example`

## 修复项

### R8-E-01（P3，新）README.md:19
现状：测试数量写 448 个，实际 487 个。
期望：更新为当前真实数量（注明以 run_tests.py 输出为准）。

### R8-E-02（P3，新）run_tests.py:18
现状：测试输出被被测代码的 print 污染。
期望：TextTestRunner 开 buffer=True，输出干净。

### R8-E-03（P3，新）ai_words.json
现状：n8n 工作流硬编码 AI 味词表与 ai_words.json 存在同步漂移风险。
期望：把 n8n 工作流 JSON 内的词表与 ai_words.json 同步（若工作流文件不在本组，则说明位置并列出差异）；或加注释说明唯一权威来源。

### R8-E-04（遗留）desktop/package.json
现状：tools/archive 与 __pycache__ 仍随 tools/** 进包（建议白名单）。
期望：extraResources 过滤改为白名单（只打包需要运行的工具文件），排除 archive/__pycache__/chrome-profile。

### R8-E-05（遗留）.env.example
现状：FANQIE_VOLUME_ID 只有写入方无读取方，疑似死配置。
期望：确认无消费后移除或标注已弃用（与代码实际消费一致）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 验证：`python run_tests.py` 全绿且输出无污染；README/.env.example 人工核对；package.json JSON 校验。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
