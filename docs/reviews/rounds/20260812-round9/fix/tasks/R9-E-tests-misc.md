# 修复任务包 · R9-E 测试与杂项

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第九轮审查修复（新发现 + 第八轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round9/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tests/test_meeting_session.py`
- `tests/test_ai_taste_check.py`
- `novel_editorial/services/ending.py`
- `tools/editorial_steps.py`
- `webapp/src/components/Shell.jsx`

## 修复项

### R9-E-01（P3，新）test_meeting_session.py:151-154
现状：test_meeting_malformed_agency_does_not_crash 使用恒真断言 assertTrue(True)。
期望：改为真实断言（malformed agency 输入下不崩溃且有明确行为/返回）。

### R9-E-02（P3，新）test_ai_taste_check.py
现状：仅 2 个测试，detect() 大部分分支无覆盖。
期望：补 detect 主要分支用例（空文本、非重叠计数、flowery/filler、类型异常输入），覆盖密度与明细口径。

### R9-E-03（遗留）ending.py
现状：仍写 FANQIE_VOLUME_ID（模板已弃用，死写）。
期望：移除死写（或改为不再写该键），与 .env.example 弃用一致。

### R9-E-04（遗留）editorial_steps.py
现状：DEFAULT_FLAVOR_WORDS 无权威来源标注（与 quality_gate/ai_words.json 同族漂移风险）。
期望：加注释声明唯一权威来源为 ai_words.json（与 quality_gate 一致），或改为运行时读取。

### R9-E-05（新，R9-B 半修跟进）Shell.jsx:172
现状：帮助弹窗文案仍写「1 – 12」，实际数字键只能直达 1–9；侧边栏调度器状态只有「在线/离线」两态，轮询失败无法区分。
期望：文案改为 1–9 并补充「其余入口走侧边栏或 Ctrl+K」；侧边栏增加「连接异常」态（轮询失败时与离线区分）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 本组允许修改 tests/ 下指派测试文件。
- 验证：`python -m compileall novel_editorial/services/ending.py tools/editorial_steps.py`；`python -m pytest tests/test_meeting_session.py tests/test_ai_taste_check.py -q`；在 webapp 目录 `npx vitest run` 与 `npm run build`。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
