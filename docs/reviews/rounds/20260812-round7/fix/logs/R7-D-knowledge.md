弄好了mashitawa。七轮遗留的五个点，我全部在指派范围内修完并验证了desuwa。

先说 R7-D-01（L-019），tools/novel_knowledge.py 第 220 行：upsert_ex 的幂等判断去掉了 `and not change_note`，现在只要内容没变，change_note 再长也不会 version+1、不写 history；内容真变了照旧递增。我验证过相同内容带 change_note 两次调用 version 仍 1、history 0，换内容后 version 2、history 1，都过了desuwa。

R7-D-02（L-026）在 tools/novel_knowledge.py 第 108 行加了 `_ensure_drafts_schema`，用 PRAGMA 检查后幂等 ALTER 给 knowledge_drafts 补 novel_id 列；第 125 行的 _add_conflict_draft 查重改成 `novel_id=?` 精确隔离，旧行（novel_id 为 NULL）走 `title IN (前缀, 裸实体)` 兜底，插入也写 novel_id。两本小说同实体各得各的草稿、同书重复触发不新增、旧数据前缀兜底不串书，六项针对性检查全过desuwa。

R7-D-03（L-033）在 sync_latest 有章节路径补了 `"count": len(updated)`，第 636 行，两条路径现在都带 count。消费方 editorial_daily 是丢弃返回值的，但 CLI 和 test_knowledge_bible 都读 count，所以按保留并补全处理mashitawa。

R7-D-04（L-034）跟着迁移一起做了：category 参数现在真写进草稿，_ensure_drafts_schema 顺带补了 category 列，INSERT 落 category 字段，验证里草稿行的 category 都是 world_ruledesuwa。

R7-D-05（L-017）在 tools/export_agent_prompts.py 第 40 行加了 `_find_system_end`：END_MARK 必须后面紧跟 `,content:`（user 消息内容字段）才算边界，正文里的标记不管是行内还是行首都被跳过。任务举例的「独立行」我换成了更严的后缀判定，因为历史工作流的 system 是紧凑拼接、后面并没有换行，行首判定会直接弄丢真边界。三个场景——行内正文标记、行首正文标记、无真边界——都按预期处理desuwa。

验证上，`python -m compileall` 两个文件都过了；相关九份测试 80 passed，追加的 web_api/review_v4/clean_knowledge 38 passed。唯一失败的是既有测试 test_novel_knowledge.py 第 116 行断言 merge 内容相同时 version 仍为 3——这正是 R7-D-01 要求消除的膨胀，测试文件不在指派范围我没改，建议把断言改为 version 2 并顺带校验 history 不新增desuwa。

另外报告两个只发现没改的事。其一，那个既有测试其实在 version 断言处就中断了，后面的 conflict 草稿分支从没被真正跑到过；我实测「与阴阳守恒完全冲突的另一套规则描述。」和现有内容相似度 0.75，会走 merge 而不是冲突，所以冲突分支缺真实覆盖，建议补一个低相似度内容的用例。其二，迁移是懒迁移，只有首次触发冲突草稿时才 ALTER，想在任何库一打开就带列得改 db.py，那不在本轮指派范围，留给下一轮desuwa。

工作区原本就有的三十来个文件改动我一个没碰，也没有 git add/commit，MEMORY.md 未更新——这轮只允许动那两个文件，规矩我守住了mashitawa。
