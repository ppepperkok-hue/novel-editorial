# MemoryAgent · 记忆更新提示词模板

阅读本章正文，输出三样东西：

1. 章节摘要（100 字内，含时间、地点、发生事件、结果）。
2. 角色状态变化（对每个出场角色：当前目标、情绪、关键变化）。
3. 新增世界事件与伏笔状态（埋设/推进/回收）。

## 输出

```json
{
  "summary": "...",
  "character_states": {"角色名": {"goal": "...", "emotion": "...", "change": "..."}},
  "world_events": [{"event": "...", "impact": "..."}],
  "plot_threads": [{"id": "...", "status": "open|advanced|recovered"}]
}
```

更新必须严格基于正文，禁止编造未发生的事件。
