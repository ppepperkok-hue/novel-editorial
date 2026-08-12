# 轮次总结 · 20260812-round2（合并后全库复查）

## 1. 范围与基线

- 范围：main 合并后的全库状态（含自由会议改造 + 前端重构）。
- 基线：后端 578、前端 45、`npm run build` 全绿。
- 审查方式：六片并行全库审查（2311-slices）。

## 2. 发现统计

| 来源 | P0 | P1 | P2 | P3 |
| --- | --- | --- | --- | --- |
| slices（2311） | 0 | 4 | 5 | 8 |

## 3. 修复分组与执行

| 组 | 内容 | 结果 |
| --- | --- | --- |
| P1 锁路径统一 | workday.py 3 处 + control.py 周会锁改用 config.TMP_DIR（NOVEL_DATA_DIR 感知），publish/release 已统一 | 已修（fbf2bf8） |
| P1 周会线程异常保护 | control.py `acquire_lock` 包 try/except，OSError 显式告警不再静默崩线程 | 已修（fbf2bf8） |
| P1 get_meta 路径分裂 | hot_topics/alerts/reader_stats 全部改读 config 路径，与写入方一致 | 已修（fbf2bf8） |

## 4. 验证与提交

- 全量回归：后端 578、前端 45、build 通过（一次 flaky 已复跑确认）。
- 提交：`fbf2bf8`（main）。
- 遗留未修项：见 `legacy-tracker.md`（均为 P2/P3，无 P1；用户可进入实际试用）。

## 5. 下一轮建议

1. 用户实际试用后按反馈处理；P2（config.DB_PATH 迁移、SettingsPage 空白、create_book 异常、delete_book 孤儿消息）下一轮处理。
2. round1 遗留 L1/L2（日更假绿灯、release.js 版本提交）继续挂账。
