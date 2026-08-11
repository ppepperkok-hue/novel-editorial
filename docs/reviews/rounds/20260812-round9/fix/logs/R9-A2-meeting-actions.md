弄好了mashitawa。两处遗留都收口了，验证也是全绿的desuwa。

R9-A2-01 在 [tools/meeting_actions.py](E:/code/novel-editorial/tools/meeting_actions.py:19)：我加了 `idx_audit_post_actions_once` 部分唯一索引（只约束 post_actions_applied 标记，不碰同类其他审计行），由 [L28 的 `_ensure_idempotency_index`](E:/code/novel-editorial/tools/meeting_actions.py:28) 做幂等运行时迁移——旧库若已有重复标记，会按 session 保留最早一条、清掉多余条，再建索引；[L73](E:/code/novel-editorial/tools/meeting_actions.py:73) 调用迁移后保留原快速路径，[L156](E:/code/novel-editorial/tools/meeting_actions.py:156) 新增 IntegrityError 分支：并发落败的一方回滚自己的副作用、返回 skipped，而不是把草稿插两遍。我为什么不用「条件 INSERT」？实测了，WAL 快照隔离下两个连接先查后插，条件 INSERT 照样 drafts=2、markers=1，只有唯一约束兜得住desuwa。

R9-A2-02 在 [tools/flow_graph.py L134-176](E:/code/novel-editorial/tools/flow_graph.py:134)：FAILED_ALIAS 补了 legacy n8n 全链名字——预检/preflight、查章节号、质量门A/B、排版A/B、新建/保存/提交发布A/B、校验/复核发布A/B、整理剧情A/B、汇总运行结果、每日/手动触发这些都有明确图节点；「未知节点」和「unknown」落到 trigger 作为运行入口兜底，图上至少看得见红点，但这个映射是近似值，我在下面额外问题里说明desuwa。

验证：compileall 通过；test_meeting_actions/test_flow_graph/test_meeting_session/test_web_api 共 46 项通过；全量 pytest 487 项通过；双线程并发实测 20 轮，每轮恰好一条草稿、一条标记、一个 skipped，无一重复；迁移兜底实测旧库 3+2 条重复标记被压成每会话一条，无关的 ending_review_recorded 行原样保留，迁移后新会话照常应用mashitawa。测试文件不在指派范围，我没改；建议补三类用例：FAILED_ALIAS 包含 预检/preflight/未知节点/unknown 且预检映射 preflight、双线程双连接同 session 只应用一次、预置重复标记的库迁移后唯一teyo。

额外问题只报不改：一是「未知节点」映射 trigger 是权宜，图上本没有对应节点，要根治得在数据侧把真实失败节点写进 failed_nodes（预检失败不写 failed_nodes 那条第八轮遗留也还开着）；二是 legacy 工作流里 读当前书/设定题材/结束/失败留痕 仍无图节点对应，我没硬凑；三是 [FlowPage.jsx](E:/code/novel-editorial/webapp/src/components/FlowPage.jsx:63) 还是不消费 node_status，整轮失败照样全红，前端要跟进；四是 IntegrityError 回滚会连带丢调用方未提交的审计行（如 post_meeting_actions），只在并发落败场景发生，语义可接受但值得知晓；五是测试普遍不清理 mkdtemp 目录的老问题依旧。MEMORY.md 没动，指派范围外desuwa。
