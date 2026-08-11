验证完毕。所有 finding 都有了执行级证据，demo.db 也已恢复到污染前的精确状态（`review_tmp.db` 副本，逐表核对一致）。

**审查结论汇总**

Scope：`tools/publish_stock.py / create_book.py / check_stock.py / get_meta.py / record_work.py / delete_book.py / collect_reader_stats.py / current_book.py / preflight.py / release_lock.py / n8n_api.py`、`scripts/*`、`pyproject.toml`、`launch_desktop.vbs`；依赖契约只核对了 `novel_editorial/db.py、config.py、services/{audit,ending,activity}.py、data_feedback.py、tools/{app_settings,novel_knowledge}.py` 与调度器的调用点。

Baseline：`python -m compileall` 全数通过；`current_book/check_stock/get_meta/preflight/publish_stock/delete_book/release_lock/watch_daily` 离线路径全部按预期运行（preflight 无凭据时快速失败、publish_stock 空池返回 warning、delete_book 无确认即拒绝）。未跑完整测试套件（按分片要求）。

```json
{
  "findings": [
    {
      "title": "[P2] create_book 的 _gender 把「仙侠言情」永远判为男频",
      "body": "tools/create_book.py:93-96：`_gender()` 要求命中女频词且不含任何男频关键词，但 `_MALE_KEYWORDS`（第 56 行）含「仙侠」，而 `_FEMALE_GENRES`（第 55 行）显式列出的「仙侠言情」必然同时命中「仙侠」→ 女频分支不可达。已实测 `_gender('仙侠言情')` 返回 1。番茄上仙侠言情属女频，按此建书会以 gender=1 发到男频频道，作品分类错误且建书不可重试（每天限 1 本）。同类问题还影响「都市言情」这类含男频词的题材。",
      "confidence_score": 0.95,
      "priority": 2,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\create_book.py",
        "line_range": {"start": 93, "end": 96}
      }
    },
    {
      "title": "[P3] collect_reader_stats 从环境变量读 FANQIE_BOOK_ID，与 current_book 的 DB 权威设计矛盾",
      "body": "tools/collect_reader_stats.py:93 用 `os.environ.get(\"FANQIE_BOOK_ID\")` 取书，而 tools/current_book.py 的 docstring 明确说明环境变量在 bind_book/create_book 更新 ~/.n8n/.env 后不会刷新、DB 才是权威。长驻进程（如 web_api 面板进程）里 `os.environ.setdefault` 不会覆盖旧值，换书后 `_wrapup` 调用的 `collect_reader_stats.run(db_path)`（env_file=None，只读 os.environ）会继续抓旧书的完读/追读率写入 reader_stats.csv，把错误反馈喂给 get_meta。建议改为从 DB 活动书读取。",
      "confidence_score": 0.8,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\collect_reader_stats.py",
        "line_range": {"start": 86, "end": 93}
      }
    },
    {
      "title": "[P3] record_work CLI 硬编码 demo.db，缺少 --db 参数",
      "body": "tools/record_work.py:15 与 :475 的 `main()` 无条件 `db.connect(DB_PATH)`（ROOT/demo.db），与同批工具（publish_stock/check_stock/current_book/get_meta 等均支持 --db）不一致。实测：用 `--file` 验证时 payload 直接写入了真实 demo.db（章节/成本/伏笔被覆盖，已从测试前副本逐表核对恢复）。手动测试或指向其他库时无任何提示，属于容易踩的静默副作用。",
      "confidence_score": 0.9,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\record_work.py",
        "line_range": {"start": 15, "end": 15}
      }
    },
    {
      "title": "[P3] preflight.py 的 --no-lock 参数声明后从未被读取",
      "body": "tools/preflight.py:212 声明 `--no-lock`（帮助文案暗示 CLI 会持锁），但 `main()` 全程只读 args.env_file/args.db/args.budget，从未读 args.no_lock，且按设计 CLI 从不获取锁（见 main 注释）。传不传该参数行为完全一致，会误导使用者以为默认会持锁、加了才不锁；建议删除或真正接入 acquire_lock。",
      "confidence_score": 0.95,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\preflight.py",
        "line_range": {"start": 210, "end": 214}
      }
    },
    {
      "title": "[P3] install_autostart.ps1 用 ASCII 写 VBS，非 ASCII 路径会被替换为 ?",
      "body": "scripts/install_autostart.ps1:103 `Set-Content -Encoding ASCII` 把含 `$PipelineRoot` 的 VBS 以 ASCII 写出；当仓库/用户名路径含中文等非 ASCII 字符时（本仓库面向中文用户），路径中的字符被替换为 '?'，生成的 NovelEditorial-api.vbs 指向错误路径，开机自启的 web_api 静默起不来。应以 UTF-8（无 BOM）写 VBS。",
      "confidence_score": 0.8,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\scripts\\install_autostart.ps1",
        "line_range": {"start": 103, "end": 103}
      }
    },
    {
      "title": "[P3] 当前 .venv 缺 websocket-client，inject_fanqie_cookie.py 无法运行",
      "body": "pyproject.toml:10 声明 `websocket-client>=1.0`，uv.lock 已锁定 1.9.0，但本机 .venv 实测 `import websocket` 抛 ModuleNotFoundError（site-packages 中无该包）。scripts/inject_fanqie_cookie.py 模块级 `import websocket` 会直接失败。环境与锁文件不同步，`uv sync` 即可修复；若部署机也沿用旧 venv，该 cookie 注入脚本会静默不可用。",
      "confidence_score": 0.95,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\pyproject.toml",
        "line_range": {"start": 10, "end": 10}
      }
    }
  ],
  "overall_correctness": "patch is correct",
  "overall_explanation": "分片内无 P0/P1 阻断问题：compileall 全过，各工具离线路径行为符合预期，round4 引入的改动（publish_batch 完结即 break、record_work 幂等 scores、n8n_api 惰性凭据、watch_daily 空快照）经核对均正确。6 个 finding 均为 P2/P3 非阻断项，其中 create_book 的性别判定是唯一功能性错误，建议随下次迭代修复。审查期间 record_work CLI 硬编码 demo.db 导致一次测试写入真实库，已从测试前精确副本恢复并逐表核对一致。",
  "overall_confidence_score": 0.85
}
```
