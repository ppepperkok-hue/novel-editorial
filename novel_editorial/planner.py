"""立项与大纲：从一句话 premise 生成结构化大纲（JSON 输出 + 字段校验）。"""

import json
import sys

PLANNER_PROMPT = """你是网络小说策划编辑。根据用户给出的 premise 与章节数，产出一本书的立项大纲，严格按下面的 JSON 结构输出，不要输出其他内容：

{
  "title": "书名",
  "genre": "题材，如 都市重生",
  "premise": "一句话核心设定（沿用用户 premise，可微调措辞）",
  "selling_point": "核心卖点，一句话",
  "volume_goal": "第一卷目标，一句话",
  "chapter_outlines": ["第1章 标题与要点", "第2章 标题与要点"],
  "keywords": ["贯穿全书的关键词，5-8 个"]
}

要求：chapter_outlines 数量必须与章节数一致；每章要点包含钩子或爽点；keywords 用于后续质量门的情节校验。"""


def build_outline(client, premise, chapters=3, platform="fanqie"):
    user = json.dumps(
        {"premise": premise, "chapters": chapters, "platform": platform},
        ensure_ascii=False,
    )
    raw = client.chat(PLANNER_PROMPT, user, tier="planning", max_tokens=3000)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("Planner 输出不是合法 JSON 对象")
    data = json.loads(raw[start:end + 1])

    required = {"title", "genre", "premise", "volume_goal", "chapter_outlines", "keywords"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"大纲缺少字段：{sorted(missing)}")
    if not isinstance(data["chapter_outlines"], list) or len(data["chapter_outlines"]) != chapters:
        raise ValueError("chapter_outlines 数量与章节数不一致")
    if not isinstance(data["keywords"], list) or not data["keywords"]:
        raise ValueError("keywords 必须为非空列表")
    data.setdefault("platform", platform)
    return data


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    import argparse

    from novel_editorial.llm_client import LLMClient

    ap = argparse.ArgumentParser(description="立项与大纲")
    ap.add_argument("--premise", required=True, help="一句话核心设定")
    ap.add_argument("--chapters", type=int, default=3)
    ap.add_argument("--platform", default="fanqie")
    args = ap.parse_args()
    client = LLMClient()
    if not client.configured:
        print("未配置 LLM_API_KEY / LLM_BASE_URL，无法生成大纲。")
        return 2
    print(json.dumps(build_outline(client, args.premise, args.chapters, args.platform),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
