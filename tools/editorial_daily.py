"""Python daily scheduler: the de-n8n replacement for the 66-node workflow.

Single entry point:
    daily(conn, chapters=None, trigger="manual"|"scheduled", dry_run=False)

It replicates the n8n daily chain in-process (preflight -> stock/generate ->
A/B tracks -> publish -> payload -> record -> wrap-up) and writes durable
`daily_runs` rows itself. See `docs/planning/de-n8n-mapping.md`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import backup, config, db  # noqa: E402
from novel_pipeline.services import audit  # noqa: E402
from tools import (  # noqa: E402
    agent_tool_loop,
    auto_fill_actions,
    check_stock,
    collect_reader_stats,
    current_book,
    editorial_steps as steps,
    novel_knowledge,
    preflight,
    publish_stock,
    record_work,
    write_diaries,
)
from tools.app_settings import get_all, set_many  # noqa: E402

UA = publish_stock.UA
FANQIE = "https://fanqienovel.com"

AGENT_PARAMS = {
    "Planner出大纲": {"temperature": 0.7, "max_tokens": 8000},
    "生成作品资料": {"temperature": 0.7, "max_tokens": 4000},
    "守护细纲": {"temperature": 0.3, "max_tokens": 2000},
    "写手A": {"temperature": 0.85, "max_tokens": 4000, "target_words": True},
    "写手B": {"temperature": 0.85, "max_tokens": 4000, "target_words": True},
    "润色A": {"temperature": 0.5, "max_tokens": 8000, "target_words": True},
    "润色B": {"temperature": 0.5, "max_tokens": 8000, "target_words": True},
    "审稿A": {"temperature": 0.2, "max_tokens": 2000},
    "审稿B": {"temperature": 0.2, "max_tokens": 2000},
    "读者审稿A": {"temperature": 0.3, "max_tokens": 2000},
    "读者审稿B": {"temperature": 0.3, "max_tokens": 2000},
    "主编终审A": {"temperature": 0.2, "max_tokens": 2000},
    "主编终审B": {"temperature": 0.2, "max_tokens": 2000},
    "提炼剧情A": {"temperature": 0.3, "max_tokens": 2400},
    "提炼剧情B": {"temperature": 0.3, "max_tokens": 2400},
}


def _j(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class _Ctx:
    """Mutable per-run state threaded through every step."""

    def __init__(self, novel_id, db_path, dry_run, book_id="", book_name=""):
        self.novel_id = novel_id
        self.db_path = str(db_path)
        self.dry_run = bool(dry_run)
        self.book_id = str(book_id or "")
        self.book_name = str(book_name or "")
        self.writing_context = ""
        self.failed_nodes = []
        self.warnings = []
        self.errors = []
        self.published = 0
        self.costs = []
        self.agent_calls = []
        self.tool_attempts = []
        self.lock_path = None
        self.dry_item_counter = 0


def _dry_agent_text(ctx, node, task, target_words):
    """Deterministic placeholder responses so `--dry-run` walks the full chain."""
    if node.startswith("写手") or node.startswith("润色"):
        sentence = "他推开门走进院子，风从巷口吹来，远处传来吆喝声。"
        # ~21 Chinese chars per sentence; target 105% so the quality gate's
        # 75%-of-target word floor is safely cleared in dry-run mode.
        n = max(1, int((target_words or 2000) * 1.05) // 21 + 1)
        return sentence * n
    if node == "Planner出大纲":
        return _j(
            {
                "premise": "测试设定：主角林舟在都市中经营一家旧书店。",
                "genre": "都市",
                "title": "测试之书",
                "keywords": ["测试", "都市"],
                "chapter_outlines": [
                    {
                        "title": "开局",
                        "outline": "主角发现旧书店的秘密，迎来第一位客人。",
                        "hook": "门口的风铃突然响了。",
                        "emotion": "好奇",
                        "position": "开篇",
                        "pacing": "中",
                        "scenes": [],
                        "plant_foreshadow": "",
                        "recover_foreshadow": "",
                        "character_arc": {},
                    },
                    {
                        "title": "试探",
                        "outline": "主角试探客人的真实身份，发现书店与往事有关。",
                        "hook": "客人留下的书签上有一个熟悉的名字。",
                        "emotion": "紧张",
                        "position": "推进",
                        "pacing": "快",
                        "scenes": [],
                        "plant_foreshadow": "书签上的名字",
                        "recover_foreshadow": "",
                        "character_arc": {},
                    },
                ],
                "bible": {
                    "characters": [
                        {"name": "林舟", "role": "主角", "traits": "坚韧冷静", "goals": "查明书店秘密"}
                    ],
                    "relationships": [],
                    "world_rules": ["旧书店只在夜间开门"],
                    "style_guide": "简洁平实，少修饰",
                },
            }
        )
    if node == "生成作品资料":
        return _j(
            {
                "book_name": ctx.book_name or "测试之书",
                "abstract": "这是一本用于流水线测试的长篇网络小说，主角在都市中经营旧书店，逐步揭开尘封往事，剧情紧凑节奏明快。",
                "protagonist": {"name": "林舟", "traits": "坚韧冷静", "goals": "查明书店秘密"},
                "secondary_name": "",
                "volume_goal": "第一卷 旧书店",
                "genre": "都市",
            }
        )
    if node == "守护细纲":
        return _j({"passed": True, "issues": [], "constraints": [], "character_beats": {}})
    if node in ("审稿A", "审稿B", "读者审稿A", "读者审稿B"):
        return _j(
            {
                "passed": True,
                "score": 9,
                "hook_rating": 9,
                "would_read_next": True,
                "issues": [],
            }
        )
    if node in ("主编终审A", "主编终审B"):
        return _j({"verdict": "pass", "issues": []})
    if node.startswith("提炼剧情"):
        return _j(
            {
                "summary": "测试摘要：本章主角发现旧书店的秘密。",
                "character_updates": {},
                "plot_events": [],
                "foreshadowing_planted": [],
                "foreshadowing_recovered": [],
            }
        )
    return "测试占位输出"


def _agent(ctx, node, task, target_words=None):
    """Call one agent; collect usage/cost; record failures explicitly."""
    params = AGENT_PARAMS.get(node, {})
    if ctx.dry_run:
        text = _dry_agent_text(ctx, node, task, target_words)
        model = "dry-run"
        usage = {"prompt_tokens": 1, "completion_tokens": 1}
    else:
        result = agent_tool_loop.run(
            node,
            task,
            temperature=params.get("temperature"),
            max_tokens=params.get("max_tokens", 1600),
            target_words=target_words,
            novel_id=ctx.novel_id,
            db_path=ctx.db_path,
        )
        if not result.get("ok"):
            ctx.failed_nodes.append(node)
            ctx.errors.append(f"{node}: {result.get('error', 'agent failed')}")
            return None
        text = result.get("text") or ""
        model = result.get("model") or ""
        usage = result.get("usage") or {}
    ctx.costs.append(
        {
            "node": node,
            "model": model,
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
        }
    )
    ctx.agent_calls.append({"node": node, "chars": len(str(text or ""))})
    return str(text or "")


def _fanqie_get(ctx, url, params, env):
    """GET a Fanqie endpoint; dry-run returns canned responses."""
    if ctx.dry_run:
        return _dry_fanqie(ctx, url)
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url + "?" + qs,
        headers={
            "Cookie": env.get("FANQIE_COOKIE", ""),
            "X-Secsdk-Csrf-Token": env.get("FANQIE_CSRF_TOKEN", ""),
            "User-Agent": UA,
            "Origin": FANQIE,
            "Referer": FANQIE + "/main/writer/",
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return json.loads(raw.decode("gbk", "ignore"))


def _fanqie_post(ctx, url, fields, env):
    """POST form fields to a Fanqie endpoint; dry-run returns canned responses."""
    if ctx.dry_run:
        return _dry_fanqie(ctx, url)
    return publish_stock.http_form(url, fields, env)


def _dry_fanqie(ctx, url):
    if url.endswith("/book/book_list/v0"):
        return {
            "code": 0,
            "data": {
                "book_list": [
                    {
                        "book_id": ctx.book_id,
                        "chapter_number": 0,
                        "book_name": ctx.book_name or "测试之书",
                        "abstract": "这是一本用于流水线测试的长篇网络小说，主角在都市中经营旧书店，剧情紧凑。",
                    }
                ]
            },
        }
    if url.endswith("/article/new_article/v0/"):
        ctx.dry_item_counter += 1
        item = "dry-item-" + str(ctx.dry_item_counter)
        ctx._dry_last_item = item  # type: ignore[attr-defined]
        return {
            "code": 0,
            "data": {
                "item_id": item,
                "volume_id": "v1",
                "volume_data": [{"volume_id": "v1", "volume_name": "正文"}],
            },
        }
    if url.endswith("/article/cover_article/v0/"):
        return {"code": 0}
    if url.endswith("/publish_article/v0/"):
        return {"code": 0}
    if url.endswith("/chapter/chapter_list/v1"):
        item = getattr(ctx, "_dry_last_item", "dry-item-1")
        return {"code": 0, "data": {"item_list": [{"item_id": item, "article_status": 1}]}}
    if url.endswith("/book/modify_book/v0/"):
        return {"code": 0}
    return {"code": 0}


def _run_tool(ctx, name, fn):
    """Run a wrap-up/utility step; failures become warnings, never silent."""
    if ctx.dry_run:
        ctx.tool_attempts.append(name)
        return {"ok": True, "dry_run": True}
    try:
        result = fn()
        return result if isinstance(result, dict) else {"ok": True}
    except Exception as exc:  # noqa: BLE001
        ctx.warnings.append(f"{name}: {str(exc)[:200]}")
        return {"ok": False, "error": str(exc)[:200]}


def _get_meta(ctx, book_id):
    """Read the local memory pack; dry-run uses an empty pack."""
    if ctx.dry_run:
        ctx.tool_attempts.append("读本地资料")
        return {}
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "get_meta.py"),
        str(book_id or ""),
        "--db",
        ctx.db_path,
    ]
    try:
        out = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        return json.loads(out.stdout.strip() or "{}")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        ctx.failed_nodes.append("读本地资料")
        ctx.errors.append(f"读本地资料: {str(exc)[:200]}")
        return None


def _preflight(ctx, conn, env, trigger):
    """Mirror tools/preflight.py checks; acquires the shared atomic lock."""
    settings = get_all(conn)
    enabled = str(settings.get("daily_enabled", "true")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    try:
        budget = float(settings.get("monthly_budget") or 100.0)
    except (TypeError, ValueError):
        budget = 100.0
    manual_requested = str(settings.get("manual_run_requested", "0")) == "1"

    if trigger == "scheduled" and not enabled:
        return {"ok": False, "skipped": True, "reasons": ["日更已暂停（可在面板恢复）"]}

    cookie_ok, cookie_reason = preflight.check_cookie()
    already_ran = preflight.check_already_ran(conn)
    if manual_requested:
        already_ran = False
    budget_ok, spent = preflight.check_budget(conn, budget)
    book_ok, book_reason = preflight.check_active_book(conn)
    reasons = []
    if not enabled:
        reasons.append("日更已暂停（可在面板恢复）")
    if not cookie_ok:
        reasons.append(cookie_reason)
        preflight.alert("预检失败：" + cookie_reason)
    if already_ran:
        reasons.append("今日已发布过章节，跳过防重复")
    if not budget_ok:
        reasons.append(f"本月成本 {spent:.2f} 元已达预算 {budget:.2f} 元")
        preflight.alert(reasons[-1])
    if not book_ok:
        reasons.append(book_reason)
    if manual_requested:
        reasons.append("手动请求运行已生效")
    ok = enabled and cookie_ok and not already_ran and budget_ok and book_ok
    if ok:
        lock_path = ROOT / "n8n_tmp" / (Path(ctx.db_path).stem + ".lock")
        locked, lock_reason = preflight.acquire_lock(lock_path)
        if not locked:
            reasons.append(lock_reason)
            ok = False
        else:
            ctx.lock_path = lock_path
    if ok and manual_requested:
        set_many(conn, {"manual_run_requested": "0"})
    audit.log(
        conn,
        "preflight",
        "passed" if ok else "blocked",
        target_type="novel",
        detail={
            "ok": ok,
            "reasons": reasons,
            "cookie_valid": cookie_ok,
            "already_ran": already_ran,
            "budget_ok": budget_ok,
            "book_ok": book_ok,
        },
        source="preflight",
    )
    return {
        "ok": ok,
        "skipped": False,
        "reasons": reasons,
        "spent": spent,
        "budget": budget,
    }


def _writer_task(ctx, idx, meta, outline, guard, target_words, prev_track=None):
    node = "写手A" if idx == 0 else "写手B"
    ch = outline["chapter1"] if idx == 0 else outline["chapter2"]
    parts = [
        "主角：" + meta["protagonist"],
        "本章情绪目标：" + (ch.get("emotion") or ""),
        "章节定位：" + (ch.get("position") or ""),
        "章纲：" + _j(ch),
        "出场角色卡：" + _j((outline.get("bible") or {}).get("characters") or []),
        "人物关系：" + _j((outline.get("bible") or {}).get("relationships") or []),
        "世界观规则：" + _j((outline.get("bible") or {}).get("world_rules") or []),
        "世界观守护约束：" + _j(guard.get("constraints") or []),
        "本轮角色言行要点：" + _j(guard.get("character_beats") or {}),
        "前情提要：" + ctx.writing_context,
        "题材：" + outline["genre"],
        "关键词：" + outline["keywords"],
    ]
    if idx == 1 and prev_track:
        gate = prev_track.get("gate") or {}
        parts.append(
            "上一章（A章）结尾：" + (gate.get("editedText") or "")[-300:]
        )
        parts.append(
            "A章提炼：" + _j(prev_track.get("summary") or {})
            + "；本章开篇必须自然承接A章结尾并回应其悬念，不得重复A章内容"
        )
    return "；".join(parts)


def _reviewer_task(idx, outline, editor_text, prev_track=None, ctx=None, include_relations=False):
    ch = outline["chapter1"] if idx == 0 else outline["chapter2"]
    parts = [
        "章纲：" + _j(ch),
        "角色卡：" + _j((outline.get("bible") or {}).get("characters") or []),
    ]
    if include_relations:
        parts.append("人物关系：" + _j((outline.get("bible") or {}).get("relationships") or []))
    parts += [
        "世界观规则：" + _j((outline.get("bible") or {}).get("world_rules") or []),
        "前情提要：" + (ctx.writing_context if ctx else ""),
        "正文：" + str(editor_text or ""),
    ]
    if idx == 1 and prev_track:
        gate = prev_track.get("gate") or {}
        parts.append(
            "上一章（A章）结尾：" + (gate.get("editedText") or "")[-300:]
            + "；核对本章开头是否自然承接A章结尾"
        )
    return "；".join(parts)


def _eic_task(idx, outline, review_text, reader_text, editor_text):
    ch = outline["chapter1"] if idx == 0 else outline["chapter2"]
    return "；".join(
        [
            "角色卡：" + _j((outline.get("bible") or {}).get("characters") or []),
            "人物关系：" + _j((outline.get("bible") or {}).get("relationships") or []),
            "世界观规则：" + _j((outline.get("bible") or {}).get("world_rules") or []),
            "章纲：" + _j(ch),
            "逻辑审稿原始输出：" + str(review_text or ""),
            "读者审稿原始输出：" + str(reader_text or ""),
            "正文前800字：" + str(editor_text or "")[:800],
        ]
    )


def _memory_task(idx, outline, editor_text, ctx):
    ch = outline["chapter1"] if idx == 0 else outline["chapter2"]
    return "；".join(
        [
            "角色卡：" + _j((outline.get("bible") or {}).get("characters") or []),
            "人物关系：" + _j((outline.get("bible") or {}).get("relationships") or []),
            "世界观规则：" + _j((outline.get("bible") or {}).get("world_rules") or []),
            "章纲：" + _j(ch),
            "前情提要：" + ctx.writing_context,
            "正文：" + str(editor_text or ""),
        ]
    )


def _run_track(ctx, conn, idx, outline, guard, meta, target_words, env, prev_track=None):
    """Run one full A/B track: writer -> editor -> reviewer -> reader -> eic
    -> quality gate -> memory summary. Publishing happens afterwards."""
    suffix = "A" if idx == 0 else "B"
    chapter = outline["chapter1"] if idx == 0 else outline["chapter2"]

    writer_text = _agent(ctx, "写手" + suffix, _writer_task(ctx, idx, meta, outline, guard, target_words, prev_track), target_words)
    if writer_text is None:
        return {"gate": None, "summary": {}, "failed": True}
    editor_task = (
        "初稿：" + writer_text
        + "；角色卡：" + _j((outline.get("bible") or {}).get("characters") or [])
        + "；人物关系：" + _j((outline.get("bible") or {}).get("relationships") or [])
        + "；世界观规则：" + _j((outline.get("bible") or {}).get("world_rules") or [])
        + "；文风指南：" + str((outline.get("bible") or {}).get("style_guide") or "")
    )
    editor_text = _agent(ctx, "润色" + suffix, editor_task, target_words)
    if editor_text is None:
        return {"gate": None, "summary": {}, "failed": True}

    review_text = _agent(ctx, "审稿" + suffix, _reviewer_task(idx, outline, editor_text, prev_track, ctx))
    if review_text is None:
        # n8n semantics: a failed logic-reviewer node never reaches the
        # quality gate, so this track must not publish.
        return {
            "gate": {
                "passed": False,
                "errors": ["审稿链路失败：审稿" + suffix],
                "review": None,
                "reader": None,
                "editor": None,
            },
            "summary": {},
            "failed": True,
        }
    reader_text = _agent(
        ctx,
        "读者审稿" + suffix,
        _reviewer_task(idx, outline, editor_text, prev_track, ctx, include_relations=True),
    )
    eic_text = _agent(ctx, "主编终审" + suffix, _eic_task(idx, outline, review_text or "", reader_text or "", editor_text))
    gate = steps.quality_gate(
        editor_text,
        review_text,
        reader_text,
        eic_text,
        chapter,
        target_words,
        ROOT,
    )
    memory_text = _agent(ctx, "提炼剧情" + suffix, _memory_task(idx, outline, editor_text, ctx))
    summary = steps.parse_summary(memory_text) if memory_text is not None else {}
    return {
        "gate": gate,
        "summary": summary,
        "editor_text": editor_text,
        "failed": False,
    }


def _publish_track(ctx, idx, track, outline, meta, target_words, env):
    """Publish one track's chapter when the gate passed; K4/K5 handled in payload."""
    gate = track.get("gate") or {}
    if not gate.get("passed"):
        return {"draft": None, "pub": None, "verify": None}
    editor_text = track.get("editor_text") or ""
    content_html = publish_stock.to_html(editor_text)
    chapter = outline["chapter1"] if idx == 0 else outline["chapter2"]
    start_num = int(meta.get("start_num") or 1) + idx
    try:
        new_resp = _fanqie_post(
            ctx,
            FANQIE + "/api/author/article/new_article/v0/",
            {
                "book_id": str(meta.get("book_id") or ctx.book_id),
                "need_reuse": "0",
                "aid": "2503",
                "app_name": "muye_novel",
            },
            env,
        )
        draft = steps.build_draft_payload(
            {"book_id": str(meta.get("book_id") or ctx.book_id), "content_html": content_html},
            start_num,
            new_resp,
            chapter,
        )
        if draft is None:
            return {"draft": None, "pub": None, "verify": None}
        _fanqie_post(
            ctx,
            FANQIE + "/api/author/article/cover_article/v0/",
            {
                "book_id": draft["book_id"],
                "item_id": draft["item_id"],
                "title": draft["title"],
                "content": draft["content_html"],
                "volume_id": draft["volume_id"],
                "volume_name": draft["volume_name"],
                "aid": "2503",
                "app_name": "muye_novel",
            },
            env,
        )
        pub_raw = _fanqie_post(
            ctx,
            FANQIE + "/api/author/publish_article/v0/",
            {
                "item_id": draft["item_id"],
                "book_id": draft["book_id"],
                "content": draft["content_html"],
                "title": draft["title"],
                "volume_id": draft["volume_id"],
                "volume_name": draft["volume_name"],
                "timer_status": "0",
                "timer_time": "0",
                "publish_status": "1",
                "need_pay": "0",
                "use_ai": "2",
                "device_platform": "pc",
                "speak_type": "0",
                "timer_chapter_preview": "[]",
                "has_chapter_ad": "false",
                "chapter_ad_types": "",
                "aid": "2503",
                "app_name": "muye_novel",
            },
            env,
        )
        pub = steps.parse_publish_response(pub_raw)
        if pub.get("published"):
            ctx.published += 1
        verify = None
        if pub.get("published"):
            verify_resp = _fanqie_get(
                ctx,
                FANQIE + "/api/author/chapter/chapter_list/v1",
                {
                    "aid": "2503",
                    "app_name": "muye_novel",
                    "book_id": draft["book_id"],
                    "page_index": "0",
                    "page_count": "50",
                },
                env,
            )
            verify = steps.parse_review(verify_resp, draft["item_id"])
        return {"draft": draft, "pub": pub, "verify": verify}
    except Exception as exc:  # noqa: BLE001
        ctx.failed_nodes.append("发布" + ("A" if idx == 0 else "B"))
        ctx.errors.append(f"发布链: {str(exc)[:300]}")
        return {"draft": None, "pub": None, "verify": None, "error": str(exc)[:300]}


