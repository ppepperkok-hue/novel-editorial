"""Pure step helpers for the Python daily scheduler (de-n8n migration).

Each function mirrors one n8n code node from `n8n/novel_workflow.json`.
Keep the behaviours byte-compatible with the workflow JSON; see
`docs/planning/de-n8n-mapping.md` for the node-by-node mapping.
"""

from __future__ import annotations

import json
import re


def robust_json(text):
    """Tolerant JSON parse mirroring the n8n `tryParse` helper."""
    t = str(text).replace("```json", "").replace("```", "").strip()
    clean = lambda x: re.sub(r",\s*([}\]])", r"\1", x).strip()  # noqa: E731
    try:
        return json.loads(t)
    except ValueError:
        pass
    for _ in range(8):
        m = re.search(r',\s*"[^"]*"?\s*:\s*"[^"]*$', t)
        if m:
            t = t[: m.start()]
            continue
        m = re.search(r',\s*"[^"]*"$', t)
        if m:
            t = t[: m.start()]
            continue
        break
    t = clean(t)
    stack = []
    in_str = False
    esc = False
    for ch in t:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch in "[{":
            stack.append(ch)
        elif ch in "]}":
            if stack:
                stack.pop()
    while stack:
        t += "}" if stack.pop() == "{" else "]"
    try:
        return json.loads(t)
    except ValueError:
        return None


def _dedupe(seq):
    seen = set()
    out = []
    for x in seq:
        if not x:
            continue
        if isinstance(x, (dict, list)):
            key = json.dumps(x, ensure_ascii=False, sort_keys=True)
        else:
            key = str(x)
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out


def _finish_status_text(prev):
    fs = prev.get("finish_status")
    if fs == "finishing":
        return "收尾模式：剩余 " + str(prev.get("finish_remaining") or 0) + " 章，本批需推进结局、回收伏笔、给出角色归宿"
    if fs == "finished":
        return "已完结，停止日更"
    return "连载中"


def build_writing_context(prev):
    """Mirror the `解析本地资料` writing_context assembly (17 fields)."""
    prev = prev or {}
    bible = prev.get("bible") or {}
    parts = [
        "上一章结尾："
        + (str(prev.get("prev_ending") or "")[-800:] or "本书第1章，无需承接前文"),
        "最近摘要：" + json.dumps(prev.get("recent_summaries") or [], ensure_ascii=False)[:1200],
        "角色状态：" + json.dumps(prev.get("character_states") or {}, ensure_ascii=False),
        "活跃伏笔：" + json.dumps(prev.get("plot_threads") or [], ensure_ascii=False),
        "角色卡：" + json.dumps(bible.get("characters") or [], ensure_ascii=False)[:1400],
        "人物关系：" + json.dumps(bible.get("relationships") or [], ensure_ascii=False)[:900],
        "世界观规则：" + json.dumps(bible.get("world_rules") or [], ensure_ascii=False)[:700],
        "已有标题（不能重复）：" + json.dumps(prev.get("existing_titles") or [], ensure_ascii=False),
        "风格指南：" + str(bible.get("style_guide") or ""),
        "卷目标：" + str(prev.get("volume_goal") or ""),
        "角色成长轨迹：" + json.dumps((prev.get("character_evolution") or [])[-6:], ensure_ascii=False),
        "完结状态：" + _finish_status_text(prev),
        "阅读反馈：" + json.dumps(prev.get("reader_feedback") or {}, ensure_ascii=False),
        "目标字数：" + str(prev.get("target_words") or 2000),
        "风格微调：" + str(prev.get("style_tweak") or "无"),
        "近期热点：" + json.dumps(prev.get("hot_topics") or {}, ensure_ascii=False)[:1000],
        "设定知识库：" + json.dumps(prev.get("novel_knowledge") or [], ensure_ascii=False)[:1200],
    ]
    return "；".join(parts)


def resolve_category(genre):
    """Mirror the genre -> category mapping in `解析作品资料`."""
    g = str(genre or "")
    if re.search("都市|赘婿|神医|战神", g):
        return "124", ["124", "262"]
    if re.search("玄幻", g):
        return "258", ["258", "257"]
    if re.search("科幻|末世", g):
        return "8", ["8", "57"]
    if re.search("悬疑|灵异|盗墓", g):
        return "10", ["10", "539"]
    if re.search("历史", g):
        return "273", ["273", "272"]
    return "259", ["259", "257"]


