import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, r"C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2")
ROOT = Path(r"C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2\outputs\novel-pipeline")
sys.path.insert(0, str(ROOT))

from novel_pipeline import db  # noqa: E402
from tools.record_work import upsert_novel, upsert_characters, upsert_volume, upsert_chapters  # noqa: E402


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "book_id": "7672026913946209342",
        "book_name": "破碗提纯：从杂灵根苟到无敌",
        "genre": "凡人修仙 / 苟道流 / 系统流",
        "premise": "凡人修仙：捡到一只会提纯灵物的破碗，从杂灵根苟到无敌",
        "selling_point": "传统凡人流+金手指破碗提纯，无系统无面板，靠苟和积累逆袭，爽点在于化废为宝、步步为营。",
        "tags": ["凡人修仙", "苟道流", "破碗金手指", "稳健流"],
        "abstract": "杂灵根弟子林凡在宗门杂役房捡到一只会提纯灵物的破碗，从此废柴逆袭，一边装傻苟发育，一边用破碗提纯灵石丹药，从最底层一路苟成无敌强者。",
        "protagonists": [
            {
                "name": "林凡",
                "role": "主角",
                "traits": "杂灵根，隐忍谨慎，装傻苟发育",
                "goals": "用破碗提纯灵物，从杂役弟子一路逆袭",
            },
            {
                "name": "周平",
                "role": "执事弟子/对手",
                "traits": "精明多疑，暗中盯梢",
                "goals": "发现主角的秘密",
            },
        ],
        "volume_goal": "第一卷：破碗初现（1-100章），主角靠破碗提纯灵物，在宗门内装傻苟发育，逐步变强。",
        "outline": {
            "premise": "凡人修仙：捡到一只会提纯灵物的破碗，从杂灵根苟到无敌",
            "genre": "凡人修仙 / 苟道流 / 系统流",
            "title": "破碗飞仙",
            "keywords": "凡人修仙,破碗提纯,杂灵根,苟到无敌,稳健流",
            "chapter1": {
                "title": "破碗认主",
                "outline": "杂灵根外门弟子林凡被同门欺压，被派去后山挖灵药，意外挖出一只缺口破碗。破碗散发微光，将他刚采到的一株下品灵草提纯成上品灵药，同时脑海浮现《提纯诀》。林凡意识到逆天机缘，但立刻压下激动，决定不声张，先苟住。",
                "hook": "破碗突然发出嗡鸣，碗口竟映出一张狰狞鬼脸，低声说：“小子，想不想换一副天灵根？”",
            },
            "chapter2": {
                "title": "第一桶灵石",
                "outline": "林凡利用破碗提纯低阶灵草，悄悄在黑市售卖，赚取第一桶灵石。为防暴露，他换装易容，还用提纯废液布下陷阱，坑害了一名跟踪他的执事弟子。他意识到修仙界人心险恶，决定继续隐藏实力，只能在无人处默默修炼。",
                "hook": "正当他数着灵石暗喜时，破碗却忽然破碎重组，碗底显出一行字：“提纯百次，可解锁第二层——丹毒剥离。”而门外传来了急促的敲击声。",
            },
        },
        "chapters": [
            {
                "seq": 1,
                "title": "第 1 章 破碗认主",
                "outline": "杂灵根外门弟子林凡被同门欺压，被派去后山挖灵药，意外挖出一只缺口破碗。破碗散发微光，将他刚采到的一株下品灵草提纯成上品灵药，同时脑海浮现《提纯诀》。林凡意识到逆天机缘，但立刻压下激动，决定不声张，先苟住。",
                "status": "published",
                "words": 1762,
                "fanqie_item_id": "7672041382386598462",
                "published_at": now,
            },
            {
                "seq": 2,
                "title": "第 2 章 第一桶灵石",
                "outline": "林凡利用破碗提纯低阶灵草，悄悄在黑市售卖，赚取第一桶灵石。为防暴露，他换装易容，还用提纯废液布下陷阱，坑害了一名跟踪他的执事弟子。他意识到修仙界人心险恶，决定继续隐藏实力，只能在无人处默默修炼。",
                "status": "published",
                "words": 2234,
                "fanqie_item_id": "7672041753276318270",
                "published_at": now,
            },
        ],
    }
    conn = db.connect(ROOT / "demo.db")
    try:
        novel_id = upsert_novel(conn, payload)
        upsert_characters(conn, novel_id, payload["protagonists"])
        upsert_volume(conn, novel_id, payload)
        upsert_chapters(conn, novel_id, payload["chapters"])
        print("seeded novel_id=", novel_id)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
