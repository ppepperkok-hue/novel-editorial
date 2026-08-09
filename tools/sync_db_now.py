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
        "book_name": "捡到破碗后我修仙无敌了",
        "genre": "凡人修仙/苟道流",
        "premise": "凡人修仙：捡到一只会提纯灵物的破碗，从杂灵根苟到无敌；主角：陈凡；日更两章，章纲要有钩子",
        "selling_point": "",
        "tags": ["修仙", "凡人流", "苟", "提纯", "杂灵根"],
        "abstract": "凡人陈凡机缘巧合捡到一只能提纯灵物的破碗，从此凭借杂灵根苟于修仙界底层，默默提纯灵物、修炼成长，最终从人人轻视的杂灵根修士一步步证道无敌。",
        "protagonists": [
            {"name": "陈凡", "role": "主角", "traits": "谨慎低调，善于隐忍，心思细腻，知恩图报", "goals": "靠破碗提纯灵物默默提升修为，摆脱杂灵根桎梏，长生不死"},
            {"name": "老乞丐", "role": "配角", "traits": "", "goals": ""},
        ],
        "volume_goal": "陈凡以黑市为掩护，利用破碗提纯灵物稳定赚取灵石，将修为从练气一层逐步提升至练气七层，同时谨慎结交黑市耳目，巧设布局反制宗门执事弟子的追查，彻底隐藏破碗的秘密，为下一步筑基打下根基。",
        "outline": {
            "premise": "凡人修仙：捡到一只会提纯灵物的破碗，从杂灵根苟到无敌；主角：陈凡；日更两章，章纲要有钩子",
            "genre": "凡人修仙/苟道流",
            "title": "破碗成仙：从杂灵根苟到无敌",
            "keywords": "破碗,提纯灵物,杂灵根,苟道,凡人修仙",
            "chapter1": {"title": "破碗初鸣", "outline": "陈凡在垃圾堆捡到一只缺了口的破碗，当晚梦中见碗底浮现金色符文，醒来发现碗中残留的米汤竟蕴含灵气。他用破碗盛装低阶灵草，灵草杂质被自动剔除，药效提升三倍。从此，陈凡开始偷偷用破碗提纯日常搜集的廉价灵物，默默强化自身，同时伪装成最普通的杂灵根弟子，在宗门边缘苟活。", "hook": "正当他以为无人知晓时，掌门的传讯玉简突然飞来：'陈凡，你碗里的东西，拿来本座观观。'"},
            "chapter2": {"title": "一鸣惊人", "outline": "陈凡被掌门召见，却发现是误会——掌门只是看中他捡到的一株残药。他趁机将提纯后的灵草献上，声称是家传秘法。掌门检验后惊为天人，当场赐他内门弟子资格。陈凡心中惧怕暴露破碗，佯装贪慕虚名，实则继续低调修行。当夜，他偷偷用量变提纯的灵石布下聚灵阵，修为连破三层。", "hook": "阵成之时，窗外突然响起一声冷笑：'师弟，你可知道，掌门最恨有人在眼皮底下耍花样？'"},
        },
        "chapters": [
            {"seq": 1, "title": "第 1 章 破碗认主", "outline": "杂灵根外门弟子林凡被同门欺压，被派去后山挖灵药，意外挖出一只缺口破碗。破碗散发微光，将他刚采到的一株下品灵草提纯成上品灵药，同时脑海浮现《提纯诀》。林凡意识到逆天机缘，但立刻压下激动，决定不声张，先苟住。", "status": "published", "words": 1762, "fanqie_item_id": "7672041382386598462", "published_at": now},
            {"seq": 2, "title": "第 2 章 第一桶灵石", "outline": "林凡利用破碗提纯低阶灵草，悄悄在黑市售卖，赚取第一桶灵石。为防暴露，他换装易容，还用提纯废液布下陷阱，坑害了一名跟踪他的执事弟子。他意识到修仙界人心险恶，决定继续隐藏实力，只能在无人处默默修炼。", "status": "published", "words": 2234, "fanqie_item_id": "7672041753276318270", "published_at": now},
            {"seq": 3, "title": "第 3 章 破碗与杂灵根", "outline": "陈凡测灵被定为杂灵根，分到药园做杂役，暴雨夜在沟里捡到破碗，发现碗水能让枯草返青、下品灵石变中品，从此开始偷偷用破碗提纯灵物。", "status": "published", "words": 1901, "fanqie_item_id": "7672049207682794046", "published_at": now},
            {"seq": 4, "title": "第 4 章 破碗初鸣", "outline": "陈凡在垃圾堆捡到破碗，梦中见金色符文，醒来发现碗中米汤蕴含灵气；他用破碗提纯低阶灵草，药效提升三倍，开始伪装成普通杂灵根弟子在宗门边缘苟活。", "status": "published", "words": 2057, "fanqie_item_id": "7672050652293382718", "published_at": now},
        ],
    }
    conn = db.connect(ROOT / "demo.db")
    try:
        novel_id = upsert_novel(conn, payload)
        upsert_characters(conn, novel_id, payload["protagonists"])
        upsert_volume(conn, novel_id, payload)
        upsert_chapters(conn, novel_id, payload["chapters"])
        print("synced novel_id=", novel_id)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
