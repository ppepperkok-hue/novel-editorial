"""SQLite 数据层：小说 / 分卷 / 章节 / 角色 / 事件 / 伏笔 / 质量报告 / 发布日志。"""

import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS novels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    genre TEXT NOT NULL,
    premise TEXT NOT NULL,
    selling_point TEXT DEFAULT '',
    target_words INTEGER DEFAULT 2200,
    update_schedule TEXT DEFAULT 'daily_2',
    platform TEXT DEFAULT 'fanqie',
    status TEXT DEFAULT 'planning',
    book_id TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    abstract TEXT DEFAULT '',
    protagonists TEXT DEFAULT '[]',
    outline TEXT DEFAULT '{}',
    volume_goal TEXT DEFAULT '',
    updated_at TEXT DEFAULT '',
    target_chapters INTEGER DEFAULT 0,
    finish_remaining INTEGER DEFAULT 0,
    finish_note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS volumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id INTEGER NOT NULL REFERENCES novels(id),
    seq INTEGER NOT NULL,
    goal TEXT NOT NULL,
    outline TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id INTEGER NOT NULL REFERENCES novels(id),
    volume_id INTEGER REFERENCES volumes(id),
    seq INTEGER NOT NULL,
    outline TEXT NOT NULL,
    status TEXT DEFAULT 'draft',
    words INTEGER DEFAULT 0,
    score REAL DEFAULT 0,
    published_at TEXT,
    title TEXT DEFAULT '',
    fanqie_item_id TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id INTEGER NOT NULL REFERENCES novels(id),
    name TEXT NOT NULL,
    role TEXT DEFAULT '',
    traits TEXT DEFAULT '',
    goals TEXT DEFAULT '',
    state TEXT DEFAULT '{}',
    first_seen_chapter INTEGER
);

CREATE TABLE IF NOT EXISTS world_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id INTEGER NOT NULL REFERENCES novels(id),
    chapter_id INTEGER REFERENCES chapters(id),
    event TEXT NOT NULL,
    impact TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS plot_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id INTEGER NOT NULL REFERENCES novels(id),
    planted_chapter INTEGER NOT NULL,
    expected_recover_chapter INTEGER,
    status TEXT DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS quality_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id),
    scores TEXT NOT NULL,
    passed INTEGER NOT NULL,
    revision_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS publish_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id),
    platform TEXT NOT NULL,
    action TEXT NOT NULL,
    result TEXT NOT NULL,
    error TEXT,
    ai_declared INTEGER DEFAULT 1,
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS chapter_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id),
    summary TEXT NOT NULL,
    character_states TEXT DEFAULT '{}',
    world_events TEXT DEFAULT '[]',
    ending_excerpt TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS chapter_content (
    chapter_id INTEGER PRIMARY KEY REFERENCES chapters(id),
    content TEXT NOT NULL,
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cost_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id INTEGER,
    node_name TEXT DEFAULT '',
    model TEXT DEFAULT '',
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    cost REAL DEFAULT 0,
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_diaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    novel_id INTEGER,
    diary_type TEXT NOT NULL DEFAULT 'daily',
    content TEXT NOT NULL,
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agent_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    novel_id INTEGER,
    mood TEXT NOT NULL,
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS weekly_meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    held_at TEXT DEFAULT '',
    novel_id INTEGER,
    attendees TEXT DEFAULT '[]',
    topics TEXT DEFAULT '[]',
    report TEXT NOT NULL,
    status TEXT DEFAULT 'completed'
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT '',
    category TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT DEFAULT '',
    target_id TEXT DEFAULT '',
    detail TEXT DEFAULT '{}',
    source TEXT DEFAULT 'web'
);

CREATE TABLE IF NOT EXISTS character_evolution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id INTEGER NOT NULL,
    chapter_id INTEGER,
    name TEXT NOT NULL,
    snapshot TEXT DEFAULT '{}',
    change_log TEXT DEFAULT '',
    arc TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);