def parse_work_meta(text, src):
    """Mirror `解析作品资料`; raises when the agent JSON is unusable."""
    meta = robust_json(text)
    if meta is None:
        raise ValueError("JSON解析失败: " + str(text)[:200])
    prev = src.get("prev_meta") or {}
    genre = str(meta.get("genre") or src.get("genre") or "")
    category_id, labels = resolve_category(genre)
    old_prot = None
    if prev.get("protagonists"):
        old_prot = prev["protagonists"][0]
    prot = meta.get("protagonist") or {}
    prot_name = str(
        prot.get("name")
        or (old_prot and old_prot.get("name"))
        or "主角"
    )
    protagonists = [
        {
            "name": prot_name,
            "role": "主角",
            "traits": str(prot.get("traits") or (old_prot and old_prot.get("traits")) or ""),
            "goals": str(prot.get("goals") or (old_prot and old_prot.get("goals")) or ""),
        }
    ]
    secondary = str(meta.get("secondary_name") or "")
    if secondary:
        protagonists.append({"name": secondary, "role": "配角", "traits": "", "goals": ""})
    abstract = re.sub(r"\s+", " ", str(meta.get("abstract") or src.get("abstract") or ""))
    book_name = str(meta.get("book_name") or src.get("book_name") or "未命名")
    tags = [str(t) for t in (meta.get("tags") or []) if isinstance(meta.get("tags"), list)]
    gender = "0" if meta.get("gender") in (0, "0") else "1"
    return {
        "premise": src.get("premise"),
        "platform": src.get("platform"),
        "daily": src.get("daily"),
        "keywords": src.get("keywords"),
        "book_id": src.get("book_id"),
        "start_num": src.get("start_num"),
        "book_name": book_name,
        "abstract": abstract,
        "tags": tags,
        "gender": gender,
        "category_id": category_id,
        "label_id_list": ",".join(labels),
        "protagonists": protagonists,
        "protagonist": prot_name,
        "secondary_name": secondary,
        "volume_goal": str(meta.get("volume_goal") or ""),
        "prev_meta": prev,
        "meta_needed": src.get("meta_needed"),
        "writing_context": src.get("writing_context") or "",
    }


def merge_bible(prev_bible, next_bible):
    """Mirror the `mergeBible` helper in `解析大纲`."""
    if not next_bible or not isinstance(next_bible, dict):
        return prev_bible
    out = dict(prev_bible or {})
    out.update(next_bible)
    by_name = {}
    chars = []
    for c in (prev_bible or {}).get("characters") or []:
        if c and c.get("name"):
            by_name[c["name"]] = dict(c)
            chars.append(by_name[c["name"]])
    for c in next_bible.get("characters") or []:
        if c and c.get("name"):
            if by_name.get(c["name"]):
                by_name[c["name"]].update(c)
            else:
                by_name[c["name"]] = dict(c)
                chars.append(by_name[c["name"]])
    if chars:
        out["characters"] = chars
    rel = []
    seen = set()
    for r in list((prev_bible or {}).get("relationships") or []) + list(
        next_bible.get("relationships") or []
    ):
        if not r or not r.get("from") or not r.get("to"):
            continue
        k = str(r["from"]) + "|" + str(r["to"]) + "|" + str(r.get("relation") or "")
        if k in seen:
            continue
        seen.add(k)
        rel.append(r)
    if rel:
        out["relationships"] = rel
    wr = _dedupe(
        list((prev_bible or {}).get("world_rules") or [])
        + list(next_bible.get("world_rules") or [])
    )
    if wr:
        out["world_rules"] = wr
    return out


def _norm_chapter(ch, i):
    if isinstance(ch, dict):
        return {
            "title": str(ch.get("title") or ch.get("chapter_title") or ("第" + str(i + 1) + "章 开局")),
            "outline": str(
                ch.get("outline")
                or ch.get("content")
                or ch.get("summary")
                or json.dumps(ch, ensure_ascii=False)
            ),
            "hook": str(ch.get("hook") or ""),
            "hook_type": str(ch.get("hook_type") or ""),
            "emotion": str(ch.get("emotion") or ""),
            "position": str(ch.get("position") or ""),
            "pacing": str(ch.get("pacing") or ""),
            "scenes": ch.get("scenes") if isinstance(ch.get("scenes"), list) else [],
            "plant_foreshadow": str(ch.get("plant_foreshadow") or ""),
            "recover_foreshadow": str(ch.get("recover_foreshadow") or ""),
            "character_arc": (
                ch.get("character_arc") if isinstance(ch.get("character_arc"), dict) else {}
            ),
        }
    s = str(ch or ("第" + str(i + 1) + "章 开局"))
    return {"title": s, "outline": s, "hook": ""}


