"""DEPRECATED 流水线编排（n8n 时代路径，当前无调用方）。

现役链路请使用 `tools/editorial_daily.py` 与 `tools/editorial_steps.py`；
本模块保留为回退后备。
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import compliance, db, quality_gate
from novel_editorial.llm_client import LLMClient, MockLLMClient
from novel_editorial.publisher import FanqieHttpAdapter, ManualAdapter

PROMPTS_DIR = ROOT / "prompts" / "agents"


def load_prompt(name):
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def fill(template, **kwargs):
    """把模板里的 {占位符} 替换成实参；不做 str.format，避免被 JSON 花括号误伤。"""
    out = template
    for key, value in kwargs.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def parse_review(text):
    """从 LLM 输出里提取 JSON 对象（允许带 ```json 围栏）。"""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("LLM 输出不是合法 JSON 对象")
    return json.loads(text[start:end + 1])


def generate_chapter(client, chapter_outline, prev_summary="", character_states="{}",
                     plot_threads="[]", min_chars=800, max_chars=1300,
                     max_revisions=3):
    """写稿 → 润色 → 审稿（不过则重写，最多 max_revisions 轮）→ 记忆。"""
    writer_prompt = fill(
        load_prompt("writer"),
        chapter_outline=chapter_outline,
        prev_summary=prev_summary,
        character_states=character_states,
        plot_threads=plot_threads,
        min_chars=min_chars,
        max_chars=max_chars,
    )
    draft = client.chat(
        writer_prompt, "请开始写作。", tier="writing", max_tokens=max_chars * 2 + 800
    )

    editor_prompt = fill(
        load_prompt("editor"),
        min_chars=min_chars,
        max_chars=max_chars,
    )
    edited = client.chat(
        editor_prompt, f"初稿：\n{draft}", tier="editing", max_tokens=max_chars * 2 + 800
    )

    review_raw = client.chat(
        load_prompt("reviewer"),
        f"章纲：{chapter_outline}\n正文：\n{edited}",
        tier="reviewing",
        max_tokens=2000,
    )
    review = parse_review(review_raw)

    revisions = 0
    while not review.get("passed") and revisions < max_revisions:
        revisions += 1
        revision_prompt = (
            f"上一版正文：\n{edited}\n"
            f"审稿意见：\n{json.dumps(review.get('suggestions', []), ensure_ascii=False)}"
        )
        edited = client.chat(editor_prompt, revision_prompt, tier="editing")
        review_raw = client.chat(
            load_prompt("reviewer"),
            f"章纲：{chapter_outline}\n正文：\n{edited}",
            tier="reviewing",
            max_tokens=2000,
        )
        review = parse_review(review_raw)

    memory_raw = client.chat(
        load_prompt("memory"),
        f"正文：\n{edited}",
        tier="memory",
        max_tokens=2400,
    )
    memory = parse_review(memory_raw)

    return {"draft": draft, "edited": edited, "review": review,
            "memory": memory, "revisions": revisions}


def generate_one_chapter(conn, client, novel_id, volume_id, chapter_seq,
                         chapter_outline, outline_keywords, prev_summary="",
                         character_states="{}", plot_threads="[]",
                         min_chars=800, max_chars=1300, platform="fanqie"):
    """单章完整流程：建章 → 四步生成 → 质量门 + LLM 审稿 + 合规门 → 持久化。"""
    chapter_id = db.add_chapter(conn, novel_id, volume_id, chapter_seq, chapter_outline)
    result = generate_chapter(
        client, chapter_outline,
        prev_summary=prev_summary,
        character_states=character_states,
        plot_threads=plot_threads,
        min_chars=min_chars, max_chars=max_chars,
    )
    report = quality_gate.score_chapter(
        result["edited"],
        outline_keywords=outline_keywords,
        min_chars=min_chars,
        max_chars=max_chars,
    )
    llm_review = result["review"]
    comp = compliance.check(result["edited"], platform=platform)
    passed = bool(llm_review.get("passed", False)) and report["passed"] and comp["passed"]
    status = "reviewed" if passed else "draft"
    conn.execute(
        "UPDATE chapters SET words=?, score=?, status=? WHERE id=?",
        (report["char_count"], report["scores"]["words"], status, chapter_id),
    )
    conn.commit()
    db.add_quality_report(
        conn,
        chapter_id,
        {**report["scores"], "llm_review": llm_review.get("scores", {})},
        passed,
        revision_count=result["revisions"],
    )
    memory = result["memory"]
    db.add_chapter_summary(
        conn,
        chapter_id,
        memory.get("summary", ""),
        json.dumps(memory.get("character_states", {}), ensure_ascii=False),
        json.dumps(memory.get("world_events", []), ensure_ascii=False),
    )
    conn.execute(
        "INSERT INTO chapter_content(chapter_id,content,updated_at) "
        "VALUES(?,?,datetime('now','localtime')) "
        "ON CONFLICT(chapter_id) DO UPDATE SET content=excluded.content, "
        "updated_at=excluded.updated_at",
        (chapter_id, result["edited"]),
    )
    conn.commit()
    return {"chapter_id": chapter_id, "seq": chapter_seq, "passed": passed,
            "quality": report, "review": llm_review, "memory": memory,
            "compliance": comp, "revisions": result["revisions"]}


def run_generation(conn, client, outline, min_chars=800, max_chars=1300):
    """完整生成一轮：建书建章 → 四步生成 → 质量门 + LLM 审稿 → 持久化。"""
    novel_id = db.add_novel(
        conn, outline["title"], outline["genre"], outline["premise"],
        platform=outline.get("platform", "fanqie"),
    )
    vol_id = db.add_volume(conn, novel_id, 1, outline["volume_goal"])
    return generate_one_chapter(
        conn, client, novel_id, vol_id, 1,
        outline["chapter_outline"], outline["keywords"],
        platform=outline.get("platform", "fanqie"),
        min_chars=min_chars, max_chars=max_chars,
    )


def run_demo(db_path=None):
    if db_path is None:
        fd, db_path = tempfile.mkstemp(suffix=".db", prefix="novel_demo_")
        os.close(fd)

    demo_dir = ROOT / "demo_data"
    outline = json.loads((demo_dir / "sample_outline.json").read_text(encoding="utf-8"))
    text = (demo_dir / "sample_chapter.md").read_text(encoding="utf-8")

    conn = db.connect(db_path)
    novel_id = db.add_novel(conn, outline["title"], outline["genre"], outline["premise"],
                            platform=outline.get("platform", "fanqie"))
    vol_id = db.add_volume(conn, novel_id, 1, outline["volume_goal"])
    chapter_id = db.add_chapter(conn, novel_id, vol_id, 1, outline["chapter_outline"])

    report = quality_gate.score_chapter(
        text,
        outline_keywords=outline["keywords"],
        min_chars=800,
        max_chars=1300,
    )
    comp = compliance.check(text, platform=outline.get("platform", "fanqie"))
    passed_all = report["passed"] and comp["passed"]

    status = "reviewed" if passed_all else "draft"
    conn.execute("UPDATE chapters SET words=?, score=?, status=? WHERE id=?",
                 (report["char_count"], report["scores"]["words"], status, chapter_id))
    conn.commit()
    db.add_quality_report(conn, chapter_id, report["scores"], report["passed"])
    db.add_publish_log(
        conn,
        chapter_id,
        outline.get("platform", "fanqie"),
        "dry_run",
        "passed" if passed_all else "blocked",
        error=None if passed_all else "质量门或合规门未通过",
        ai_declared=1,
    )

    publish_result = None
    if passed_all:
        adapter = ManualAdapter()
        publish_result = adapter.publish(chapter_id, text)

    print(json.dumps({
        "chapter_id": chapter_id,
        "title": outline["title"],
        "quality": report,
        "compliance": comp,
        "publish": publish_result,
        "final_status": "PUBLISH_QUEUED" if passed_all else "BLOCKED",
    }, ensure_ascii=False, indent=2))
    return 0 if passed_all else 1


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="novel-editorial MVP 脚手架")
    ap.add_argument("--demo", action="store_true", help="无 API 依赖的端到端演示")
    ap.add_argument("--generate", action="store_true", help="走真实 LLM 生成链路（需配置密钥）")
    ap.add_argument("--db", default=None, help="演示数据库路径（默认临时文件）")
    args = ap.parse_args()
    if args.demo:
        return run_demo(args.db)
    if args.generate:
        client = LLMClient()
        if not client.configured:
            print("未配置 LLM_API_KEY / LLM_BASE_URL，无法生成；请参考 .env.example 配置。")
            return 2
        outline = json.loads(
            (ROOT / "demo_data" / "sample_outline.json").read_text(encoding="utf-8")
        )
        conn = db.connect(args.db or "demo.db")
        result = run_generation(conn, client, outline)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 1
    raise SystemExit("请先指定 --demo（骨架阶段），或接入 LLMClient 后运行真实流水线。")


if __name__ == "__main__":
    sys.exit(main())