def _wrapup(ctx, conn, db_path, novel_id):
    _run_tool(ctx, "采集阅读数据", lambda: collect_reader_stats.run(db_path))
    _run_tool(ctx, "全员写日记", lambda: write_diaries.write(conn, novel_id, "daily"))
    _run_tool(ctx, "同步设定知识库", lambda: novel_knowledge.sync_latest(conn))
    _run_tool(ctx, "回填行动项", lambda: auto_fill_actions.run(db_path, novel_id=novel_id))


def _generate(ctx, conn, stock, env, run_id, out_file):
    """The fresh-chapter branch: metadata -> planner -> guard -> A/B -> publish
    -> payload -> record. Returns (payload, published_count, target)."""
    target = int(stock.get("target") or 2)
    cfg = {
        "premise": stock.get("novel_premise") or "",
        "platform": "fanqie",
        "daily": target,
        "novel_title": stock.get("book_name") or "",
        "keywords": stock.get("novel_keywords") or "",
        "genre": stock.get("novel_genre") or "",
        "book_id": stock.get("book_id") or "",
    }
    ctx.book_id = str(stock.get("book_id") or "")
    ctx.book_name = str(stock.get("book_name") or "")

    book_list = _fanqie_get(
        ctx,
        FANQIE + "/api/author/book/book_list/v0",
        {"aid": "2503", "app_name": "muye_novel", "page_index": "0", "page_count": "20"},
        env,
    )
    start = steps.compute_start_meta(cfg, book_list)
    ctx.book_name = start["book_name"] or ctx.book_name

    prev = _get_meta(ctx, start["book_id"])
    if prev is None:
        raise RuntimeError("读本地资料失败")
    prev_for_meta = prev if prev.get("book_name") else None
    ctx.writing_context = steps.build_writing_context(prev)
    target_words = int(prev.get("target_words") or 2000)

    work_meta_task = (
        "premise：" + str(start.get("premise") or "")
        + "；题材：" + str(start.get("genre") or (prev_for_meta or {}).get("genre") or "")
        + "；关键词：" + str(start.get("keywords") or "")
        + "；现有书名：" + str(start.get("book_name") or "")
        + "；现有主角：" + _j((prev_for_meta or {}).get("protagonists") or [])
        + "；上一章：" + _j((prev_for_meta or {}).get("last_chapter") or None)
        + "。已有主角/书名请沿用，只补全缺的字段；上一章不为空时卷目标要衔接剧情。"
    )
    work_meta_text = _agent(ctx, "生成作品资料", work_meta_task)
    if work_meta_text is None:
        raise RuntimeError("生成作品资料失败")
    src = {
        **start,
        "prev_meta": prev_for_meta,
        "writing_context": ctx.writing_context,
        "novel_id": ctx.novel_id,
    }
    meta = steps.parse_work_meta(work_meta_text, src)

    if meta.get("meta_needed"):
        modify_resp = _fanqie_post(
            ctx,
            FANQIE + "/api/author/book/modify_book/v0/",
            {
                "aid": "2503",
                "app_name": "muye_novel",
                "book_id": str(meta.get("book_id") or ""),
                "book_name": meta.get("book_name") or "",
                "gender": meta.get("gender") or "1",
                "abstract": meta.get("abstract") or "",
                "category_id": meta.get("category_id") or "",
                "original_type": "1",
                "label_id_list": meta.get("label_id_list") or "",
                "protagonist_name_1": meta.get("protagonist") or "",
                "protagonist_name_2": meta.get("secondary_name") or "",
            },
            env,
        )
        if isinstance(modify_resp, dict) and modify_resp.get("code") != 0:
            ctx.warnings.append("提交作品资料: " + str(modify_resp.get("message") or modify_resp)[:200])

    prev_blueprints = (prev_for_meta or {}).get("blueprints") or []
    planner_task = (
        "premise：" + str(meta.get("premise") or "")
        + "；主角：" + str(meta.get("protagonist") or "")
        + "；日更两章，章纲要有钩子"
        + (
            "；上一章：" + _j((prev_for_meta or {}).get("last_chapter") or None)
            + "，请接着剧情往后写两章；前情提要：" + ctx.writing_context
            + "；已有圣经：" + _j((prev_for_meta or {}).get("bible") or None)
            + "。已有圣经非空时必须沿用其角色/世界观/关系/风格，只做增量补充，不得另起炉灶；可用蓝图："
            + _j(
                [
                    b
                    for b in prev_blueprints
                    if int(b.get("seq") or 0) >= int(meta.get("start_num") or 1)
                    and int(b.get("seq") or 0) < int(meta.get("start_num") or 1) + 2
                ]
            )
            + "，若对应章节蓝图存在，必须优先采用其标题/大纲/钩子，不得另起炉灶"
            if (prev_for_meta or {}).get("last_chapter")
            else ""
        )
    )
    planner_text = _agent(ctx, "Planner出大纲", planner_task)
    if planner_text is None:
        raise RuntimeError("Planner出大纲失败")
    outline = steps.parse_planner_outline(planner_text, prev_for_meta, meta)

    if not ctx.dry_run:
        bible_file = ROOT / "n8n_tmp" / "bible.json"
        bible_file.parent.mkdir(parents=True, exist_ok=True)
        bible_file.write_text(
            _j({"book_id": meta.get("book_id") or "", "bible": outline.get("bible")}),
            encoding="utf-8",
        )
        _run_tool(
            ctx,
            "初始化设定知识库",
            lambda: novel_knowledge.sync_from_bible(conn, ctx.novel_id, outline.get("bible")),
        )

    guard_task = (
        "故事圣经：" + _j(outline.get("bible") or {})
        + "；两章细纲：" + _j({"chapter1": outline["chapter1"], "chapter2": outline["chapter2"]})
        + "；记忆包：" + ctx.writing_context
    )
    guard_text = _agent(ctx, "守护细纲", guard_task)
    guard = steps.parse_guard(guard_text, outline) if guard_text is not None else {
        "bible": outline.get("bible"),
        "chapter1": outline["chapter1"],
        "chapter2": outline["chapter2"],
        "constraints": [],
        "character_beats": {},
        "guard_passed": None,
        "guard_issues": [],
    }

    track_a = _run_track(ctx, conn, 0, outline, guard, meta, target_words, env)
    track_b = _run_track(ctx, conn, 1, outline, guard, meta, target_words, env, track_a)
    pub_a = _publish_track(ctx, 0, track_a, outline, meta, target_words, env)
    pub_b = _publish_track(ctx, 1, track_b, outline, meta, target_words, env)
    track_a.update(pub_a)
    track_b.update(pub_b)

    payload = steps.build_payload(
        run_id, meta, outline, track_a, track_b, ctx.costs, ctx.failed_nodes
    )
    if not ctx.dry_run:
        out_path = Path(out_file) if out_file else ROOT / "n8n_tmp" / "daily_result.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_j(payload), encoding="utf-8")
        _run_tool(ctx, "记录作品资料", lambda: record_work.record_payload(conn, payload))
    published = sum(1 for c in payload.get("chapters") or [] if c.get("status") == "published")
    return payload, published, target