def parse_planner_outline(text, prev_meta, meta):
    """Mirror `解析大纲`; requires >= 2 chapter outlines (no silent fallback)."""
    outline = robust_json(text)
    if outline is None:
        raise ValueError("JSON解析失败: " + str(text)[:200])
    if not isinstance(outline.get("chapter_outlines"), list) or len(outline["chapter_outlines"]) < 2:
        raise ValueError("Planner输出缺少两章章纲，拒绝静默兜底")
    arr = [_norm_chapter(ch, i) for i, ch in enumerate(outline["chapter_outlines"])]
    prev_bible = (prev_meta or {}).get("bible")
    bible = merge_bible(prev_bible, outline.get("bible"))
    return {
        "premise": str(outline.get("premise") or (meta or {}).get("premise") or ""),
        "genre": str(outline.get("genre") or ""),
        "title": str(outline.get("title") or ""),
        "keywords": ",".join(str(k) for k in (outline.get("keywords") or [])),
        "bible": bible,
        "chapter1": arr[0],
        "chapter2": arr[1],
    }


def parse_guard(text, outline):
    """Mirror `解析守护`; guard failures degrade to empty constraints."""
    out = {
        "bible": outline.get("bible"),
        "chapter1": outline.get("chapter1"),
        "chapter2": outline.get("chapter2"),
        "constraints": [],
        "character_beats": {},
        "guard_passed": None,
        "guard_issues": [],
    }
    g = None
    t = str(text or "").replace("```json", "").replace("```", "").strip()
    g = robust_json(t)
    if g is None:
        m = re.search(r"\{[\s\S]*\}", t)
        if m:
            g = robust_json(m.group(0))
    if isinstance(g, dict):
        out["guard_passed"] = bool(g.get("passed"))
        out["guard_issues"] = g.get("issues") if isinstance(g.get("issues"), list) else []
        out["constraints"] = [c for c in (g.get("constraints") or []) if c][:8]
        if isinstance(g.get("character_beats"), dict):
            out["character_beats"] = g["character_beats"]
    return out


def parse_summary(text):
    """Mirror `整理剧情A/B` with the default summary fallback."""
    default = {
        "summary": "",
        "character_updates": {},
        "plot_events": [],
        "foreshadowing_planted": [],
        "foreshadowing_recovered": [],
    }
    t = str(text or "").replace("```json", "").replace("```", "").strip()
    summary = robust_json(t)
    if summary is None:
        m = re.search(r"\{[\s\S]*\}", t)
        if m:
            summary = robust_json(m.group(0))
    return summary or default


def _load_flavor_words(root):
    try:
        from pathlib import Path

        data = json.loads((Path(root) / "ai_words.json").read_text(encoding="utf-8"))
        words = data.get("ai_flavor")
        return words if isinstance(words, list) and words else DEFAULT_FLAVOR_WORDS
    except (OSError, ValueError, TypeError):
        return DEFAULT_FLAVOR_WORDS


DEFAULT_FLAVOR_WORDS = [
    "突然", "顿时", "仿佛", "缓缓", "不由得", "微微一", "嘴角", "眼神一凝", "低沉",
    "冷哼一声", "心中一动", "不禁", "瞬间", "面无表情", "淡淡", "不由自主", "情不自禁",
    "微微一愣", "缓缓说道", "与此同时", "一股强大的气息",
]


