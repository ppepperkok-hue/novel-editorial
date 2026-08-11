"""合规门：平台规则清单 + 敏感词扫描 + AI 声明状态。

词库来源（合并去重）：
1. `compliance_words.txt`（仓库根，每行一词，# 开头为注释）——正式启用前按
   目标平台规则补充/裁剪；
2. 内置 `DEFAULT_SENSITIVE_KEYWORDS`：通用明显违规词，覆盖常见平台红线
   （违禁品/赌博/诈骗/暴恐/色情露骨/代充广告引流）。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORDS_FILE = ROOT / "compliance_words.txt"

DEFAULT_SENSITIVE_KEYWORDS = [
    # 违禁品 / 涉毒
    "冰毒",
    "海洛因",
    "摇头丸",
    "制毒",
    "贩毒",
    # 赌博 / 博彩
    "赌博网站",
    "博彩平台",
    "网络赌场",
    "赌博攻略",
    # 诈骗 / 传销
    "电信诈骗",
    "诈骗教程",
    "传销组织",
    "裸贷",
    # 暴恐 / 危险品
    "自制炸药",
    "恐怖袭击策划",
    "枪支交易",
    # 色情露骨
    "色情直播",
    "裸聊",
    "约炮",
    "卖淫",
    # 代充 / 广告引流
    "代充值",
    "刷单兼职",
    "日结兼职",
    "加微信领福利",
    "私聊发资源",
]

# Backwards-compatible alias for any existing reference.
SENSITIVE_KEYWORDS = DEFAULT_SENSITIVE_KEYWORDS


def _load_words():
    words = list(DEFAULT_SENSITIVE_KEYWORDS)
    if WORDS_FILE.exists():
        for line in WORDS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                words.append(line)
    seen = set()
    out = []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def check(text, platform="fanqie", ai_declared=True):
    words = _load_words()
    found = [k for k in words if k in text]
    return {
        "passed": not found,
        "sensitive_hits": found,
        "ai_declared": ai_declared,
        "platform": platform,
        "note": "词库 = 内置通用违规词 + compliance_words.txt 自定义项，按平台规则持续补充",
    }
