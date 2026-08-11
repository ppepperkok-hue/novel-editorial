三处都修好了mashitawa，验证也全绿desuwa。

桌面通知那处，问题在 main.js 的 watchExecutions，改动集中在 199 到 247 行。我加了启动播种：fetchList 在启动时先拉一次最近 30 条执行，把已经是终态的 key 全部塞进 notifiedExecKeys，之后 30 秒轮询只对本次运行期间新出现的终态发通知；万一启动那次拉取失败，第一次成功轮询也会先播种再返回，绝不补发历史teyo。验证上 node --check 通过，我还把真实代码里的 watchExecutions 抠出来做了模拟：30 条历史终态启动后 0 条通知，新增一条终态只发 1 条，种子失败场景同样先抑制、恢复后正常masuwa。

前端那处，App.jsx 59 到 79 行。手动刷新之前直接调 fetchDashboard，绕开了轮询的错误状态，失败自然静默；现在包了一层 trackedFetchDashboard，轮询和手动刷新走同一个函数、同一个 dashboardError，成功清空、失败写错误字符串，刷新按钮的转圈也保住了desuwa。vitest 7 个文件 16 条全过，npm run build 也过了，只剩原有的 chunk 超 500KB 警告。

.npmrc 直接删掉了，里面就一行 cache=E:\code\.npm-cache 的本机绝对路径，没有别的配置，删了最干净desuwa。

额外发现两个点，只报告不动手：main.js 那个 30 秒轮询没有超时或重入保护，某次请求真挂起超过 30 秒，下一次 tick 照样启动，可能叠请求，本地 API 下概率很低desuno；另一个是 App.jsx 本地维护 dashboardError 之后，usePolling 返回的 error 和 refresh 就不再被消费了，属于冗余不是 bug，先记着desuwa。

MEMORY.md 没动，工作区里其它改动是并行分片的痕迹，我只碰了指派的那三个文件mashitawa。