def quality_gate(
    edited_text,
    review_text,
    reader_text,
    editor_text,
    title_obj,
    target_words=2000,
    root=None,
):
    """Mirror `质量门A/B`: mechanical checks + reader/editor verdicts."""
    if not edited_text or not str(edited_text).strip():
        return {"passed": False, "errors": ["润色正文为空"], "review": None, "reader": None}
    edited = str(edited_text)
    chars = len(re.findall(r"[\u4e00-\u9fff]", edited))
    target = int(target_words or 2000)
    flavor = _load_flavor_words(root)
    esc = lambda w: re.escape(w)  # noqa: E731
    cnt = lambda pat: len(re.findall(pat, edited))  # noqa: E731
    mech = []
    sudden = cnt(r"突然")
    banned = cnt(re.compile("|".join(esc(w) for w in flavor)))
    exclaim = cnt(r"！")
    ellipsis = cnt(r"……")
    double_q = cnt(r"[！？]{2,}")
    if sudden > 1:
        mech.append("突然×" + str(sudden) + "（限1）")
    if banned > 3:
        mech.append("AI高频词×" + str(banned))
    if double_q > 0:
        mech.append("连续问号/感叹号")
    if exclaim > 8:
        mech.append("感叹号×" + str(exclaim) + "（限8）")
    if ellipsis > 5:
        mech.append("省略号×" + str(ellipsis) + "（限5）")
    if chars < int(target * 0.75):
        mech.append("字数不足 " + str(chars) + "（目标" + str(target) + "）")
    if mech:
        return {
            "passed": False,
            "errors": mech,
            "review": robust_json(review_text) if review_text else None,
            "reader": robust_json(reader_text) if reader_text else None,
            "chars": chars,
        }
    reader = robust_json(reader_text) if reader_text else None
    review = robust_json(review_text) if review_text else None
    editor = robust_json(editor_text) if editor_text else None
    reader_passed = True
    reader_note = ""
    if reader:
        reader_passed = bool(reader.get("would_read_next")) and float(reader.get("score") or 0) >= 7 and float(reader.get("hook_rating") or 0) >= 7
    else:
        reader_note = "读者审稿缺失，已降级"
    if editor:
        editor_passed = editor.get("verdict") == "pass"
        editor_note = ""
    else:
        editor_note = "主编终审缺失，按双审降级"
        editor_passed = bool(review and review.get("passed") and reader_passed) if review else True
    if not editor_passed:
        return {
            "passed": False,
            "errors": ["主编终审未过"],
            "review": review,
            "reader": reader,
            "editor": editor,
            "chars": chars,
            "readerNote": reader_note,
            "editorNote": editor_note,
        }
    return {
        "passed": True,
        "review": review,
        "reader": reader,
        "editor": editor,
        "chars": chars,
        "editedText": edited,
        "title": title_obj,
        "mechanical_issues": mech,
        "readerNote": reader_note,
        "editorNote": editor_note,
    }


def clean_chapter_title(title_obj):
    """Mirror `解析草稿A/B` title prefix removal."""
    if isinstance(title_obj, dict):
        raw = str(title_obj.get("title") or title_obj.get("chapter_title") or "")
    else:
        raw = str(title_obj)
    return re.sub(r"^\s*第\s*\d+\s*章[：:\s]*", "", raw)


def build_draft_payload(layout, start_num, resp, title_obj):
    """Mirror `解析草稿A/B`: assemble item/volume/title/content for publishing."""
    data = resp.get("data") if isinstance(resp, dict) and isinstance(resp.get("data"), dict) else resp
    if not isinstance(data, dict) or not data.get("item_id"):
        return None
    clean = clean_chapter_title(title_obj)
    title = "第 " + str(start_num) + " 章 " + clean
    volume_id = str(data.get("volume_id") or "")
    volume_name = "正文"
    vd = data.get("volume_data")
    if isinstance(vd, str):
        try:
            vd = json.loads(vd)
        except ValueError:
            vd = None
    if isinstance(vd, list):
        hit = next((v for v in vd if str(v.get("volume_id")) == volume_id), None)
        hit = hit or (vd[0] if vd else None)
        if hit and hit.get("volume_name"):
            volume_name = str(hit["volume_name"])
    return {
        "item_id": str(data["item_id"]),
        "book_id": layout.get("book_id"),
        "volume_id": volume_id,
        "volume_name": volume_name,
        "title": title,
        "content_html": layout.get("content_html"),
    }


def parse_publish_response(body_text):
    """Mirror `校验发布A/B`: code==0 means published."""
    if isinstance(body_text, str):
        try:
            parsed = json.loads(body_text)
        except ValueError:
            parsed = None
    else:
        parsed = body_text
    if not isinstance(parsed, dict) or parsed.get("code") != 0:
        return {
            "published": False,
            "item_id": None,
            "error": (parsed and parsed.get("message")) or str(body_text)[:300],
        }
    data = parsed.get("data") or {}
    return {
        "published": True,
        "item_id": str(data.get("item_id") or data.get("article_id") or "") or None,
        "message": parsed.get("message"),
    }


