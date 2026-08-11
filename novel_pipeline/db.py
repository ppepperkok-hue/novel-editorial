"""SQLite 数据层：小说 / 分卷 / 章节 / 角色 / 事件 / 伏笔 / 质量报告 / 发布日志。"""

import json
import sqlite3
import threading
from pathlib import Path

_INIT_LOCK = threading.Lock()
_INITIALIZED = set()

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
    volume_id TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    abstract TEXT DEFAULT '',
    protagonists TEXT DEFAULT '[]',
    outline TEXT DEFAULT '{}',
    volume_goal TEXT DEFAULT '',
    updated_at TEXT DEFAULT '',
    target_chapters INTEGER DEFAULT 0,
    finish_remaining INTEGER DEFAULT 0,
    finish_note TEXT DEFAULT '',
    cover_prompt TEXT DEFAULT ''
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
    run_id TEXT DEFAULT '',
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
    status TEXT DEFAULT 'completed',
    kind TEXT DEFAULT 'weekly'
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

CREATE TABLE IF NOT EXISTS meeting_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT DEFAULT 'topic',
    topic TEXT NOT NULL,
    status TEXT DEFAULT 'running',
    novel_id INTEGER DEFAULT 0,
    current_round INTEGER DEFAULT 0,
    attendees TEXT DEFAULT '[]',
    transcript TEXT DEFAULT '[]',
    instruction TEXT DEFAULT '',
    report TEXT DEFAULT '',
    db_path TEXT DEFAULT '',
    current_agent TEXT DEFAULT '',
    heartbeat_at TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS knowledge_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL DEFAULT 'lesson',
    agent TEXT DEFAULT '',
    source TEXT DEFAULT '',
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    agents TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT DEFAULT '',
    accepted_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS novel_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    entity TEXT NOT NULL,
    content TEXT NOT NULL,
    source_chapter INTEGER,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT DEFAULT '',
    UNIQUE(novel_id, category, entity)
);

