"""Flow topology for the panel's pipeline view (de-n8n).

The daily scheduler is a fixed DAG mirroring `docs/planning/de-n8n-mapping.md`;
this module exposes that graph plus the latest run state so the frontend can
render the chain without n8n. `FAILED_ALIAS` maps scheduler failure names back
to graph node ids for highlighting.
"""

from __future__ import annotations

import json


def _node(nid, label, group):
    return {"id": nid, "label": label, "group": group}


FLOW_NODES = [
    _node("trigger", "触发（手动/定时）", "trigger"),
    _node("backup", "备份数据库", "preflight"),
    _node("preflight", "预检（Cookie/预算/锁）", "preflight"),
    _node("stock", "查存稿", "dispatch"),
    _node("publish_stock", "发布存稿", "publish"),
    _node("book_list", "查章节号", "meta"),
    _node("meta", "读本地资料", "meta"),
    _node("work_meta", "生成作品资料", "meta"),
    _node("modify_book", "提交作品资料", "meta"),
    _node("planner", "Planner 出大纲", "plan"),
    _node("bible", "初始化设定知识库", "plan"),
    _node("guard", "守护细纲", "plan"),
    _node("writer_a", "写手 A", "track_a"),
    _node("editor_a", "润色 A", "track_a"),
    _node("reviewer_a", "审稿 A", "track_a"),
    _node("reader_a", "读者审稿 A", "track_a"),
    _node("eic_a", "主编终审 A", "track_a"),
    _node("gate_a", "质量门 A", "track_a"),
    _node("memory_a", "提炼剧情 A", "track_a"),
    _node("layout_a", "排版 A", "publish"),
    _node("publish_a", "发布 A", "publish"),
    _node("verify_a", "校验 A", "publish"),
    _node("writer_b", "写手 B", "track_b"),
    _node("editor_b", "润色 B", "track_b"),
    _node("reviewer_b", "审稿 B", "track_b"),
    _node("reader_b", "读者审稿 B", "track_b"),
    _node("eic_b", "主编终审 B", "track_b"),
    _node("gate_b", "质量门 B", "track_b"),
    _node("memory_b", "提炼剧情 B", "track_b"),
    _node("layout_b", "排版 B", "publish"),
    _node("publish_b", "发布 B", "publish"),
    _node("verify_b", "校验 B", "publish"),
    _node("payload", "汇总运行结果", "wrapup"),
    _node("record", "记录作品资料", "wrapup"),
    _node("wrapup", "收尾（阅读/日记/知识/行动项）", "wrapup"),
]


def _edge(source, target):
    return {"source": source, "target": target}


FLOW_EDGES = [
    _edge("trigger", "backup"),
    _edge("backup", "preflight"),
    _edge("preflight", "stock"),
    _edge("stock", "publish_stock"),
    _edge("stock", "book_list"),
    _edge("book_list", "meta"),
    _edge("meta", "work_meta"),
    _edge("work_meta", "modify_book"),
    _edge("work_meta", "planner"),
    _edge("planner", "bible"),
    _edge("bible", "guard"),
    _edge("guard", "writer_a"),
    _edge("writer_a", "editor_a"),
    _edge("editor_a", "reviewer_a"),
    _edge("reviewer_a", "reader_a"),
    _edge("reader_a", "eic_a"),
    _edge("eic_a", "gate_a"),
    _edge("gate_a", "memory_a"),
    _edge("memory_a", "layout_a"),
    _edge("layout_a", "publish_a"),
    _edge("publish_a", "verify_a"),
    _edge("gate_a", "writer_b"),
    _edge("writer_b", "editor_b"),
    _edge("editor_b", "reviewer_b"),
    _edge("reviewer_b", "reader_b"),
    _edge("reader_b", "eic_b"),
    _edge("eic_b", "gate_b"),
    _edge("gate_b", "memory_b"),
    _edge("memory_b", "layout_b"),
    _edge("layout_b", "publish_b"),
    _edge("publish_b", "verify_b"),
    _edge("verify_a", "payload"),
    _edge("verify_b", "payload"),
    _edge("payload", "record"),
    _edge("record", "wrapup"),
    _edge("publish_stock", "wrapup"),
]


FAILED_ALIAS = {
    "写手A": "writer_a",
    "写手B": "writer_b",
    "润色A": "editor_a",
    "润色B": "editor_b",
    "审稿A": "reviewer_a",
    "审稿B": "reviewer_b",
    "读者审稿A": "reader_a",
    "读者审稿B": "reader_b",
    "主编终审A": "eic_a",
    "主编终审B": "eic_b",
    "提炼剧情A": "memory_a",
    "提炼剧情B": "memory_b",
    "发布A": "publish_a",
    "发布B": "publish_b",
    "Planner出大纲": "planner",
    "生成作品资料": "work_meta",
    "守护细纲": "guard",
    "读本地资料": "meta",
    "备份数据库": "backup",
    "发布存稿": "publish_stock",
    "初始化设定知识库": "bible",
    "记录作品资料": "record",
    "采集阅读数据": "wrapup",
    "全员写日记": "wrapup",
    "同步设定知识库": "wrapup",
    "回填行动项": "wrapup",
}


def build_flow(conn):
    """Return {nodes, edges, failed_ids, last_run} for the panel view."""
    row = conn.execute(
        "SELECT run_id, trigger, source, status, started_at, finished_at, "
        "published, failed_nodes, error FROM daily_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    last_run = dict(row) if row else None
    failed_ids = []
    if last_run:
        try:
            names = json.loads(last_run.get("failed_nodes") or "[]")
        except (TypeError, ValueError):
            names = []
        if not isinstance(names, list):
            names = []
        failed_ids = [
            FAILED_ALIAS[n] for n in names if FAILED_ALIAS.get(n)
        ]
    return {
        "nodes": FLOW_NODES,
        "edges": FLOW_EDGES,
        "failed_ids": failed_ids,
        "last_run": last_run,
    }
