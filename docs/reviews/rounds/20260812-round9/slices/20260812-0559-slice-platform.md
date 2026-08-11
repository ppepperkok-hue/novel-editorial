查完了mashitawa。范围里所有文件我都过了一遍，依赖契约也对着 db.py、config.py、services 验证过，该跑的都跑了——语法编译、切片测试、真实数据的冒烟和复现实验。报告如下desuwa。

---

# 代码审查报告（platform 切片）

## 审查范围

`scripts/`（watch_daily.py、inject_fanqie_cookie.py、start_n8n.ps1、install_autostart.ps1、install_daily_task.ps1、run_fix_batch.ps1、_run_fix_worker.ps1、run_review.ps1）、`tools/publish_stock.py`、`tools/create_book.py`、`tools/check_stock.py`、`tools/get_meta.py`、`tools/record_work.py`、`tools/delete_book.py`、`tools/collect_reader_stats.py`、`tools/current_book.py`、`tools/preflight.py`、`tools/release_lock.py`、`tools/n8n_api.py`、`pyproject.toml`、`launch_desktop.vbs`。依赖接口只读了 `novel_editorial/db.py`、`config.py`、`services/audit.py`、`services/activity.py`、`services/ending.py`、`data_feedback.py`、`tools/app_settings.py`、`tools/novel_knowledge.py`、`tools/editorial_daily.py`（仅成本契约部分）。

## 基线结果

- `py_compile`：13 个 Python 目标文件全部通过（含 scripts 下两个）。
- 切片测试：`test_record_work.py` + `test_publish_stock.py` + `test_preflight_guard.py` + `test_create_book.py` + `test_delete_book.py` → **37 passed**。
- 冒烟：`current_book.py`、`check_stock.py`（含 --novel-id）、`get_meta.py`、`preflight.py`、`release_lock.py` 对真实 `demo.db` 全部 exit 0，输出 JSON 合法；preflight 显示 cookie 有效、预算 1.83/100。

## P0

无。

## P1

**1. `upsert_costs` 按 `(run_id, node_name)` 去重，同一 run 内同一节点的多次 LLM 调用成本被丢弃** — `tools/record_work.py:466-467`

```python
if run_id:
    dup = conn.execute(
        "SELECT id FROM cost_logs WHERE run_id=? AND node_name=?",
        (run_id, node),
    ).fetchone()
    if dup:
        continue
```

证据链：
- `n8n_tmp/daily_result.json`（真实调度产物，run_id=`scheduler-20260812060145-090a45-b1`）：`写手A` 出现 3 次、`润色A` 2 次、`审稿A` 2 次，共 20 条 costs，均非重放——是同一 run 内同一节点的多次独立 LLM 调用（`tools/editorial_daily.py:373-380` 每次调用追加一条）。
- 实测：用该文件跑 `record_work.py` 到临时库，cost_logs 只落 16 行，写手A/润色A/审稿A 各只剩 1 行，总成本从 20 条缩成 16 条的量。
- 现有测试 `test_cost_insert_idempotent_per_run` 只覆盖"同一 payload 重放"（防 n8n 重试），没覆盖"同 run 同 node 多次调用"，所以测试全绿但缺陷真实存在。

影响：生产路径（scheduler 的 run_id 永远非空）每月成本被系统性低估（demo.db 历史数据里同 node 平均 4~8 次调用，只记 1 次，低估可达 50%+），`preflight.check_budget`（`tools/preflight.py:105-108`）基于低估的成本做月度预算闸门，会允许实际超预算的运行继续。建议按 `(run_id, node, model, prompt_tokens, completion_tokens)` 全字段或 payload 指纹去重。

## P2

**2. `seq = int(ch.get("seq") or 0)` 无保护强转，脏 seq 让整个归档崩溃** — `tools/record_work.py:341`

同一函数里 `words` 走 `_to_int`（有 alerts.log 兜底），唯独 `seq` 裸 `int()`。实测：payload 传 `"seq": "abc"` → `ValueError: invalid literal for int() with base 10: 'abc'`，exit 1，无 JSON 输出（`"seq": 2.5` 这类 float 倒是能截断通过）。LLM 或 n8n 上游产出非数字 seq 时，当日归档整体失败且 n8n 只能看到裸 traceback。

## P3