"""


def connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn):
    """Add columns introduced after the first schema version."""
    novel_cols = {r["name"] for r in conn.execute("PRAGMA table_info(novels)")}
    for col, ddl in {
        "book_id": "TEXT DEFAULT ''",
        "tags": "TEXT DEFAULT '[]'",
        "abstract": "TEXT DEFAULT ''",
        "protagonists": "TEXT DEFAULT '[]'",
        "outline": "TEXT DEFAULT '{}'",
        "volume_goal": "TEXT DEFAULT ''",
        "updated_at": "TEXT DEFAULT ''",
    }.items():
        if col not in novel_cols:
            conn.execute(f"ALTER TABLE novels ADD COLUMN {col} {ddl}")
    for col, ddl in {
        "target_chapters": "INTEGER DEFAULT 0",
        "finish_remaining": "INTEGER DEFAULT 0",
        "finish_note": "TEXT DEFAULT ''",
    }.items():
        if col not in novel_cols:
            conn.execute(f"ALTER TABLE novels ADD COLUMN {col} {ddl}")
    chapter_cols = {r["name"] for r in conn.execute("PRAGMA table_info(chapters)")}
    for col, ddl in {
        "title": "TEXT DEFAULT ''",
        "fanqie_item_id": "TEXT DEFAULT ''",
    }.items():
        if col not in chapter_cols:
            conn.execute(f"ALTER TABLE chapters ADD COLUMN {col} {ddl}")
    log_cols = {r["name"] for r in conn.execute("PRAGMA table_info(publish_logs)")}
    if "created_at" not in log_cols:
        conn.execute("ALTER TABLE publish_logs ADD COLUMN created_at TEXT DEFAULT ''")
    summary_cols = {r["name"] for r in conn.execute("PRAGMA table_info(chapter_summaries)")}
    if "ending_excerpt" not in summary_cols:
        conn.execute("ALTER TABLE chapter_summaries ADD COLUMN ending_excerpt TEXT DEFAULT ''")
    thread_cols = {r["name"] for r in conn.execute("PRAGMA table_info(plot_threads)")}
    if "description" not in thread_cols:
        conn.execute("ALTER TABLE plot_threads ADD COLUMN description TEXT DEFAULT ''")
    conn.commit()


def add_novel(conn, title, genre, premise, selling_point="", target_words=2200, platform="fanqie"):
    cur = conn.execute(
        "INSERT INTO novels(title,genre,premise,selling_point,target_words,platform) "
        "VALUES(?,?,?,?,?,?)",
        (title, genre, premise, selling_point, target_words, platform),
    )
    conn.commit()
    return cur.lastrowid


def add_volume(conn, novel_id, seq, goal, outline=""):
    cur = conn.execute(
        "INSERT INTO volumes(novel_id,seq,goal,outline) VALUES(?,?,?,?)",
        (novel_id, seq, goal, outline),
    )
    conn.commit()
    return cur.lastrowid


def add_chapter(conn, novel_id, volume_id, seq, outline):
    cur = conn.execute(
        "INSERT INTO chapters(novel_id,volume_id,seq,outline) VALUES(?,?,?,?)",
        (novel_id, volume_id, seq, outline),
    )
    conn.commit()
    return cur.lastrowid


def update_chapter_after_review(conn, chapter_id, words, score, passed):
    status = "reviewed" if passed else "draft"
    conn.execute("UPDATE chapters SET words=?, score=?, status=? WHERE id=?", (words, score, status, chapter_id))
    conn.commit()


def add_quality_report(conn, chapter_id, scores, passed, revision_count=0):
    cur = conn.execute(
        "INSERT INTO quality_reports(chapter_id,scores,passed,revision_count) VALUES(?,?,?,?)",
        (chapter_id, json.dumps(scores, ensure_ascii=False), int(passed), revision_count),
    )
    conn.commit()
    return cur.lastrowid


def add_publish_log(conn, chapter_id, platform, action, result, error=None, ai_declared=1):
    cur = conn.execute(
        "INSERT INTO publish_logs(chapter_id,platform,action,result,error,ai_declared,created_at) "
        "VALUES(?,?,?,?,?,?,datetime('now','localtime'))",
        (chapter_id, platform, action, result, error, int(ai_declared)),
    )
    conn.commit()
    return cur.lastrowid


def add_chapter_summary(conn, chapter_id, summary, character_states="{}", world_events="[]"):
    cur = conn.execute(
        "INSERT INTO chapter_summaries(chapter_id,summary,character_states,world_events) "
        "VALUES(?,?,?,?)",
        (chapter_id, summary, character_states, world_events),
    )
    conn.commit()
    return cur.lastrowid
