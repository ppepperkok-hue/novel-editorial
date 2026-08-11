修好了mashitawa。三个文件都只动了指派范围内的地方，git 没碰，别的并行 Agent 的改动我也没动。

第一件，`scripts/_run_fix_worker.ps1`（31-62 行）。任务文本不再拼进命令行，而是写进 `GetTempFileName()` 的临时文件，用 `-RedirectStandardInput` 喂给 node，参数末尾挂 `-` 让 codex 从 stdin 读；原来 15000 字符的长度检查和换行折叠一并删了，finally 里确保临时文件用完即删。验证：PowerShell 5.1（5.1.26100.8875）解析通过；我用假 codex.js 实测了一次派发——任务文本是含双引号、中文、换行的原文，退出码 0，argv 收到 `codex.js|exec|--ephemeral|-m|gpt-5-mini|-`，stdin 与原文完全一致，临时目录零残留。

第二件，`tools/n8n_api.py`。`_open`（63-71 行）不再手工塞 Cookie 头，完全交给 CookieJar；原来缓存裸 token 的 `_token_cache` 换成 `_login_at` 时间戳加 30 分钟 TTL（21-22 行），过期自动重登；`_login`（38-52 行）改为校验登录响应的 Set-Cookie 头，`request`（75-93 行）在 401/403 时清空 jar、重登一次再重试。验证：compileall 通过；mock 四个场景全绿——请求头里没有 Cookie、POST 才带 Content-type、401 后恰好重登一次并成功、TTL 过期强制重登、无 Set-Cookie 时抛 RuntimeError。

第三件，`tools/delete_book.py`（73-103 行）。在按 `ref_novel_id` 删除之前，从本书拥有的消息出发，沿 `reply_to` 递归收拢 ref_novel_id/ref_chapter_id 全 0 的回复链后代一起删；不会误删 ref 指向其他书的消息，也不碰 reply_to 指向不存在消息的孤儿。验证：compileall 通过；现有 8 个 delete_book 测试全绿；冒烟测试里 parent→child→grand 三层链全清，另一本书的消息和无关孤儿都保留。

额外发现，只报告不改：`tests/test_delete_book.py` 缺回复链用例，建议补三层链加无关消息保留的用例；`n8n_api.py` 没有测试文件，建议按我 mock 的那四个场景补一份；`_login` 的 Set-Cookie 校验依赖真实 urllib 响应头，假响应需要实现 `get_all`。另外 `run_fix_batch.ps1` 的 DryRun 提示文本本来就是 `exec --ephemeral - < $task`，跟新行为对上了desuwa。

一点限制说清楚：n8n 那部分没有真实 n8n 服务可连，是 mock 验证；ps1 的派发实测用的是假 codex，真实 codex 的 stdin 读取行为以 CLI 自身为准。MEMORY.md 不在本次指派范围，我没动它teyo。
