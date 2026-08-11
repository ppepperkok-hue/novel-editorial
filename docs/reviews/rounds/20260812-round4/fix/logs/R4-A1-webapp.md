全部验证通过了。修复收尾，汇报如下desuwa。

四项都修好了，测试和构建全绿，验证结果如下。

R4-A1-01，SettingsPage.jsx 第 85–89 行。保存流程本来就检查了 `sched.ok`，但真正的问题在后端失败时的返回结构——`apply_schedule` 注册计划任务失败时只返回 `{ok: false, deploy: {ok: false, output: ...}}`，不带 `error` 字段，所以旧代码只会弹「更新时间应用失败：未知」，等于没告诉用户任何东西。现在失败时优先取 `sched.deploy?.output`（schtasks 的真实输出），没有就退回 `sched.error`，再兜底写「计划任务注册失败」，文案明确区分「设置已保存」和「计划任务注册失败」，级别也从 warn 提到 bad，不再静默desuwa。

R4-A1-02，AgentsPage.jsx 第 171–181 行。后端 save 失败时本来就带 `render`、`validation`、`validation_output` 三个字段，前端失败分支却只打 `r.error`，详情分支确实不可达。现在失败时把渲染输出和校验未通过的详情都写进操作日志，toast 保留简短错误，用户能直接看到失败原因mashitawa。

R4-A1-03，Shell.jsx 第 172 行。帮助文案改成动态生成：`1 – ${NAV.length}`，NAV 现在 12 项，弹窗就显示「1 – 12」，以后导航项增减也不会再对不上desuwa。

R4-A1-04，vite.config.js 第 6–20 行。加了 `/api` 代理到 `http://127.0.0.1:8000`——端口是从 web_api.py 的 `--port default=8000` 确认的。这里有个细节：后端 CSRF guard 只信任 8000 端口的 Origin，dev 页面在 5173 发 POST 会被直接拒绝，所以代理里把 Origin 改写为后端信任的同源值，不然联调只通一半teyo。

验证方面，基线测试 16/16 通过，修复后 `npx vitest run` 仍是 16/16 全绿，`npm run build` 成功（4.17s），另外用 Node 加载了配置确认代理对象无误。工作区里其他文件的改动是并行分片同事动的，我只碰了指派四个文件，没有 git add/commit，也没更新 MEMORY.md。

测试建议（没改测试文件）：给 SettingsPage 写一条 mock，让 `apply_schedule` 返回 `{ok:false, deploy:{ok:false, output:"..."}}`，断言 toast 包含「计划任务注册失败」和输出详情；给 AgentsPage 写一条 mock，返回 `{ok:false, render, validation:false, validation_output}`，断言操作日志出现「渲染输出」和「校验未通过」；Shell 断言帮助弹窗显示 `1 – 12`。

额外发现，只报告不改：`SettingsPage` 的 `action()` 和 `save()` 没有 catch 分支，虽然 `postJSON` 已把网络错误包成 `ok:false`，风险不高，但兜底更稳；另外 build 时 charts chunk 有 527KB 的超 500KB 警告，属于既有打包提示，与本次改动无关desuwa。
