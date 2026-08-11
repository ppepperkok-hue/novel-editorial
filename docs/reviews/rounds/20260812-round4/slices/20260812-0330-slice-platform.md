本 slice 存在 1 个 P1（record_work 对已存在 quality_reports 的章节重录时抛 IndexError，导致记录环节数据丢失/假绿）与 2 个 P2（publish_batch 完结后超额发布；uv.lock 与 pyproject 声明不同步导致 uv sync 失败）。基线：全部 slice 文件 compileall 通过、8 个 PowerShell 脚本 Parser 通过、40 个针对性测试全绿，但真实复现路径均未被测试覆盖。修复上述阻塞项前不应视为可交付。

Full review comments:

- [P1] record_work 二次记录同一章时 qrow["scores"] 抛 IndexError — E:\code\novel-editorial\tools\record_work.py:315-322
  tools/record_work.py:315-322 中 `qrow = conn.execute("SELECT id FROM quality_reports ...")` 只 SELECT 了 `id` 列，随后 `json.loads(qrow["scores"] or "{}")` 在 qrow 非空时必然抛 `IndexError: No item with that key`（该异常不在 `except (TypeError, json.JSONDecodeError)` 捕获范围内）。复现：对同一章带 `quality_passed` 的 payload 连续调用两次 `record_payload`，第二次即崩溃（实测输出 `IndexError: No item with that key` at record_work.py:322）；demo.db 中 chapters 1/2 已存在 quality_reports 行（`{"gate": 1}`），因此同一章节的任何重跑（同日手动重跑、n8n 节点重试、失败后补跑）都会命中。在 de-n8n 路径中 editorial_daily.py:1582 经 `_run_tool` 捕获后仅记 warning（editorial_daily.py:455-457），本 run 的章节内容/摘要/发布日志/成本（含 run_id 幂等）全部丢失，表现为“假绿”；n8n 路径则直接节点报错。修复应改为 `SELECT id, scores` 或对缺失键兜底。

- [P2] publish_batch 在书已标记 finished 后仍继续发布超额章节 — E:\code\novel-editorial\tools\publish_stock.py:290-311
  tools/publish_stock.py:290-311 中 `remaining` 减到 0 时会把 novels.status 置为 'finished' 并写入 `daily_enabled=false`，但外层 `for ch in rows`（263 行）没有 break，`if remaining > 0` 分支之后的章节仍照常 `status='published'` 并插入 publish_logs。复现：finish_remaining=1、target=3、存稿池 3 章时，3 章全部发布成功，novel 在第 1 章后即被标为 finished，第 2、3 章在完结之后仍被发布（实测输出：published=3，novels.status='finished'，chapters 1-3 全部 published）。当收尾书剩余章数小于当日发布目标（editorial_daily.py:1678 同样调用此函数）时，番茄后台上会出现超出计划完结点的章节。应在 remaining 归零后终止循环。

- [P2] pyproject 声明 websocket-client 但 uv.lock 未更新，uv sync 会失败 — E:\code\novel-editorial\pyproject.toml:10-10
  pyproject.toml:10 已声明 `dependencies = ["websocket-client>=1.0"]`，但 uv.lock（最后更新 2026-08-11 23:27，早于该改动）中 novel-editorial 条目（170-187 行）的 requires-dist 只含 pywebview，没有 websocket-client。实测 `uv lock --check` 输出 "The lockfile at `uv.lock` needs to be updated"（exit=1），即全新环境 `uv sync` 会直接报错；项目 .venv 中 `import websocket` 实测 `ModuleNotFoundError`（仅系统 Python 有 1.9.0），因此 scripts/inject_fanqie_cookie.py 在项目虚拟环境中无法运行。需要 `uv lock` 重新生成锁文件并同步安装依赖。

- [P3] n8n_api.py 模块级读取 N8N_TMP_PW，未加载 ~/.n8n/.env 且报错无提示 — E:\code\novel-editorial\tools\n8n_api.py:7-9
  tools/n8n_api.py:9 在模块导入时执行 `PASSWORD = os.environ["N8N_TMP_PW"]`，未设置时直接抛裸 `KeyError: 'N8N_TMP_PW'`（实测复现），且不像 preflight.py/collect_reader_stats.py 那样先经 `load_env`/`config.load_env()` 读取 `~/.n8n/.env`（config.N8N_ENV_FILE），用户按 .env.example 把 N8N_TMP_PW 写进该文件后仍无法直接运行 `python tools/n8n_api.py list`。建议改用 `config.env_value("N8N_TMP_PW")` 并给出可读错误信息。

- [P3] watch_daily.py 在 daily_runs 无记录时访问 exec['status'] 抛 KeyError — E:\code\novel-editorial\scripts\watch_daily.py:21-22
  scripts/watch_daily.py:21-22 中 `latest = dict(row) if row else {}` 后只补了 `latest["id"]` 键，而 main() 第 69-70 行直接读 `s['exec']['status']`；数据库没有任何 daily_runs 行（如全新 demo.db 或清库后）时第一次循环即抛 `KeyError: 'status'`。另外 `cost_today` 在 cost_logs 为空时打印 None。建议对空快照给默认值 `{"id": None, "status": "none"}`。

- [P3] install_daily_task.ps1 -Remove 不检查 schtasks 退出码，误报删除成功 — E:\code\novel-editorial\scripts\install_daily_task.ps1:33-34
  scripts/install_daily_task.ps1:33-34 执行 `schtasks /Delete /TN $TaskName /F | Out-Null` 后未检查 `$LASTEXITCODE`，任务不存在时 schtasks 返回非零，脚本仍输出“已删除计划任务 $TaskName”并 exit 0，属静默失败。建议校验退出码并区分“已删除/不存在”两种结果。

- [P3] 遗留重命名脚本硬编码 E:\code 绝对路径且已完成使命，建议归档 — E:\code\novel-editorial\scripts\finish_rename.ps1:15-18
  scripts/finish_rename.ps1:15-18 与 scripts/rename_on_login.ps1:13-15 硬编码 `E:\code\novel-pipeline` / `E:\code\novel-editorial`，目录重命名早已完成（git 记录 2959d2c），任何其他机器或再次执行都会误操作或空转；rename_on_login.ps1 还依赖 RunOnce 注册。作为一次性迁移脚本建议移入 docs/legacy 或删除，避免后续被当作现役脚本使用。
