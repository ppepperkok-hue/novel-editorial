"""质量门（确定性部分）。

五维评分：字数 / 情节 / 文笔 / 规范 / 衔接。
情节、文笔、衔接的严格评估需要 LLM ReviewerAgent 完成，此处先提供
可测试的确定性代理值，保证骨架能端到端运行；正式版接入 LLM 后替换。
"""

import re
import json
from pathlib import Path

CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# 常见 AI 味模板词（去 AI 味专项治理用；与 ai_words.json、tools/editorial_steps.py 同源）
AI_FLAVOR_WORDS = [
    "突然", "顿时", "仿佛", "缓缓", "不由得", "微微一", "嘴角", "眼神一凝", "低沉",
    "冷哼一声", "心中一动", "不禁", "瞬间", "面无表情", "淡淡", "不由自主", "情不自禁",
    "微微一愣", "缓缓说道", "与此同时", "一股强大的气息",
]
_WORDS_FILE = Path(__file__).resolve().parent.parent / "ai_words.json"
try:
    _AI_DATA = json.loads(_WORDS_FILE.read_text(encoding="utf-8"))
    AI_FLAVOR_WORDS = _AI_DATA.get("ai_flavor", AI_FLAVOR_WORDS)
except (OSError, ValueError):
    pass


def count_chinese_chars(text):
    """统计中文字符数（平台计字通常以此为准）。"""
    return len(CJK_RE.findall(text))


def check_punctuation(text):
    """中文语境里的标点规范问题清单。"""
    issues = []
    if re.search(r"[\u4e00-\u9fff][,.;:!?]", text):
        issues.append("中文后紧跟半角标点")
    if re.search(r"[\u4e00-\u9fff]\s*[\"']", text):
        issues.append("中文明文使用英文引号")
    if "...." in text or "。。。" in text:
        issues.append("省略号写法不规范")
    return issues


def ai_flavor_density(text):
    """每千字中 AI 味模板词出现次数，越高越可疑；重叠词按位置只计一次。"""
    total = count_chinese_chars(text)
    if total == 0:
        return 0.0
    if not AI_FLAVOR_WORDS:
        return 0.0
    pattern = re.compile("|".join(re.escape(w) for w in AI_FLAVOR_WORDS))
    hits = len(pattern.findall(text))
    return hits / total * 1000


def keyword_coverage(text, keywords):
    """章纲关键词在正文中的覆盖率，作为「情节紧扣章纲」的代理指标。"""
    if not keywords:
        return 1.0
    found = sum(1 for k in keywords if k and k in text)
    return found / len(keywords)


def _clamp_score(value):
    return max(0.0, min(10.0, round(value, 1)))


def _banded_word_score(words, min_chars, max_chars):
    if min_chars <= words <= max_chars:
        return 10.0
    if min_chars * 0.8 <= words <= max_chars * 1.2:
        return 7.0
    if min_chars * 0.6 <= words <= max_chars * 1.5:
        return 4.0
    return 1.0


def score_chapter(text, outline_keywords=None, min_chars=2000, max_chars=2300,
                  ai_flavor_limit=6.0, prev_tail=None):
    words = count_chinese_chars(text)
    word_score = _banded_word_score(words, min_chars, max_chars)

    coverage = keyword_coverage(text, outline_keywords or [])
    plot_score = 3.0 + 7.0 * coverage

    density = ai_flavor_density(text)
    if density <= 2.0:
        style_score = 10.0
    elif density <= ai_flavor_limit:
        style_score = 8.0
    else:
        style_score = max(0.0, 10.0 - (density - ai_flavor_limit) * 2.0)

    issues = check_punctuation(text)
    punct_score = 10.0 if not issues else max(0.0, 10.0 - 2.0 * len(issues))

    if prev_tail is None:
        coher_score = 10.0
    else:
        tail = (prev_tail or "")[-40:]
        # A missing tail match is a real coherence failure, not a mild ding:
        # 4.0 sits below the per-dimension pass bar (5.0).
        coher_score = 10.0 if (tail and tail in text) else 4.0

    scores = {
        "words": _clamp_score(word_score),
        "plot": _clamp_score(plot_score),
        "style": _clamp_score(style_score),
        "punctuation": _clamp_score(punct_score),
        "coherence": _clamp_score(coher_score),
        "ai_flavor_density": round(density, 2),
    }
    dims = ("words", "plot", "style", "punctuation", "coherence")
    avg = sum(scores[d] for d in dims) / len(dims)
    passed = avg >= 7.0 and all(scores[d] >= 5.0 for d in dims)
    return {
        "scores": scores,
        "passed": passed,
        "issues": issues,
        "char_count": words,
    }
