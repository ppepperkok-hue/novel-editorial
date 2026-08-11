# 修复任务包 · R6-A 核心服务层

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第六轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round6/slices/slices-summary.md`（core 分片含 P1 完整复现链）。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `novel_editorial/services/control.py`
- `scripts/install_daily_task.ps1`
- `novel_editorial/services/meeting_session.py`

## 修复项

### R6-A-01（P1）control.py:280-284 + install_daily_task.ps1:28
现状：跨盘时 apply_schedule 保留绝对路径传给 ps1，ps1 无条件 Join-Path 拼出垃圾路径（如 E:\code\novel-editorial\C:\...\demo.db），计划任务注册成功但每天静默空跑；面板显示已注册（假绿灯）。
期望：ps1 先判 `[System.IO.Path]::IsPathRooted($DbPath)`，rooted 时直接用绝对路径不 Join-Path；或 control.py 恒传绝对路径且 ps1 只做 rooted 判断。修完实测：跨盘传入 C: 盘绝对路径，ps1 解析出的最终路径就是该绝对路径；同盘相对路径行为不变。

### R6-A-02（P3）meeting_session.py:330-339
现状：run_session 以空 db_path 调用时先在默认库查行内 db_path，会话不在默认库则静默漏跑、永久卡 running，且注释与实现矛盾。
期望：查找前无法定位行内库时显式报错或置 failed，绝不静默继续。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall novel_editorial/services/control.py novel_editorial/services/meeting_session.py`；用 rg 找相关测试并 pytest 运行；ps1 用 PowerShell 5.1 解析校验（不实跑注册）。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
