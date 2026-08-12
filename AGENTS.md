# AGENTS.md（项目宪法）

## 定位与加载

本文是项目级宪法，Codex 等 agent 在项目内工作时自动加载；任务开始前必须按“加载清单”全量读取规则，只读片段等于没读。

规则只存放在指定位置，不散落副本：

- 本文件：强制项（验证纪律、失败显式化、权限边界、冲突规则）常驻。
- `docs/architecture/rules.md`：详细技术规则（按需读取，涉及实现时必读）。
- `docs/architecture/extension.md`：功能接入规则（涉及新功能时必读）。
- `docs/project-checklist.md` 与 `docs/project-plan/`：立项范围与里程碑（涉及需求时必读）。

## 强制项（常驻）

1. **验证纪律**：任务完成 = 可用测试通过 + 类型检查通过 + lint 无阻塞 + 真实或代表性输入跑通。修 bug 先复现问题或写失败测试。
2. **失败显式化**：不静默吞错、不假装绿灯；验证失败必须修复后重跑。
3. **权限边界**：破坏性操作需用户明确批准；不记录密码、密钥、token 等敏感信息。
4. **冲突规则**：本文件优先于通用习惯；与用户最新指令冲突时，以用户最新指令为准并说明差异。

## 行为规则（摘要）

5. **配置驱动**：环境差异进配置（`NOVEL_*` 环境变量 + `config.toml`），不硬编码密钥、路径、端口。
6. **幂等**：脚本与操作可重复执行，结果一致。
7. **最小改动**：只改任务相关文件，不重写、不格式化无关代码；不覆盖用户改动。
8. **文档如实**：代码、文档、交付说明一致，不夸大结果。
9. **审查义务**：交付前自审；重要改动提交审查；收到审查意见先验证再回应。
10. **沟通纪律**：进度、卡点、风险如实报告；仅在缺凭据 / 权限、外部环境不可得、目标不清或存在真实破坏性风险时才停下询问。

## 技术约定

- 依赖方向：`cli → core → store / llm / quality`；禁止反向与循环依赖（有测试守卫）。
- 验证命令：`uv run pytest`、`uv run ruff check .`、`uv run pyright`。
- 提交信息：Conventional Commits（英文）。
- 命令命名：动词-宾语；错误码枚举见 `src/novel_editorial/core/errors.py`。
- 详细约定见 `docs/architecture/rules.md`。

## 加载清单（任务开始前全量读取）

- [ ] `AGENTS.md`（本文件全文）
- [ ] 涉及实现时：`docs/architecture/rules.md`
- [ ] 涉及新功能时：`docs/architecture/extension.md` 与 `docs/project-plan/05-executable-units.md` 对应单元
- [ ] 涉及需求变更时：`docs/project-checklist.md`

禁止：跳过加载直接动手、只读标题、凭记忆执行。

## 宪法校验

```bash
python scripts/verify_constitution.py
```

校验 AGENTS.md 存在且非空、引用路径有效、强制项关键词齐全；失败则停下补读再继续。