def compute_start_meta(cfg, book_list_resp):
    """Mirror `算章节号`: resolve start chapter number and meta_needed."""
    data = book_list_resp
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            data = {}
    if isinstance(data, dict) and "body" in data and data["body"] is not None:
        body = data["body"]
        if isinstance(body, str):
            try:
                data = json.loads(body)
            except ValueError:
                data = {}
        else:
            data = body
    blist = []
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        blist = data["data"].get("book_list") or []
    book_id = cfg.get("book_id")
    if not book_id:
        raise ValueError("未找到活跃作品：请先确认创意并自动建书")
    target = next(
        (b for b in blist if str(b.get("book_id")) == str(book_id)),
        None,
    )
    if target is None:
        raise ValueError(
            "番茄账号中未找到 book_id=" + str(book_id) + " 的书籍，请检查绑定"
        )
    start_num = int(target.get("chapter_number") or 0) + 1
    book_name = str(target.get("book_name") or "")
    abstract = str(target.get("abstract") or "")
    local_title = str(cfg.get("novel_title") or "").strip()
    title_mismatch = bool(local_title) and book_name.strip() != local_title
    meta_needed = book_name.startswith("用户") or len(abstract) < 50 or title_mismatch
    return {
        "premise": cfg.get("premise"),
        "platform": cfg.get("platform") or "fanqie",
        "daily": cfg.get("daily") or 2,
        "novel_title": local_title,
        "keywords": cfg.get("keywords") or "",
        "genre": cfg.get("genre") or "",
        "book_id": str(book_id),
        "start_num": start_num,
        "book_name": book_name,
        "abstract": abstract,
        "meta_needed": meta_needed,
    }


def parse_review(raw, item_id):
    """Mirror `解析复核A/B`: chapter_list lookup of the published item."""
    if isinstance(raw, str):
        try:
            resp = json.loads(raw)
        except ValueError:
            resp = None
    else:
        resp = raw
    if not isinstance(resp, dict):
        return {
            "status": "unknown",
            "item_id": item_id,
            "found": False,
            "error": "复核响应非JSON",
        }
    lst = []
    if isinstance(resp.get("data"), dict):
        lst = resp["data"].get("item_list") or []
    found = next(
        (x for x in lst if str(x.get("item_id")) == str(item_id)),
        None,
    )
    status = "pending"
    if found and int(found.get("article_status") or 0) == 1:
        status = "published"
    return {
        "status": status,
        "item_id": item_id,
        "found": bool(found),
        "article_status": int(found.get("article_status")) if found else None,
    }


