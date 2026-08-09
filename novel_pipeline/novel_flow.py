"""端到端自动连载：大纲 → 逐章生成（带前文记忆）→ 质量门 → 返回发布队列。"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import db, pipeline, planner
from novel_pipeline.llm_client import LLMClient


def run_novel(conn, client, premise, chapters=3, platform="fanqie",
              min_chars=800, max_chars=1300):
    outline = planner.build_outline(client, premise, chapters=chapters, platform=platform)
    novel_id = db.add_novel(
        conn, outline["title"], outline["genre"], outline["premise"],
        selling_point=outline.get("selling_point", ""),
        platform=platform,
    )
    vol_id = db.add_volume(conn, novel_id, 1, outline["volume_goal"])

    prev_summary = ""
    character_states = "{}"
    plot_threads = "[]"
    chapter_results = []
    for seq, chapter_outline in enumerate(outline["chapter_outlines"], start=1):
        res = pipeline.generate_one_chapter(
            conn, client, novel_id, vol_id, seq, chapter_outline,
            outline["keywords"],
            prev_summary=prev_summary,
            character_states=character_states,
            plot_threads=plot_threads,
            min_chars=min_chars,
            max_chars=max_chars,
            platform=platform,
        )
        memory = res["memory"]
        prev_summary = memory.get("summary", "")
        character_states = json.dumps(memory.get("character_states", {}), ensure_ascii=False)
        chapter_results.append(res)

    return {
        "novel_id": novel_id,
        "outline": outline,
        "chapters": chapter_results,
        "all_passed": all(c["passed"] for c in chapter_results),
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="端到端自动连载")
    ap.add_argument("--premise", required=True, help="一句话核心设定")
    ap.add_argument("--chapters", type=int, default=3)
    ap.add_argument("--platform", default="fanqie")
    ap.add_argument("--db", default="demo.db")
    args = ap.parse_args()
    client = LLMClient()
    if not client.configured:
        print("未配置 LLM_API_KEY / LLM_BASE_URL，无法运行自动连载。")
        return 2
    conn = db.connect(args.db)
    result = run_novel(conn, client, args.premise, chapters=args.chapters,
                       platform=args.platform)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
