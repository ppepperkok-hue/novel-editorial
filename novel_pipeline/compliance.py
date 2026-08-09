"""合规门：平台规则清单 + 敏感词扫描 + AI 声明状态。"""

SENSITIVE_KEYWORDS = [
    # 占位样例，正式版按目标平台规则清单加载
    "example_redline",
    "涉政占位词",
    "违规示例词",
]


def check(text, platform="fanqie", ai_declared=True):
    found = [k for k in SENSITIVE_KEYWORDS if k in text]
    return {
        "passed": not found,
        "sensitive_hits": found,
        "ai_declared": ai_declared,
        "platform": platform,
        "note": "正式版从平台规则清单加载敏感词库与 AI 声明要求",
    }
