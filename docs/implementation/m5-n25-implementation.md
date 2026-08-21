# M5 实施真元文档（产品形态与开源 · N25 导入导出与备份）

## 总览

- **大阶段**：M8 产品形态与开源扩展线（backlog 见 docs/project-plan/06-new-capability-backlog.md；N20/N21/N22/N24 已收口，N25 为下一 P1 候选）。
- **N25 一句话**：一部作品连同编辑部设置一键打包带走，换设备、迁移、备份都不丢。
- **现状**：
  - 作品数据为「全局注册行（workspaces）+ 每作品独立 SQLite（data.db）」结构（N13/N5/N3 等全部落在这两层）；
  - 无导出 / 导入 / 备份入口；换设备只能整目录拷贝，且无法跨实例恢复注册信息。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条端到端「建作品并造数据（草稿/消息/设定/结构/风格/事件）→ `works export` 出 ZIP → 新环境 `works import` 恢复 → 新作品可 works show / style show / events list / log 正常使用，内容与导出前一致」；既有 1047 测试全绿。

## 红线（本阶段强制，06 通用性红线继承）

1. **导出只读**：`works export` 不落事件、不改任何数据；导出过程写临时文件，成功后原子移动到目标路径，失败不留半成品。
2. **导入不覆盖**：导入始终生成新 workspace id，绝不覆盖既有作品、绝不改写既有数据库文件；导入失败清理临时目录、不留半成品。
3. **可校验**：ZIP 内含 `manifest.json`（format / version / exported_at / workspace 元数据 / data.db sha256）；导入时校验 format、version、sha256，任一不符拒绝导入。
4. **迁移即完整**：导入后新作品可正常使用全部既有命令（数据迁移到 schema head）；作者在导入侧 `works list` 可找到新作品。
5. **路径显式、不覆盖**：导出目标为显式路径；目标文件已存在时拒绝覆盖（USAGE_ERROR），由作者自行处理旧文件；不写任何默认位置。

## 地基影响评估（先评估再动工）

- 无表结构变更、无事件契约变更、无新依赖（标准库 zipfile / sqlite3 / shutil / hashlib / json）。
- 新增 `core/archive.py` + CLI `works export` / `works import` + 测试；依赖方向 cli → core → store 不变。
- 导出用 SQLite backup API 取一致快照（源库并发写入时仍得到完整副本）；导入用临时目录解包 → 校验 → 新 id 落盘 → 迁移到 head → 注册全局行。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 S1：归档核心服务

### 做什么

- `core/archive.py`（新模块）：
  - `export_workspace_archive(db, workspace_id, target) -> Path`：
    - 作品不存在 → NovelError(NOT_FOUND)（复用既有守卫）；
    - 用 sqlite3 backup API 把 `data/works/<id>/data.db` 快照到内存/临时文件；
    - 生成 `manifest.json`：`format: "novel-editorial-workspace"`、`version: 1`、`exported_at`（ISO）、`workspace`（id/title/genre/description/status/created_at）、`files: {"data.db": "<sha256>"}`；
    - 打包为 ZIP（manifest.json + data.db）；
    - 目标语义：target 为已存在目录 → 目录内生成 `novel-export-<id>-<YYYYmmdd-HHMMSS>.zip`；target 为不存在路径且父目录存在 → 作为文件路径；父目录不存在 → USAGE_ERROR；target 文件已存在 → USAGE_ERROR（不覆盖）；
    - 原子落盘：先写同目录临时文件，成功后 rename；
    - 导出只读：不落事件、不改任何数据。
  - `import_workspace_archive(db, archive_path) -> Workspace`：
    - 路径不存在 → NOT_FOUND；解包到临时目录（失败清理并抛 USAGE_ERROR）；
    - 校验：manifest 存在且 format / version 正确；data.db 存在且 sha256 匹配；任一不符 → USAGE_ERROR；
    - 生成新 workspace id（uuid4 hex）；把 data.db 复制到 `data/works/<新id>/data.db`，对副本跑既有迁移（`run_migrations`）到 head；
    - 在 global.db 注册新行：id=新id，title/genre/description/status/created_at 沿用 manifest.workspace 原值；
    - 落一条 SYSTEM 事件 `workspace_imported`（payload 含 source_id）；
    - 返回新 Workspace；失败清理临时目录与半成品。
