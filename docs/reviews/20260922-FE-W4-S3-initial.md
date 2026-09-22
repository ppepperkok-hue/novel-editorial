# 2026-09-22 FE-W4-S3 审查报告

- 审查方式：独立审查（隔离上下文子代理，只读）
- 审查范围：commit 648ee89（S3 实现）；复审 commit 80d45c1（S3 修复）
- 审查依据：AGENTS.md / rules.md / frontend-app.md / fe-w4-implementation.md
- 环境限制：electron 原生二进制下载体在沙箱受限，实际打包与双击验证未执行，需 Windows 实机验证（docs/usage.md 已标注）。

## 优点

1. 路径上溯正确：NOVEL_APP_ROOT 优先 + 校验，exe 目录 / app.getAppPath() 上溯，app.asar isFile→dirname 处理正确。
2. spawn 命令注入面为零：args 固定字面量无空格无用户输入，shell:true 仅为 Windows uv.cmd 垫片。
3. webPreferences 三元组正确（contextIsolation:true / nodeIntegration:false / sandbox:true）。
4. 单实例锁 + second-instance 聚焦正确；退出清理覆盖全路径 + backendStopped 幂等。
5. 文档与代码一致：端口 / 轮询间隔 / 超时 / 窗口尺寸 / 产物路径 / mac 限制均一致。

## 问题（初审，commit 648ee89）

### Important

- will-navigate 同源判断用 `url.startsWith(BASE_URL)` 字符串前缀匹配，可被 `http://127.0.0.1:87650` / `http://127.0.0.1:8765.evil.com` 绕过。修法：`new URL(url).origin` 精确比较。

### Minor

- exit 码丢失（exit 处理器先 backend=null）、taskkill 异步时序、NOVEL_API_HOST=0.0.0.0 时连接失败、日志 Buffer 隐式转换 / 可能透敏感、release/ 未 gitignore、mac/linux 孙进程残留、openExternal 未 catch、second-instance 竞态。

## 修复与复审（commit 80d45c1）

- 修复 I-1（isSameOrigin 用 origin 精确比较）+ 连接/绑定 host 分离（BASE_URL 固定 127.0.0.1）+ exit 码快照 + openExternal 封装（isHttpUrl + try/catch）+ will-redirect 拦截 + release/ gitignore + chunk.toString()。
- 复审结论：**Ready to merge: Yes**。两条非阻塞 Minor（localhost origin 误判、signal 快照）记 P3 后补。

## 处理记录

- 初审 1 Important + 8 Minor；修复 80d45c1；复审 Ready to merge: Yes。
- `node --check main.cjs` 与前端 typecheck 绿；electron 打包 / 双击验证需 Windows 实机（沙箱 CDN 下载受限）。
- 代码提交 648ee89（实现）+ 80d45c1（修复），已推送 origin/main。
- P3 后补（记 07-parked-backlog）：localhost origin 等价、signal 快照、mac/linux 孙进程清理、second-instance bootstrap 竞态。
