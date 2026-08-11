"""合规门：平台规则清单 + 敏感词扫描 + AI 声明状态。

词库来源（合并去重）：
1. `compliance_words.txt`（仓库根，每行一词，# 开头为注释）——正式启用前按
   目标平台规则补充/裁剪；
2. 内置 `DEFAULT_SENSITIVE_KEYWORDS`：通用明显违规词，覆盖常见平台红线
   （违禁品/赌博/诈骗/暴恐/色情露骨/代充广告引流）。
"""

import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORDS_FILE = ROOT / "compliance_words.txt"

EMPTY_WORDS_WARNING = (
    "compliance_words.txt 为空或全为注释，未加载任何自定义词；"
    "仅使用内置 DEFAULT_SENSITIVE_KEYWORDS"
)
MISSING_WORDS_WARNING = (
    "compliance_words.txt 不存在，仅使用内置 DEFAULT_SENSITIVE_KEYWORDS"
)
READ_WORDS_WARNING = (
    "compliance_words.txt 读取或解码失败，仅使用内置 DEFAULT_SENSITIVE_KEYWORDS"
)

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


def _read_custom_words():
    """Return custom words from compliance_words.txt (comments skipped).

    Returns None when the file exists but cannot be read/decoded
    (a RuntimeWarning is emitted and only built-in words are used).
    """
    if not WORDS_FILE.exists():
        return []
    try:
        content = WORDS_FILE.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        warnings.warn(READ_WORDS_WARNING, RuntimeWarning, stacklevel=2)
        return None
    words = []
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.append(line)
    return words


_UNREAD = object()


def _load_words(custom_words=_UNREAD):
    words = list(DEFAULT_SENSITIVE_KEYWORDS)
    if custom_words is _UNREAD:
        custom_words = _read_custom_words()
    if custom_words:
        words.extend(custom_words)
    seen = set()
    out = []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def check(text, platform="fanqie", ai_declared=True):
    custom_words = _read_custom_words()
    words = _load_words(custom_words)
    warnings_list = []
    if not WORDS_FILE.exists():
        warnings_list.append(MISSING_WORDS_WARNING)
        warnings.warn(MISSING_WORDS_WARNING, RuntimeWarning, stacklevel=2)
    elif custom_words is None:
        warnings_list.append(READ_WORDS_WARNING)
    elif not custom_words:
        warnings_list.append(EMPTY_WORDS_WARNING)
        warnings.warn(EMPTY_WORDS_WARNING, RuntimeWarning, stacklevel=2)
    found = [k for k in words if k in text]
    return {
        "passed": not found,
        "sensitive_hits": found,
        "ai_declared": ai_declared,
        "platform": platform,
        "warnings": warnings_list,
        "note": "词库 = 内置通用违规词 + compliance_words.txt 自定义项，按平台规则持续补充",
    }