**3. `daily_chapters`/`pending_publish` 设 0 无法表达"本次不发"** — `tools/check_stock.py:37-40`、`tools/publish_stock.py:411-414`。`int(x or 2)` 把显式 `0` 吞掉，`max(1, ...)` 下限 1。实测 `daily_chapters=0` → `target=1`。若用户用 0 表示暂停，会意外往番茄发 1 章（外部副作用）；项目虽有 `daily_enabled` 开关，但 0 的语义与直觉相悖。

**4. `pyproject.toml:6` description 是 GBK 乱码**（"鏂囧鐖辩紪杈戦儴锛歕I 缃戞枃澶?Agent..."）。文件本身是合法 UTF-8（strict decode 通过），但 description 内容是被错误转码后写入的 mojibake，`pip show` / 包元数据直接显示乱码。`desktop/package.json` 同源问题，不在本切片。

**5. `preflight.py:38-52` / `collect_reader_stats.py:28-42` 的本地 `load_env` 与 `config.load_env` 不一致**：前两者 `v.strip()` 不去内联注释，config 用 `_strip_inline_comment`（`config.py:93-106`）。`~/.n8n/.env` 里若出现 `KEY=value # 注释`，preflight 会把 `# 注释` 带进 cookie/CSRF 值导致校验失败，而 config 路径解析结果不同。`.env` 一般无内联注释，概率低，但两处实现理应统一。

**6. `n8n_api.py:49` 每次 `request` 都重新 `POST /rest/login`**：`headers = {"Cookie": "n8n-auth=" + auth_token()}` 每次都登录换新 JWT，批量操作（list/delete 循环）会打多次登录接口；建议缓存 token。

**7. `watch_daily.py:35-37` `cost_today` 名不副实**：`created_at >= date('now','localtime','-1 day')` 统计的是"昨天 00:00 至今"，不是"今天"。监控展示层的小偏差。

**8. `_run_fix_worker.ps1:39-44` Model 为空时仍传 `-m ""`**：`run_fix_batch.ps1` 只在 `-Model` 非空时传参，worker 默认 `""` 却无条件拼进 `$parts`，codex 收到空 `-m` 值。另外 taskText 全文作为单条命令行参数，任务文件过大时可能触碰 Windows 命令行长度上限。

**9. `delete_book.py` 的 `_purge_novel`（70-95 行）不清理 `agent_messages.ref_chapter_id` 孤儿行**：循环 1 只匹配列名恰为 `chapter_id` 的表，`agent_messages` 的引用列是 `ref_chapter_id`（`db.py:277`，无 FK 约束），章节删除后消息行残留。不影响 FK 完整性，属清理不完整。

## 影响表

| 编号 | 级别 | 位置 | 影响 | 触发条件 |
|---|---|---|---|---|
| 1 | P1 | record_work.py:466 | 月度成本低估 50%+，预算闸门失真 | 生产 scheduler 每次运行（必现） |
| 2 | P2 | record_work.py:341 | 归档崩溃、n8n 裸 traceback | 上游 seq 为非数字字符串 |
| 3 | P3 | check_stock/publish_stock | 设置 0 仍发 1 章 | 用户显式设 0 |
| 4 | P3 | pyproject.toml:6 | 包元数据乱码 | pip show / 发布时可见 |
| 5 | P3 | preflight.py:48 | cookie 值混入注释 | .env 含内联注释 |
| 6 | P3 | n8n_api.py:49 | 每次请求重复登录 | 批量 CLI 操作 |
| 7 | P3 | watch_daily.py:35 | 监控标签偏差 | 面板查看时 |
| 8 | P3 | _run_fix_worker.ps1 | 空模型参数/超长命令行 | 未指定 -Model / 大任务文件 |
| 9 | P3 | delete_book.py:70-95 | 孤儿消息残留 | 删除绑定番茄的书 |

## 结论

这个切片的整体质量是像样的——锁机制（O_EXCL + PID 存活检查 + 2h 兜底）设计严谨，SQL 全部参数化，脏数据兜底意识普遍存在，切片测试全绿，我实测的只读工具路径没有发现假绿灯。但有一个必须修的问题：成本去重把"防重试"做成了"防多次调用"，生产路径每天都在低估成本，预算闸门形同虚设，这是 P1，建议下个周期就处理；`seq` 强转是同一个文件的第二处硬伤，顺手一起修掉teyo。其余 P3 都不阻塞，但 3、5 两个涉及外部副作用的语义问题，还是值得看一眼desuwa。

---

嗯，就这些mashitawa。临时验证库我都清干净了，demo.db 没动过一个字节。整体判断：功能链路可用，但成本数据这条线不诚实，先修它desuno。
