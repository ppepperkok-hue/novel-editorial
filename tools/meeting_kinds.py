"""R4-2: meeting kind registry.

Each kind defines its label, the material blocks it needs, the speech agenda
label, post-meeting actions and default attendees. The engine stays generic;
only these declarations change per kind.
"""

MEETING_KINDS = {
    "weekly": {
        "label": "编辑部例会",
        "materials_keys": ["weekly"],
        "agenda_label": "本周小结",
        "post_actions": ["apply", "actions"],
        "default_attendees": ["planner", "guard", "writer", "reader", "memory", "eic"],
    },
    "topic": {
        "label": "剧情碰头会",
        "materials_keys": ["book"],
        "agenda_label": "主题观察",
        "post_actions": ["apply", "actions"],
        "default_attendees": ["planner", "guard", "writer", "reviewer", "reader", "eic"],
    },
    "planning": {
        "label": "选题会",
        "materials_keys": ["planning"],
        "agenda_label": "市场观察",
        "post_actions": ["next_book", "actions"],
        "default_attendees": ["planner", "reader", "memory", "guard", "writer", "eic"],
    },
    "critique": {
        "label": "单章会诊",
        "materials_keys": ["book", "chapter", "quality"],
        "agenda_label": "这章好在哪",
        "post_actions": ["critique", "actions"],
        "default_attendees": ["writer", "editor", "reviewer", "reader", "eic"],
    },
    "retro": {
        "label": "数据复盘会",
        "materials_keys": ["book", "reader_stats", "quality"],
        "agenda_label": "数据告诉我什么",
        "post_actions": ["retro", "actions"],
        "default_attendees": ["reader", "writer", "reviewer", "memory", "eic"],
    },
    "review": {
        "label": "收尾会",
        "materials_keys": ["book", "finish", "quality"],
        "agenda_label": "完成度评估",
        "post_actions": ["review", "actions"],
        "default_attendees": ["ending_judge", "planner", "guard", "memory", "eic"],
    },
    "incident": {
        "label": "危机处理会",
        "materials_keys": ["book", "failures", "quality"],
        "agenda_label": "发生了什么",
        "post_actions": ["incident", "actions"],
        "default_attendees": ["eic", "guard", "reviewer", "memory", "writer"],
    },
    "learning": {
        "label": "知识分享会",
        "materials_keys": ["knowledge", "drafts", "hot_topics"],
        "agenda_label": "我学到了什么",
        "post_actions": ["learning", "actions"],
        "default_attendees": ["knowledge_keeper", "writer", "reviewer", "memory", "eic"],
    },
    "free": {
        "label": "茶水间闲聊",
        "materials_keys": ["topic_pool"],
        "agenda_label": "自然发言",
        "post_actions": ["actions"],
        "default_attendees": ["eic"],
    },
}

MEETING_KIND_NAMES = tuple(MEETING_KINDS.keys())
