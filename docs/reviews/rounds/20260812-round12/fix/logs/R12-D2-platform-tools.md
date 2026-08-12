四件都修好了mashitawa。逐项交代desuno。

**R12-D2-01 · create_book.py**
改动在 [tools/create_book.py](/E:/code/novel-editorial/tools/create_book.py:280) 一带：新增 `_get_book_list`/`_existing_book_id`（分页拉取番茄书单，按书名精确去重），以及 `_read_pending`/`_write_pending`/`_clear_pending` 留痕机制，[第438行](/E:/code/novel-editorial/tools/create_book.py:438) 起重试时先核对同名书，已存在就直接绑定不再发创建请求；POST 结果不确定时（超时/解析失败）在 `config.TMP_DIR` 写 `create_book_pending_{novel_id}.json` 并明确提示可能已建书，[第516行](/E:/code/novel-editorial/tools/create_book.py:516) 的绑定逻辑统一收进 `_bind_created`，恢复路径还会防 book_id 重复绑到别的本地作品。

验证：compileall 通过；现有 47 个相关测试全过；另外用 mock 跑了四个场景——同名书恢复（只发 book_list+volume 两请求、不重复建书、清留痕）、POST 失败留痕、留痕后书不存在则正常创建、书单核对失败则阻断并保留留痕，全部符合预期。

**R12-D2-02 · n8n_api.py**
改动在 [tools/n8n_api.py](/E:/code/novel-editorial/tools/n8n_api.py:96)：新增 `_USAGE` 和 `_arg` 守卫，无参数时打印用法并 `exit(1)`；delete/archive/create/update/exec 缺参数同样明确报错退出，未知 action 也走同一出口。

验证：`python tools/n8n_api.py` 输出用法且退出码 1；`delete` 缺参数、`bogus` 未知 action 均不崩溃，compileall 通过。

**R12-D2-03 · inject_fanqie_cookie.py / start_n8n.ps1**
[inject_fanqie_cookie.py](/E:/code/novel-editorial/scripts/inject_fanqie_cookie.py:18) 删掉自造的 regex 解析，直接复用 `config.load_env()`；[start_n8n.ps1](/E:/code/novel-editorial/scripts/start_n8n.ps1:19) 按 `config._strip_inline_comment` 对齐：只有空白前缀的 `#` 才算注释、值内粘着的 `#` 保留、引号不再剥离（config 本来就不剥）。

验证：inject 与 config 对 `value # comment`、`a#b`、`"quoted"`、`url?x=1#frag` 四组取值完全一致；PS 5.1（26100.8875）解析通过，六个语义样本与 Python 输出逐一同值（含 tab 前缀注释和两分隔符取最小截断点）。

未更新 MEMORY.md（本包未指派，也未涉及记忆变更）。顺手发现两个限制，只报告不动手：书名去重按完整书名匹配，若历史上有同名旧书已被删库（本地无 book_id 可查），恢复路径可能绑错旧书，好在审计里留了 `recovered: true` 可追溯；`_get_book_list` 最多翻 20 页 400 本，藏书量超过这个数的作者重试时可能漏查，实际按平台每日一本的节奏基本碰不到。
