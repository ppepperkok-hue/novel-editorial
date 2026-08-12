# 功能接入规则（Feature Extension）

所有新功能走同一条路：取单元 → 查规则 → 在骨架内增量实现 → 过验证门。

## 接入流程

1. 从 backlog（05-executable-units.md）取一个单元。
2. 查通用规则（rules.md）与最小范围（scope.md），确认不在“本期不做”清单。
3. 在既有骨架内增量实现：CLI 命令注册在 `cli/`，业务逻辑放 `core/`，数据访问放 `store/`，外部能力放 `llm/` 或 `quality/`。
4. 为单元写验收测试（tests/ 镜像 src/）。
5. 跑验证四连：`pytest`、`ruff check`、`pyright`、CLI 冒烟。
6. 更新相关文档（功能拆解标记、skeleton 结构说明），提交走 Conventional Commits。

## 模块模板

### CLI 命令

```python
@works_app.command("show")
def works_show(workspace_id: str = typer.Argument(...)) -> None:
    """Show a workspace and its band."""
    settings = load_settings()
    db = DB(settings)
    ...
```

- 命令命名：动词-宾语；退出码：0 成功 / 1 业务错误 / 2 用法错误 / 3 系统错误。
- 业务异常抛 `NovelError`（带错误码），CLI 顶层统一转换退出码。

### 数据访问

- 全局数据用 `db.global_session()`；作品数据用 `db.workspace_session(workspace_id)`。
- 新表加入 `store/models.py`，迁移走 Alembic（本期仅 baseline，后续随功能加迁移）。

### 测试

```python
def test_works_show(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    runner.invoke(app, ["works", "create", "书名"])
    result = runner.invoke(app, ["works", "show", "workspace_id"])
    assert result.exit_code == 0
```

## 禁止项

- 新功能自带新架构（另起炉灶）。
- 绕过规则（跳过测试 / lint / 类型检查）。
- 复制粘贴改名（复制模块后只改名字，不按功能重构）。
- 把“以后可能用到”的机制顺手搭进来。

## 每功能交付检查单

- [ ] 单元与 backlog 对应，不在“本期不做”清单
- [ ] 规则符合（目录、命名、依赖方向、错误码、事件契约）
- [ ] 验收测试通过，覆盖错误路径
- [ ] 验证四连全绿
- [ ] 文档同步更新，无残留调试代码

## 模板实测示例

用 `works show` 实测接入流程：CLI 命令 + 数据访问 + 测试，验证“取单元 → 增量实现 → 过验证门”可走通。实现见 `src/novel_editorial/cli/app.py` 与 `tests/test_works.py`。
