"""Rewrite the book with a continuity-aware pipeline.

Story bible -> chapter blueprints -> write chapters 1..N with memory context ->
review -> save drafts -> publish (waits past midnight if daily cap blocks) -> record.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2\outputs\novel-pipeline")
ENV = Path.home() / ".n8n" / ".env"
sys.path.insert(0, r"C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2")
sys.path.insert(0, str(ROOT))

from novel_pipeline import db  # noqa: E402
from tools.record_work import upsert_novel, upsert_characters, upsert_volume, upsert_chapters  # noqa: E402
from tools.paragraphs import to_html  # noqa: E402

BOOK_ID = os.environ.get("FANQIE_BOOK_ID", "YOUR_FANQIE_BOOK_ID")
VOLUME_ID = os.environ.get("FANQIE_VOLUME_ID", "YOUR_FANQIE_VOLUME_ID")
VOLUME_NAME = os.environ.get("FANQIE_VOLUME_NAME", "第一卷：默认")
MODEL = "deepseek-v4-flash"
WRITER_MODEL = os.environ.get("DEEPSEEK_WRITER_MODEL", "deepseek-v4-pro")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


def load_env():
    for line in open(ENV, encoding="utf-8"):
        line = line.strip()
        if line and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def llm(messages, temperature=0.7, model=None):
    model = model or MODEL
    body = json.dumps(
        {
            "model": model,
            "temperature": temperature,
            "messages": messages,
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + os.environ["DEEPSEEK_API_KEY"],
        },
    )
    for attempt in range(3):
        try:
            r = urllib.request.urlopen(req, timeout=120)
            data = json.loads(r.read().decode())
            msg = data["choices"][0]["message"]
            text = msg.get("content") or ""
            if not text.strip():
                text = msg.get("reasoning_content") or ""
            return text.strip()
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(3)


def extract_json(text):
    t = text.replace("```json", "").replace("```", "").strip()
    start = t.find("{")
    if start >= 0:
        for end in range(len(t) - 1, start - 1, -1):
            if t[end] == "}":
                try:
                    return json.loads(t[start : end + 1])
                except json.JSONDecodeError:
                    continue
    raise ValueError("JSON parse failed: " + t[:200])


def fanqie_req(path, params, method="POST"):
    headers = {
        "Cookie": os.environ["FANQIE_COOKIE"],
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://fanqienovel.com",
        "Referer": "https://fanqienovel.com/main/writer/",
        "X-Secsdk-Csrf-Token": os.environ["FANQIE_CSRF_TOKEN"],
    }
    url = "https://fanqienovel.com" + path
    data = None
    if method == "POST":
        data = urllib.parse.urlencode(params).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"
    else:
        url += "?" + urllib.parse.urlencode(params)
    r = urllib.request.urlopen(
        urllib.request.Request(url, data=data, headers=headers, method=method), timeout=30
    )
    return json.loads(r.read().decode())


def delete_chapter(item_id):
    for is_draft in ("0", "1"):
        try:
            d = fanqie_req(
                "/api/author/delete_article/v1",
                {"book_id": BOOK_ID, "item_id": item_id, "is_draft": is_draft},
            )
            if d.get("code") == 0:
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def cleanup_all_drafts():
    d = fanqie_req(
        "/api/author/chapter/draft_list/v1/",
        {"book_id": BOOK_ID, "aid": "2503", "app_name": "muye_novel",
         "page_index": "0", "page_count": "50"},
        method="GET",
    )
    items = (d.get("data") or {}).get("draft_list") or []
    for it in items:
        item_id = str(it.get("item_id") or "")
        if item_id:
            delete_chapter(item_id)
            print("cleanup draft", item_id)


def new_draft():
    d = fanqie_req(
        "/api/author/article/new_article/v0/",
        {"book_id": BOOK_ID, "need_reuse": "0", "aid": "2503", "app_name": "muye_novel"},
    )
    if d.get("code") != 0:
        raise RuntimeError("new_article: " + str(d))
    return d["data"]["item_id"]


def cover_draft(item_id, title, content_html):
    d = fanqie_req(
        "/api/author/article/cover_article/v0/",
        {
            "book_id": BOOK_ID,
            "item_id": item_id,
            "title": title,
            "content": content_html,
            "volume_id": VOLUME_ID,
            "volume_name": VOLUME_NAME,
            "aid": "2503",
            "app_name": "muye_novel",
        },
    )
    if d.get("code") != 0:
        raise RuntimeError("cover_article: " + str(d))


def publish_chapter(item_id, title, content):
    return fanqie_req(
        "/api/author/publish_article/v0/",
        {
            "item_id": item_id,
            "book_id": BOOK_ID,
            "content": content,
            "title": title,
            "volume_id": VOLUME_ID,
            "volume_name": VOLUME_NAME,
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
    )


def chinese_chars(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def wait_until_midnight():
    now = datetime.now()
    target = now.replace(hour=0, minute=0, second=30, microsecond=0)
    if target <= now:
        target = target.replace(day=target.day + 1)
    wait = (target - now).total_seconds() + 5
    print("daily cap hit, waiting", int(wait), "seconds until", target.isoformat())
    time.sleep(wait)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    load_env()
    conn = db.connect(ROOT / "demo.db")

    # 1. delete old pending chapters on Fanqie
    cleanup_all_drafts()
    old_items = [x.strip() for x in os.environ.get("FANQIE_OLD_ITEMS", "").split(",") if x.strip()]
    for item in old_items:
        ok = delete_chapter(item)
        print("delete", item, "ok" if ok else "FAILED")

    # 2. reset local story tables (keep novel row)
    row = conn.execute("SELECT id FROM novels WHERE book_id=?", (BOOK_ID,)).fetchone()
    novel_id = row["id"] if row else None
    if novel_id:
        conn.executescript(
            """
            DELETE FROM publish_logs WHERE chapter_id IN (SELECT id FROM chapters WHERE novel_id=%(n)s);
            DELETE FROM quality_reports WHERE chapter_id IN (SELECT id FROM chapters WHERE novel_id=%(n)s);
            DELETE FROM chapter_summaries WHERE chapter_id IN (SELECT id FROM chapters WHERE novel_id=%(n)s);
            DELETE FROM world_events WHERE novel_id=%(n)s;
            DELETE FROM plot_threads WHERE novel_id=%(n)s;
            DELETE FROM characters WHERE novel_id=%(n)s;
            DELETE FROM chapters WHERE novel_id=%(n)s;
            DELETE FROM volumes WHERE novel_id=%(n)s;
            """
            % {"n": novel_id}
        )
        conn.commit()

    # 3. story bible
    bible_prompt_system = (
        "你是资深网文架构师，擅长长篇网文设定。只输出JSON："
        "{style_guide(200-300字), characters(至少6个，每项含name/role/appearance/personality/background/abilities/growth_arc/speech_style), "
        "world_settings(至少8个，每项含category/name/description), main_plot(主线骨架300-500字), "
        "arcs(第一卷，含volume/title/goal/chapters/ending), golden_finger(金手指规则与限制)}"
    )
    bible_user = (
        "书名：捡到破碗后我修仙无敌了；题材：凡人修仙/苟道流；"
        "核心创意：凡人修仙：捡到一只会提纯灵物的破碗，从杂灵根苟到无敌；"
        "主角：陈凡（杂灵根，谨慎隐忍，装傻苟发育）。请设计完整世界观、角色阵容与第一卷框架。"
    )
    bible_path = Path(r"C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2\outputs\novel-pipeline\tools\rewrite_bible.json")
    bible = None
    if bible_path.exists():
        try:
            bible = json.loads(bible_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            bible = None
    if bible is None:
        bible = extract_json(llm([
            {"role": "system", "content": bible_prompt_system},
            {"role": "user", "content": bible_user},
        ]))
    Path(r"C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2\outputs\novel-pipeline\tools\rewrite_bible.json").write_text(
        json.dumps(bible, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("bible ok:", len(bible.get("characters", [])), "characters,", len(bible.get("world_settings", [])), "settings")

    arcs = bible.get("arcs") or bible.get("volumes") or []
    first_arc = arcs[0] if isinstance(arcs, list) and arcs else {}
    volume_goal = str(first_arc.get("goal") or bible.get("volume_goal") or "第一卷：主角用破碗苟住发育，从杂役一路逆袭。")

    # 4. blueprints for first 10 chapters
    bp_system = (
        "你是网文章纲规划师。只输出JSON：{chapters:[{seq,title(2-20字且全书唯一，不含第X章),"
        "outline(100-200字),scenes([3-5个]),characters([角色名]),emotion,"
        "hook_type(cliffhanger/revelation/question/twist/promise),hook}]}"
    )
    bp_user = (
        "主线骨架：" + str(bible.get("main_plot", ""))[:800] +
        "；第一卷目标：" + volume_goal +
        "；金手指：" + json.dumps(bible.get("golden_finger", {}), ensure_ascii=False)[:600] +
        "；主角：陈凡。规划第1-10章，前3章要有强钩子，每章结尾自然引向下一章。"
    )
    bp_path = Path(r"C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2\outputs\novel-pipeline\tools\rewrite_blueprints.json")
    blueprints = None
    if bp_path.exists():
        try:
            blueprints = json.loads(bp_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            blueprints = None
    if blueprints is None:
        blueprints = extract_json(llm([
            {"role": "system", "content": bp_system},
            {"role": "user", "content": bp_user},
        ]))["chapters"]
    Path(r"C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2\outputs\novel-pipeline\tools\rewrite_blueprints.json").write_text(
        json.dumps(blueprints, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("blueprints ok:", len(blueprints))

    # 5. persist bible + blueprints
    payload_base = {
        "book_id": BOOK_ID,
        "book_name": "捡到破碗后我修仙无敌了",
        "genre": "凡人修仙/苟道流",
        "premise": "凡人修仙：捡到一只会提纯灵物的破碗，从杂灵根苟到无敌",
        "selling_point": bible.get("main_plot", "")[:200],
        "tags": ["修仙", "凡人流", "苟", "提纯", "杂灵根"],
        "abstract": "凡人陈凡机缘巧合捡到一只能提纯灵物的破碗，从此凭借杂灵根苟于修仙界底层，默默提纯灵物、修炼成长，最终从人人轻视的杂灵根修士一步步证道无敌。",
        "protagonists": [
            {"name": "陈凡", "role": "主角", "traits": "谨慎低调，善于隐忍，心思细腻", "goals": "靠破碗提纯灵物默默提升修为，摆脱杂灵根桎梏，长生不死"},
        ],
        "volume_goal": volume_goal,
        "outline": {
            "bible": bible,
            "blueprints": blueprints,
        },
        "chapters": [],
    }
    nid = upsert_novel(conn, payload_base)
    bible_chars = []
    for c in bible.get("characters") or []:
        bible_chars.append(
            {
                "name": c.get("name", ""),
                "role": c.get("role", "supporting"),
                "traits": (c.get("personality", "") + "；说话习惯：" + c.get("speech_style", "")).strip("；"),
                "goals": c.get("growth_arc", ""),
            }
        )
    upsert_characters(conn, nid, bible_chars or payload_base["protagonists"])
    upsert_volume(conn, nid, payload_base)
    conn.close()
    print("persisted bible, novel_id=", nid)

    # 6-7. write + review + save drafts
    chapters = []
    for i in range(1, 3):
        bp = blueprints[i - 1]
        prev_ending = chapters[-1].get("ending_excerpt", "") if chapters else ""
        recent_txt = ""
        if chapters:
            recent_txt = "上一章：" + chapters[-1]["title"] + "，" + chapters[-1].get("content", "")[:300]
        char_states = json.dumps({}, ensure_ascii=False)
        threads = "[]"
        existing = "、".join(c["title"] for c in chapters)
        style = json.dumps(bible.get("style_guide", ""), ensure_ascii=False)

        writer_system = (
            "你是在番茄小说连载多年的网文作者。写作要求：长短句混用；对话带动作神态；"
            "心理描写为核心；环境描写克制；全角标点，对话用中文双引号，省略号用……，破折号用——；"
            "禁止'突然'超过1次，禁止'此刻''就在这时'开头，禁止'不由自主''情不自禁'；"
            "正文必须分段：每个自然段用空行（换行符）分隔，每段60-150字；"
            "单章2000-2200个中文字符。只输出JSON：{title(2-20字，不含第X章，全书唯一),content}"
        )
        writer_user = (
            "风格指南：" + style +
            "；前情提要：" + (recent_txt or "本书第一章，无需承接前文") +
            ("；上一章结尾原文：" + prev_ending[-800:] if prev_ending else "") +
            "；本章大纲：" + json.dumps(bp, ensure_ascii=False) +
            "；角色当前状态：" + char_states +
            "；活跃伏笔：" + threads +
            "；已有章节标题（不能重复）：" + (existing or "无")
        )
        reviewer_system = (
            "你是严格的网文质检专家。只输出JSON：{score(0-10),passed(bool),"
            "coherence_ok(bool),issues([{severity,description}])}。"
            "重点：将上一章结尾与本章开头3段逐句对比检查连贯性；角色是否OOC；"
            "设定是否吃书；标题是否与已有标题重复；是否有AI痕迹。"
        )
        title = ""
        content = ""
        review = {}
        for attempt in range(3):
            out = extract_json(llm([
                {"role": "system", "content": writer_system},
                {"role": "user", "content": writer_user},
            ], temperature=0.85, model=WRITER_MODEL))
            title = str(out.get("title") or bp.get("title") or title)
            content = str(out.get("content") or content)
            chars = chinese_chars(content)
            if chars < 1500:
                content = str(
                    extract_json(llm([
                        {"role": "system", "content": writer_system + "上一版太短，请扩充到2000字以上。"},
                        {"role": "user", "content": writer_user + "；上一版正文：" + content[:1500]},
                    ], temperature=0.85, model=WRITER_MODEL)).get("content") or content
                )
                title = str(out.get("title") or title)
                chars = chinese_chars(content)
            reviewer_user = (
                "本章标题：" + title +
                ("；上一章结尾：" + prev_ending[-800:] if prev_ending else "；本书第一章，无上一章") +
                "；本章大纲：" + json.dumps(bp, ensure_ascii=False) +
                "；已有标题：" + (existing or "无") +
                "；正文：" + content[:4000]
            )
            review = extract_json(llm([
                {"role": "system", "content": reviewer_system},
                {"role": "user", "content": reviewer_user},
            ], temperature=0.2))
            print("chapter", i, "attempt", attempt + 1, "written:", title, chars, "chars",
                  "review", review.get("score"), review.get("passed"))
            if review.get("passed") and float(review.get("score") or 0) >= 7:
                break
            issues = json.dumps(review.get("issues", []), ensure_ascii=False)
            writer_user = writer_user + "；上一版被审稿打回：" + issues[:1200] + "，请针对性修改，保持剧情连贯。"
        print("review", i, "score", review.get("score"), "passed", review.get("passed"), "coherence", review.get("coherence_ok"))

        item_id = new_draft()
        cover_draft(item_id, f"第 {i} 章 {title}", to_html(content))
        paras = [p.strip() for p in content.splitlines() if p.strip()]
        ending_excerpt = "\n".join(paras[-3:])[-600:]
        chapters.append({
            "seq": i,
            "title": f"第 {i} 章 {title}",
            "outline": bp.get("outline", ""),
            "status": "draft",
            "words": chars,
            "fanqie_item_id": item_id,
            "published_at": "",
            "ending_excerpt": ending_excerpt,
            "content": content,
            "review": review,
        })

    # 8. memory extraction (one call)
    mem_system = (
        "你是小说内容分析专家。只输出JSON：{chapters:[{seq,summary(200-300字),"
        "character_updates({角色名:{changes,new_info}}),plot_events([{event_type,description,importance,resolved}]),"
        "new_characters([{name,role,description}]),world_updates([{category,name,description}])}]}"
    )
    mem_user = "\n\n".join(
        f"第{c['seq']}章 {c['title']}\n{c['content']}" for c in chapters
    )
    memory = extract_json(llm([
        {"role": "system", "content": mem_system},
        {"role": "user", "content": mem_user},
    ], temperature=0.2))
    mem_by_seq = {m["seq"]: m for m in memory.get("chapters", [])}
    for c in chapters:
        c["summary"] = mem_by_seq.get(c["seq"], {})

    # 9. publish (retry after midnight on daily cap)
    for c in chapters:
        d = publish_chapter(c["fanqie_item_id"], c["title"], c["content"])
        if d.get("code") == -1019:
            wait_until_midnight()
            d = publish_chapter(c["fanqie_item_id"], c["title"], c["content"])
        if d.get("code") == 0:
            c["status"] = "published"
            c["published_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print("published", c["seq"], c["fanqie_item_id"])
        else:
            c["error"] = json.dumps(d, ensure_ascii=False)
            print("publish FAILED", c["seq"], d)

    # 10. record
    payload = {**payload_base, "chapters": chapters}
    conn = db.connect(ROOT / "demo.db")
    upsert_novel(conn, payload)
    upsert_characters(conn, nid, bible_chars or payload_base["protagonists"])
    upsert_volume(conn, nid, payload)
    upsert_chapters(conn, nid, chapters)
    conn.close()
    print("DONE. chapters:", [(c["seq"], c["status"]) for c in chapters])


if __name__ == "__main__":
    main()