CREATE TABLE IF NOT EXISTS novel_knowledge_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_id INTEGER NOT NULL REFERENCES novel_knowledge(id),
    content TEXT NOT NULL,
    version INTEGER NOT NULL,
    change_note TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agent_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER DEFAULT 0,
    meeting_id INTEGER DEFAULT 0,
    agent TEXT NOT NULL,
    novel_id INTEGER,
    task TEXT NOT NULL,
    detail TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT DEFAULT '',
    completed_at TEXT DEFAULT '',
    result TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agent_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    novel_id INTEGER,
    activity_type TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT DEFAULT '{}',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS daily_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    novel_id INTEGER DEFAULT 0,
    trigger TEXT DEFAULT 'scheduled',
    source TEXT DEFAULT 'scheduler',
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT DEFAULT '',
    finished_at TEXT DEFAULT '',
    failed_nodes TEXT DEFAULT '[]',
    error TEXT DEFAULT '',
    published INTEGER DEFAULT 0,
    detail TEXT DEFAULT '{}',
    created_at TEXT DEFAULT ''
);
"""


def connect(db_path):
    """Connect to the SQLite database.

    Schema creation/migration runs exactly once per database path (process
    lifetime); subsequent connects are lightweight and set per-connection
    pragmas. WAL mode is enabled once and persists in the database file.
    """
    key = str(Path(db_path).resolve())
    with _INIT_LOCK:
        if key not in _INITIALIZED:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.executescript(SCHEMA)
            _migrate(conn)
            conn.execute("PRAGMA journal_mode=WAL").fetchall()
            conn.commit()
            conn.close()
            _INITIALIZED.add(key)
    conn = sqlite3.connect(str(db_path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate(conn):
    """Add columns introduced after the first schema version."""
    novel_cols = {r["name"] for r in conn.execute("PRAGMA table_info(novels)")}
    for col, ddl in {
        "book_id": "TEXT DEFAULT ''",
        "volume_id": "TEXT DEFAULT ''",
        "tags": "TEXT DEFAULT '[]'",
        "abstract": "TEXT DEFAULT ''",
        "protagonists": "TEXT DEFAULT '[]'",
        "outline": "TEXT DEFAULT '{}'",
        "volume_goal": "TEXT DEFAULT ''",
        "updated_at": "TEXT DEFAULT ''",
        "cover_prompt": "TEXT DEFAULT ''",
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
    cost_cols = {r["name"] for r in conn.execute("PRAGMA table_info(cost_logs)")}
    if "run_id" not in cost_cols:
        conn.execute("ALTER TABLE cost_logs ADD COLUMN run_id TEXT DEFAULT ''")
    thread_cols = {r["name"] for r in conn.execute("PRAGMA table_info(plot_threads)")}
    if "description" not in thread_cols:
        conn.execute("ALTER TABLE plot_threads ADD COLUMN description TEXT DEFAULT ''")
    meeting_cols = {r["name"] for r in conn.execute("PRAGMA table_info(weekly_meetings)")}
    if "kind" not in meeting_cols:
        conn.execute("ALTER TABLE weekly_meetings ADD COLUMN kind TEXT DEFAULT 'weekly'")
    session_cols = {r["name"] for r in conn.execute("PRAGMA table_info(meeting_sessions)")}
    if "db_path" not in session_cols:
        conn.execute("ALTER TABLE meeting_sessions ADD COLUMN db_path TEXT DEFAULT ''")
    if "current_agent" not in session_cols:
        conn.execute("ALTER TABLE meeting_sessions ADD COLUMN current_agent TEXT DEFAULT ''")
    if "heartbeat_at" not in session_cols:
        conn.execute("ALTER TABLE meeting_sessions ADD COLUMN heartbeat_at TEXT DEFAULT ''")
    weekly_cols = {r["name"] for r in conn.execute("PRAGMA table_info(weekly_meetings)")}
    if "session_id" not in weekly_cols:
        conn.execute("ALTER TABLE weekly_meetings ADD COLUMN session_id INTEGER DEFAULT 0")
    run_cols = {r["name"] for r in conn.execute("PRAGMA table_info(daily_runs)")}
    if "source" not in run_cols:
        conn.execute("ALTER TABLE daily_runs ADD COLUMN source TEXT DEFAULT 'scheduler'")
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_chapters_novel_seq ON chapters(novel_id, seq);
        CREATE INDEX IF NOT EXISTS idx_publish_logs_chapter ON publish_logs(chapter_id);
        CREATE INDEX IF NOT EXISTS idx_cost_logs_created ON cost_logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_diaries_agent ON agent_diaries(agent, novel_id, diary_type);
        CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_knowledge_lookup ON novel_knowledge(novel_id, category, entity);
        CREATE INDEX IF NOT EXISTS idx_actions_agent_status ON agent_actions(agent, status);
        CREATE INDEX IF NOT EXISTS idx_actions_session ON agent_actions(session_id);
        CREATE INDEX IF NOT EXISTS idx_activity_agent_created ON agent_activity(agent, created_at);
        CREATE INDEX IF NOT EXISTS idx_activity_created ON agent_activity(created_at);
        CREATE INDEX IF NOT EXISTS idx_daily_runs_status ON daily_runs(status, created_at);
        """
    )
    # Deduplicate (novel_id, seq) keeping the published row when possible;
    # clean child tables first so no orphan rows are left behind. A correlated
    # EXISTS works on SQLite < 3.25 too (no ROW_NUMBER requirement).
    dup_rows = conn.execute(
        "SELECT id FROM chapters c WHERE EXISTS ("
        "  SELECT 1 FROM chapters c2 "
        "  WHERE c2.novel_id = c.novel_id AND c2.seq = c.seq "
        "    AND ((c2.status = c.status AND c2.id < c.id) "
        "      OR (c2.status='published' AND c.status!='published'))"
        ")"
    ).fetchall()
    dup_ids = [r["id"] for r in dup_rows]
    if dup_ids:
        marks = ",".join("?" * len(dup_ids))
        for table, col in (
            ("publish_logs", "chapter_id"),
            ("quality_reports", "chapter_id"),
            ("chapter_content", "chapter_id"),
            ("chapter_summaries", "chapter_id"),
            ("world_events", "chapter_id"),
            ("character_evolution", "chapter_id"),
        ):
            conn.execute(f"DELETE FROM {table} WHERE {col} IN ({marks})", dup_ids)
        conn.execute(f"DELETE FROM chapters WHERE id IN ({marks})", dup_ids)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_chapters_novel_seq_unique "
        "ON chapters(novel_id, seq)"
    )
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
