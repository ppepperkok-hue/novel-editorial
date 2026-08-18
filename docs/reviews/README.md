# 审查归档（Reviews）

## 审查流程（独立 CLI 分工）

1. 总监督从实施文档 / backlog 打包任务，派给独立 CLI 执行（`codex exec`）。
2. 独立 CLI 按实施文档实现并本地验证，回报三问（做了什么 / 验证结果 / 偏离点）；不提交。
3. 总监督验收：对照验收标准跑验证四连（pytest / ruff / pyright / 宪法），通过后提交。
4. 总监督调独立审查 CLI 审查（`codex exec review --commit <sha>`）。
5. 审查报告归档到 `docs/reviews/`：`<YYYYMMDD>-<范围>.md`。
6. 总监督逐条核实审查意见，派修复任务包，回归验证，收口。

> 省 token 约定：代码 commit 才派独立审查；纯文档 / 归档 commit 由总监复核即可。推理档位统一 `model_reasoning_effort=high`：审查 CLI 与实现 / 修复 CLI 都默认 `-m deepseek-v4-flash -c model_reasoning_effort=high`（详见开发 skill 的 09a-cli-dispatch.md）。

## 报告模板

```markdown
# <YYYY-MM-DD> <范围> 审查报告

- 审查方式：codex exec review（独立 CLI，只读）
- 审查范围：commit <sha>
- 审查依据：AGENTS.md / rules.md / extension.md / 实施文档

### 优点
（具体）

### 问题
#### Critical（必须修）
#### Important（应该修）
#### Minor（可后补）
每条含：文件:行号、问题、影响、修法

### 建议

### 结论
Ready to merge: Yes | No | With fixes

### 处理记录
- 核实结果、修复 commit、回归结果
```

## 归档索引

- [20260813 历史审查汇总](20260813-review-archive.md)
- [20260815 M5-A1 初始审查](20260815-M5A1-initial.md)
- [20260815 M5-A1-FIX1 审查](20260815-M5A1-fix1.md)
- [20260815 M5-A1-FIX2 审查](20260815-M5A1-fix2.md)
- [20260815 M5-A1-FIX3 审查](20260815-M5A1-fix3.md)
- [20260815 M5-A2-A 初始审查](20260815-M5A2A-initial.md)
- [20260815 M5-A2-A-FIX2 审查](20260815-M5A2A-fix2.md)
- [20260815 M5-A2-B 初始审查](20260815-M5A2B-initial.md)
- [20260815 M5-A2-B-FIX 审查](20260815-M5A2B-fix.md)
- [20260816 M5-A3 初始审查](20260816-M5A3-initial.md)
- [20260816 M5-A3-FIX 审查](20260816-M5A3-fix.md)
- [20260817 M5-N2-B1 初始审查](20260817-M5N2B1-initial.md)
- [20260817 M5-N2-B1-FIX1 审查](20260817-M5N2B1-fix1.md)
- [20260817 M5-N2-B1-FIX2 审查](20260817-M5N2B1-fix2.md)
- [20260817 M5-N2-B1-FIX3 审查](20260817-M5N2B1-fix3.md)
- [20260817 M5-N2-B1-FIX4 审查](20260817-M5N2B1-fix4.md)
- [20260817 M5-N2-B2 初始审查](20260817-M5N2B2-initial.md)
- [20260817 M5-N2-B2-FIX 审查](20260817-M5N2B2-fix.md)
- [20260817 M5-N2-B3 审查](20260817-M5N2B3.md)
- [20260817 M5-N3-C1 初始审查](20260817-M5N3C1-initial.md)
- [20260817 M5-N3-C1-FIX 审查](20260817-M5N3C1-fix.md)
- [20260817 M5-N3-C2 审查](20260817-M5N3C2.md)
- [20260817 M5-N3-C3 初始审查](20260817-M5N3C3-initial.md)
- [20260817 M5-N3-C3-FIX 审查](20260817-M5N3C3-fix.md)
- [20260818 M5-N16-D1 初始审查](20260818-M5N16D1-initial.md)
- [20260818 M5-N16-D1-FIX 审查](20260818-M5N16D1-fix.md)
- [20260818 M5-N16-D1-FIX2 审查](20260818-M5N16D1-fix2.md)
- [20260818 M5-N16-D2 审查](20260818-M5N16D2.md)