def build_payload(run_id, meta, outline, track_a, track_b, costs, failed_nodes):
    """Mirror `汇总运行结果` incl. K2/K5 compensation rows."""
    now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    book_id = meta.get("book_id") or "unknown"
    run_id_full = str(run_id) + "-" + str(book_id)
    chapters = []
    ch1 = (outline or {}).get("chapter1") or {}
    ch2 = (outline or {}).get("chapter2") or {}

    def append_track(idx, ch_obj, gate, draft, pub, summary):
        seq = int(meta.get("start_num") or 1) + idx
        if gate and gate.get("passed") is False:
            chapters.append(
                {
                    "seq": seq,
                    "title": str(ch_obj.get("title") or ""),
                    "outline": str(ch_obj.get("outline") or ""),
                    "status": "draft",
                    "words": int(gate.get("chars") or 0),
                    "fanqie_item_id": "",
                    "published_at": "",
                    "error": "质量门未通过：" + (";".join(gate.get("errors") or []) or "unknown"),
                    "summary": summary or {},
                    "ending_excerpt": "",
                    "quality_passed": False,
                    "content": gate.get("editedText") or "",
                }
            )
            return True
        if draft and draft.get("item_id"):
            ok_pub = bool(pub and pub.get("published"))
            chapters.append(
                {
                    "seq": seq,
                    "title": draft.get("title") or "",
                    "outline": str(ch_obj.get("outline") or ""),
                    "status": "published" if ok_pub else "reviewed",
                    "words": int(gate.get("chars") or 0) if gate else 0,
                    "fanqie_item_id": draft.get("item_id") or "",
                    "published_at": now if ok_pub else "",
                    "error": "" if ok_pub else ((pub and pub.get("error")) or str(pub or {})[:200]),
                    "summary": summary or {},
                    "ending_excerpt": (gate.get("editedText") or "")[-220:] if gate else "",
                    "quality_passed": True,
                    "content": (gate.get("editedText") or "") if gate else "",
                }
            )
            return True
        return False

    a_covered = append_track(0, ch1, track_a.get("gate"), track_a.get("draft"), track_a.get("pub"), track_a.get("summary"))
    b_covered = append_track(1, ch2, track_b.get("gate"), track_b.get("draft"), track_b.get("pub"), track_b.get("summary"))

    # K5: gate passed but the draft/publish chain never produced a record.
    if track_a.get("gate") and track_a["gate"].get("passed") is True and not track_a.get("draft") and not a_covered:
        chapters.append(
            {
                "seq": int(meta.get("start_num") or 1),
                "title": str(ch1.get("title") or ""),
                "outline": str(ch1.get("outline") or ""),
                "status": "draft",
                "words": int(track_a["gate"].get("chars") or 0),
                "fanqie_item_id": "",
                "published_at": "",
                "error": "质量门通过但草稿创建/发布链中断",
                "summary": track_a.get("summary") or {},
                "ending_excerpt": "",
                "quality_passed": True,
                "content": track_a["gate"].get("editedText") or "",
            }
        )
    if track_b.get("gate") and track_b["gate"].get("passed") is True and not track_b.get("draft") and not b_covered:
        chapters.append(
            {
                "seq": int(meta.get("start_num") or 1) + 1,
                "title": str(ch2.get("title") or ""),
                "outline": str(ch2.get("outline") or ""),
                "status": "draft",
                "words": int(track_b["gate"].get("chars") or 0),
                "fanqie_item_id": "",
                "published_at": "",
                "error": "质量门通过但草稿创建/发布链中断",
                "summary": track_b.get("summary") or {},
                "ending_excerpt": "",
                "quality_passed": True,
                "content": track_b["gate"].get("editedText") or "",
            }
        )

    fail_names = ",".join(str(n) for n in (failed_nodes or []))
    if fail_names:
        # K2: any LLM/chain failure fills every uncovered track.
        if not a_covered:
            chapters.append(
                {
                    "seq": int(meta.get("start_num") or 1),
                    "title": str(ch1.get("title") or ""),
                    "outline": str(ch1.get("outline") or ""),
                    "status": "draft",
                    "words": 0,
                    "fanqie_item_id": "",
                    "published_at": "",
                    "error": "LLM链路失败：" + fail_names,
                    "summary": {},
                    "ending_excerpt": "",
                    "quality_passed": False,
                    "content": "",
                }
            )
        if not b_covered:
            chapters.append(
                {
                    "seq": int(meta.get("start_num") or 1) + 1,
                    "title": str(ch2.get("title") or ""),
                    "outline": str(ch2.get("outline") or ""),
                    "status": "draft",
                    "words": 0,
                    "fanqie_item_id": "",
                    "published_at": "",
                    "error": "LLM链路失败：" + fail_names,
                    "summary": {},
                    "ending_excerpt": "",
                    "quality_passed": False,
                    "content": "",
                }
            )

    return {
        "run_id": run_id_full,
        "book_id": book_id,
        "book_name": meta.get("book_name") or "",
        "genre": (outline or {}).get("genre") or "",
        "premise": (outline or {}).get("premise") or meta.get("premise") or "",
        "selling_point": "",
        "platform": meta.get("platform") or "fanqie",
        "tags": meta.get("tags") or [],
        "abstract": meta.get("abstract") or "",
        "protagonists": meta.get("protagonists") or [],
        "volume_goal": meta.get("volume_goal") or "",
        "outline": {
            "premise": (outline or {}).get("premise"),
            "genre": (outline or {}).get("genre"),
            "title": (outline or {}).get("title"),
            "keywords": (outline or {}).get("keywords"),
            "bible": (outline or {}).get("bible") or None,
            "chapter1": ch1,
            "chapter2": ch2,
        },
        "chapters": chapters,
        "costs": costs,
    }
