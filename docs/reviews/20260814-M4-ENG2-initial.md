# 2026-08-14 M4-ENG-2（瓶颈 2：检索性能）初始审查报告

- 审查方式：codex exec review（独立 CLI，只读）
- 审查范围：commit 8b0541c（FTS5 trigram 索引 + 双路径检索；前序 c4d7f6c、6f7bf7c）
- 审查依据：AGENTS.md / rules.md / extension.md / docs/implementation/m4-eng2-implementation.md

### 优点

- 迁移 9c3a71b5d2e4 为五个正文层建 FTS5 trigram 影子表 + 15 个增量同步触发器 + 幂等回填；旧库升级实测回填一致。
- views.py 双路径：3 字符及以上走 FTS MATCH、2 字符及以下回退 LIKE；输出格式与顺序逐字节不变。
- test_fts.py 覆盖建表、触发器同步、旧库升级、双路径一致性、攻击性关键词转义，验证充分。

### 问题

#### Critical（必须修）

无。

#### Important（应该修）

1. **P2：非 ASCII 大小写折叠破坏 FTS/LIKE 双路径一致性**
   - 文件：src/novel_editorial/core/views.py（_content_hit_ids 路径）
   - 问题：FTS trigram 默认 Unicode 大小写折叠（café 命中 CAFÉ），LIKE 的 lower() 只折叠 ASCII；实测 FTS 只多返回不漏返回。
   - 影响：违反"双路径逐字节一致"验收标准；_snippet 可能从头截取。
   - 修法：FTS 候选后追加 LIKE 精筛（见修复链）。
2. **P2：无 FTS5 的 SQLite 构建下迁移失败导致所有命令不可用**
   - 文件：migrations/versions/9c3a71b5d2e4（无条件 CREATE VIRTUAL TABLE USING fts5）
   - 问题：run_migrations 在 init_schema（每个命令）都会执行；无 FTS5 构建直接抛错，且无 LIKE 回退。
   - 修法：迁移/搜索入口做 FTS5 可用性探测，不可用时跳过建表并始终走 LIKE。

#### Minor（可后补）

3. **P3：FTS 命中 id 内联为绑定参数，超过 SQLite 变量上限崩溃**
   - 文件：src/novel_editorial/core/views.py（in_(...)）
   - 问题：命中行多时 too many SQL variables（3.45 上限 32766），实测 33000 命中崩溃。
   - 修法：FTS MATCH 子查询 JOIN 主查询，替代 in_ 列表。

### 建议

无。

### 结论

Ready to merge: No（With fixes）

### 处理记录

- 修复链（每轮独立审查收敛）：ff95a36 → 70ae0a1 → 0297529 → bb31ff1 → 1288964 → 9cdc194；终审 Ready to merge，详见 [20260814-M4-ENG2-fix.md](20260814-M4-ENG2-fix.md)。