- tests（`tests/test_archive.py`）：导出→导入往返（草稿/版本/消息/设定/结构/风格/事件数一致，style 值一致）、导出只读（events 不变、文件数不变）、目标为目录/文件路径、目标文件已存在拒绝、父目录缺失拒绝、workspace not found、导入新 id（不等于旧 id）、导入后注册可见且命令可用（works show / style show / events list / log）、坏 ZIP / 缺 manifest / 版本不支持 / sha256 不符拒绝、导入失败无残留。

### 做到什么程度

- 归档与恢复可复现、可校验；CLI 不接。

### 验收标准

- 单测覆盖上述全部路径；错误路径正确。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- CLI（S2）、文档（S3）、全局整库导出、增量备份、自动定时备份、加密。

## 子阶段 S2：CLI 与端到端

### 做什么

- 修复 S1 独立审查两个 P3（允许触碰 core/archive.py 与 tests/test_archive.py）：
  - `_rewrite_workspace_id` 的 `PRAGMA table_info` 表名做标识符转义（与 UPDATE 一致），恶意表名不再抛原始 `sqlite3.OperationalError`；
  - 导入在复制/迁移前先预检 data.db 是真实 SQLite（文件头 magic 或 `PRAGMA schema_version`），非 SQLite → `USAGE_ERROR`（"invalid archive: data.db is not a SQLite database"），不冒原始 DatabaseError。
- `cli/works.py` 新增：
  - `works export <作品ID> <目标路径>`：输出导出成功信息（`exported: <绝对/相对路径>`）；作品不存在 1；目标非法 2；
  - `works import <归档路径>`：输出 `imported workspace <新id>: <title>`；归档路径不存在 1；校验失败 2。
- tests：registry 的 works 组补 export/import；端到端「建作品+造数据 → export → 清空数据目录 → import → show/style/events/log 可用且内容一致」；退出码路径。

### 做到什么程度

- 作者一条命令打包带走、一条命令搬回来；不覆盖、可校验。

### 验收标准

- 端到端用例 + 失败路径；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3 + ruff + pyright + 宪法。

### 暂不做

- 整库导出、增量备份、加密、N24 API 导出/导入端点（面板后置再议）。

## 子阶段 S3：文档、全量回归与收口

### 做什么

- 修复 S2 独立审查 P2（允许触碰 core/archive.py 与 tests/test_archive.py）：`_is_sqlite_database` 命中文件头 magic 后不再提前返回 True，必须再真实读 schema（如 `SELECT count(*) FROM sqlite_master`）成功才算有效 SQLite；魔数前缀垃圾库 → `USAGE_ERROR`（"invalid archive: data.db is not a SQLite database"），不冒原始 DatabaseError；补对应测试（含无残留断言）。
- usage.md 增「导入导出与备份（N25）」小节：`works export` / `works import` 用法、ZIP 结构与 manifest 校验语义、导入生成新 ID 不覆盖、导出只读、mock 实跑示例。
- 全量回归 + 独立审查 + 归档 docs/reviews/（20260821-M5N25S1 / S2 / S3 链）。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 1047+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 整库备份、定时备份、加密、云同步。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权低价窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。

## 状态

- 收口（2026-08-22）：S1（c350876）、S2（0413e45，含 S1 审查两个 P3 修复）、S3（1908a11，含 S2 审查 P2 修复）全部完成并独立审查收敛；全量 1074 测试、smoke_m3、stress_m3 全绿；审查链归档 docs/reviews/20260821-M5N25S1-initial.md / 20260821-M5N25S2-initial.md / 20260821-M5N25S3.md；S3 审查 P3（0 字节空库宽容）留档工程待办。N25 正式收口。
