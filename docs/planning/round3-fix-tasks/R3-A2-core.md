# 修复任务包 · R3-A2 核心根

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第三轮分片审查修复，审查报告原文：`docs/reviews/20260812-0225-slices-summary.md`（可读确认细节）。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `novel_editorial/monitor.py`
- `novel_editorial/scheduler.py`
- `novel_editorial/seed_demo.py`
- `novel_editorial/web_api.py`

## 修复项

### R3-A2-01（P3）monitor.py:36-42
现状：`run_checks` 部分凭据场景不加载 .env，导致误报 Cookie/CSRF 缺失。
期望：检查前确保已加载 .env（幂等，参考项目其他模块的加载方式）；缺失时按真实状态报告。

### R3-A2-02（P3）scheduler.py:46
现状：`tick` 未注入时钟时 date 字段为字符串「None」。
期望：未注入时钟时用真实当前日期，date 字段永远是真日期。

### R3-A2-03（P3）seed_demo.py:21-26
现状：`seed` 在 published+reviewed 超过 chapters 时产生负数 draft，导致状态错位。
期望：draft 计算 clamp 到 >=0，总章数不越界。

### R3-A2-04（P3）web_api.py 两处
a) 645-647 行：do_POST 对垃圾 Content-Length 头抛 500 而非 400。期望：解析失败返回 400/422 结构化错误，不 500。
b) 731-739 行：/api/agent_actions/create 的 session_id/meeting_id 未做整数清洗，非数字 payload 返回 500。期望：整数清洗/校验，非法输入返回 400 并带错误信息。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：
  - `python -m compileall novel_editorial/monitor.py novel_editorial/scheduler.py novel_editorial/seed_demo.py novel_editorial/web_api.py`
  - 用 `rg` 找 tests 中引用 monitor/scheduler/seed_demo/web_api 的测试，`python -m pytest <相关测试文件> -q` 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
