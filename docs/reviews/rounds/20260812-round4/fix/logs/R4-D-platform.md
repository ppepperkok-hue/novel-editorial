修完了mashitawa。七项全清，验证也跑完了，我按条目给你捋一遍desuwa。

R4-D-01，[record_work.py](E:/code/novel-editorial/tools/record_work.py:316)，把 quality_reports 的查询从只取 `id` 改成 `SELECT id, scores`，二次记录同一章时不再对缺失的 scores 键抛 IndexError，旧分数照常合并、notes 保留。复现脚本连续调用两次 record_payload，结果都是 ok，quality_reports 只有一行且 `{"gate":1}` 正确覆盖，mashitawa。

R4-D-02，[publish_stock.py](E:/code/novel-editorial/tools/publish_stock.py:307)，finish_remaining 归零、novel 标 finished 之后立即 commit 并 break，超额章节不再发布。复现场景 finish_remaining=1、target=3、存稿 3 章，现在只发 1 章，另外 2 章留在 reviewed，desuwa。

R4-D-03，[uv.lock](E:/code/novel-editorial/uv.lock:174) 跑过 `uv lock`，加入 websocket-client v1.9.0，pyproject.toml 本身没动。`uv lock --check` 和 `uv sync --dry-run` 都是退出码 0，desuno。

R4-D-04，[n8n_api.py](E:/code/novel-editorial/tools/n8n_api.py:18)，去掉模块级 `os.environ["N8N_TMP_PW"]`，改成 `_credentials()` 延迟读取 `config.load_env()`，N8N_EMAIL/N8N_TMP_PW 缺失时抛带指引的 RuntimeError。实测缺凭据时不再裸 KeyError，能从 env dict 正常取到凭据，mashitawa。

R4-D-05，[watch_daily.py](E:/code/novel-editorial/scripts/watch_daily.py:21)，空库快照默认给 `{"id": None, "status": "none"}`，实测 daily_runs 无记录时 snapshot 正常返回、不再 KeyError，desuwa。

R4-D-06，[install_daily_task.ps1](E:/code/novel-editorial/scripts/install_daily_task.ps1:38)，-Remove 现在检查 `$LASTEXITCODE`，失败输出 Write-Error 并 exit 1。实测删除不存在的任务，脚本退出码 1、错误信息可见。这里有个插曲：我第一版错误消息用了中文全角「）。」，结果 Windows PowerShell 5.1 的 ParseFile 编码探测被那串字节带偏，脚本直接解析失败；改成 ASCII 消息后解析零错误，teyo。

R4-D-07，finish_rename.ps1 已移到 [tools/archive/finish_rename.ps1](E:/code/novel-editorial/tools/archive/finish_rename.ps1)，该目录在 .gitignore 内，git 里只显示 scripts 侧删除、不跟踪归档文件，desuwa。

验证汇总：compileall 四个 Python 文件退出码 0；相关测试跑了 test_record_work、test_publish_stock、test_review_v3/v4、test_knowledge_bible、test_audit_evolution，41 个全过；PowerShell 5.1 解析零错误；没有改测试文件，也没有 git add/commit。没动 MEMORY.md，desuno。

额外发现、只报告不改：scripts/rename_on_login.ps1 还硬编码 E:\code\novel-pipeline 并注册 RunOnce，跟本次归档的 finish_rename 是同一批遗留物；README.md 第 221 行还在列 finish_rename.ps1，归档后描述过时；watch_daily 在 cost_logs 为空时 cost_today 打印 None；publish_stock 对 status='finishing' 但 finish_remaining=0 的极端数据会照单全发而不收尾；record_work.py 行尾混用 CRLF/LF，n8n_api.py 的 BASE 也还是硬编码 localhost:5678。这些都不在指派范围，我留着没动，先这么办teyo。