def _finish_run(conn, ctx, run_id, status, published=0, error="", detail=None):
    conn.execute(
        "UPDATE daily_runs SET status=?, finished_at=?, failed_nodes=?, error=?, "
        "published=?, detail=? WHERE run_id=?",
        (
            status,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            _j(ctx.failed_nodes),
            str(error)[:500],
            published,
            _j(detail or {}),
            run_id,
        ),
    )
    conn.commit()


def daily(conn, chapters=None, trigger="manual", dry_run=False, db_path=None, env=None, out_file=None):
    """Run one daily shift. Returns the run summary with an explicit status."""
    if chapters:
        try:
            n = max(1, min(int(chapters), 10))
        except (TypeError, ValueError):
            n = 0
        if n:
            set_many(conn, {"pending_publish": str(n)})
    if db_path is None:
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
    db_path = str(Path(db_path).resolve())
    env = env if env is not None else config.load_env()
    for k, v in env.items():
        os.environ.setdefault(k, v)
    book = current_book.current_book(conn)
    ctx = _Ctx(book["novel_id"], db_path, dry_run, book["book_id"], "")
    run_id = "scheduler-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not dry_run:
        conn.execute(
            "INSERT INTO daily_runs(run_id, novel_id, trigger, source, status, started_at, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (run_id, ctx.novel_id, trigger, "scheduler", "running", started, started),
        )
        conn.commit()
    try:
        if not dry_run:
            _run_tool(
                ctx,
                "备份数据库",
                lambda: backup.backup_db(db_path, ROOT / "backups"),
            )
        pre = _preflight(ctx, conn, env, trigger)
        if pre.get("skipped"):
            if not dry_run:
                # A skipped scheduled run must not leave a forever-running row.
                conn.execute("DELETE FROM daily_runs WHERE run_id=?", (run_id,))
                conn.commit()
            return {"ok": False, "skipped": True, "run_id": run_id, "reasons": pre["reasons"]}
        if not pre["ok"]:
            if not dry_run:
                _finish_run(conn, ctx, run_id, "failed", error="；".join(pre["reasons"]))
            return {
                "ok": False,
                "skipped": False,
                "run_id": run_id,
                "status": "failed",
                "published": 0,
                "failed_nodes": ctx.failed_nodes,
                "error": "；".join(pre["reasons"]),
                "reasons": pre["reasons"],
            }

        stock = check_stock.check_stock(conn)
        # A manual chapter override is a one-shot target: consume it so the
        # next scheduled run falls back to daily_chapters.
        set_many(conn, {"pending_publish": "0"})
        payload = None
        published = 0
        if stock["need"] <= 0:
            result = _run_tool(
                ctx,
                "发布存稿",
                lambda: publish_stock.publish_batch(conn, ctx.novel_id, stock["target"], env),
            )
            published = int((result or {}).get("published") or 0)
            ctx.published = published
            if not result.get("ok") and result.get("error"):
                ctx.failed_nodes.append("发布存稿")
        else:
            payload, published, _target = _generate(ctx, conn, stock, env, run_id, out_file)
            ctx.published = published

        _wrapup(ctx, conn, db_path, ctx.novel_id)

        if published >= int(stock.get("target") or 1) and not ctx.failed_nodes:
            status = "completed"
        elif published > 0:
            status = "partial"
        else:
            status = "failed"
        error = "；".join(ctx.errors) if ctx.errors else ""
        detail = {
            "warnings": ctx.warnings,
            "agent_calls": len(ctx.agent_calls),
            "tools": ctx.tool_attempts,
            "reasons": pre.get("reasons") or [],
        }
        if not dry_run:
            _finish_run(conn, ctx, run_id, status, published, error, detail)
        return {
            "ok": status == "completed",
            "skipped": False,
            "run_id": run_id,
            "status": status,
            "published": published,
            "target": int(stock.get("target") or 1),
            "failed_nodes": ctx.failed_nodes,
            "warnings": ctx.warnings,
            "error": error,
            "reasons": pre.get("reasons") or [],
            "dry_run": dry_run,
        }
    except Exception as exc:  # noqa: BLE001
        ctx.errors.append(f"调度器异常: {str(exc)[:400]}")
        error = "；".join(ctx.errors)
        if not dry_run:
            _finish_run(
                conn,
                ctx,
                run_id,
                "failed",
                ctx.published,
                error,
                {"warnings": ctx.warnings},
            )
        return {
            "ok": False,
            "skipped": False,
            "run_id": run_id,
            "status": "failed",
            "published": ctx.published,
            "failed_nodes": ctx.failed_nodes,
            "warnings": ctx.warnings,
            "error": error,
            "dry_run": dry_run,
        }
    finally:
        if ctx.lock_path:
            preflight.release_lock(ctx.lock_path)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Python 日更调度器（替代 n8n 66 节点链路）")
    ap.add_argument("--db", default=str(ROOT / "demo.db"))
    ap.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    ap.add_argument("--chapters", type=int, default=0, help="本次发布章数（默认读设置）")
    ap.add_argument("--dry-run", action="store_true", help="不调 LLM/发布/工具，走全链占位")
    args = ap.parse_args()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(str(db_path))
    try:
        result = daily(
            conn,
            chapters=args.chapters or None,
            trigger=args.trigger,
            dry_run=args.dry_run,
            db_path=str(db_path),
        )
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") or result.get("skipped") else 1


if __name__ == "__main__":
    sys.exit(main())
