"""Knowledge base for writing agents: prompts/knowledge/*.md packages.

Each package is a markdown file with YAML-ish frontmatter:
    agents: [writer, editor]   # applicable agents, 'all' allowed
    type: craft|market|generic
    keywords: [hook, opening]
    source: ...
    updated_at: ...
"""

import json
import re
from datetime import datetime

from novel_editorial import config

KNOWLEDGE_DIR = config.ROOT / "prompts" / "knowledge"


def _parse(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", 2)
    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()
        if k in ("agents", "keywords") and v:
            try:
                v = json.loads(v)
            except ValueError:
                v = [x.strip().strip("'\"") for x in v.strip("[]").split(",") if x.strip()]
        meta[k] = v
    return meta, (parts[2].strip() if len(parts) > 2 else "")


def list_knowledge():
    if not KNOWLEDGE_DIR.exists():
        return []
    out = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        meta, body = _parse(path)
        first_line = next((l.strip() for l in body.splitlines() if l.strip()), "")
        out.append(
            {
                "file": path.name,
                "title": meta.get("title") or path.stem,
                "agents": meta.get("agents") or [],
                "type": meta.get("type") or "craft",
                "keywords": meta.get("keywords") or [],
                "source": meta.get("source") or "",
                "updated_at": meta.get("updated_at") or "",
                "summary": first_line.lstrip("#").strip()[:120],
            }
        )
    return out


def read_knowledge(file):
    path = _resolve_knowledge(file)
    if path is None or not path.exists() or path.suffix != ".md":
        return None
    meta, body = _parse(path)
    return {"file": path.name, "meta": meta, "body": body}


def write_knowledge(file, meta, body):
    path = _resolve_knowledge(file)
    if path is None:
        raise ValueError("knowledge file path escapes the knowledge directory")
    if path.suffix != ".md":
        raise ValueError("knowledge file must be .md")
    meta["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta.setdefault("title", path.stem)
    meta.setdefault("type", "craft")
    meta.setdefault("agents", [])
    meta.setdefault("keywords", [])
    for key in ("title", "source", "updated_at"):
        value = str(meta.get(key) or "")
        if "\n" in value or "\r" in value:
            raise ValueError(f"knowledge frontmatter field '{key}' must not contain newlines")
    head = (
        f"---\ntitle: {meta['title']}\ntype: {meta['type']}\n"
        f"agents: {json.dumps(meta['agents'], ensure_ascii=False)}\n"
        f"keywords: {json.dumps(meta['keywords'], ensure_ascii=False)}\n"
        f"source: {meta.get('source', '')}\n"
        f"updated_at: {meta['updated_at']}\n---\n\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(head + body.strip() + "\n", encoding="utf-8")
    return {"file": path.name, "meta": meta, "body": body.strip()}


def _resolve_knowledge(file):
    """Resolve a knowledge file and reject path traversal outside the dir."""
    root = KNOWLEDGE_DIR.resolve()
    path = (KNOWLEDGE_DIR / str(file)).resolve()
    if path != root and root not in path.parents:
        return None
    return path


def _matches(agent, meta):
    agents = meta.get("agents") or []
    return "all" in agents or agent in agents


def resolve_knowledge(agent, topic):
    """Return knowledge packages for an agent matching a topic."""
    if not KNOWLEDGE_DIR.exists():
        return []
    topic = (topic or "").strip().lower()
    if not topic:
        # No topic means the model did not ask precisely: returning every
        # package would bloat the context. Ask it to name a topic instead.
        return []
    hits = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        meta, body = _parse(path)
        if not _matches(agent, meta):
            continue
        keywords = [str(k).lower() for k in (meta.get("keywords") or [])]
        hay = " ".join(
            [
                path.stem,
                str(meta.get("title", "")),
                str(meta.get("type", "")),
                " ".join(keywords),
            ]
        ).lower()
        matched = (
            topic in hay
            or any(
                (len(t) >= 2 and (t in kw or kw in t))
                for kw in keywords
                for t in topic.split()
            )
        )
        if matched:
            hits.append(
                {
                    "file": path.name,
                    "title": meta.get("title") or path.stem,
                    "type": meta.get("type") or "craft",
                    "content": body,
                }
            )
    return hits[:3]


def build_knowledge_index(agent):
    """One-line index of packages available to an agent (for system prompts)."""
    if not KNOWLEDGE_DIR.exists():
        return ""
    lines = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        meta, body = _parse(path)
        if not _matches(agent, meta):
            continue
        title = meta.get("title") or path.stem
        keywords = "、".join(str(k) for k in (meta.get("keywords") or [])[:5])
        lines.append(f"- {title}（关键词：{keywords}）")
    if not lines:
        return ""
    return "可用知识包：\n" + "\n".join(lines)


def clean_title(text):
    """Strip font-anti-crawl artifacts from scraped titles."""
    if not text:
        return ""
    # keep CJK, ASCII, digits and common punctuation; drop private-use glyphs
    cleaned = re.sub(
        r"[\uE000-\uF8FF\ud800-\udfff\u200b-\u200f\ufeff]", "", text
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def list_drafts(conn, status=None):
    if status:
        rows = conn.execute(
            "SELECT * FROM knowledge_drafts WHERE status=? ORDER BY id DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM knowledge_drafts ORDER BY id DESC"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["agents"] = json.loads(d.get("agents") or "[]")
        except ValueError:
            d["agents"] = []
        out.append(d)
    return out


def add_draft(conn, kind, title, content, agent="", source="", agents=None):
    cur = conn.execute(
        "INSERT INTO knowledge_drafts(kind,agent,source,title,content,agents,status,created_at) "
        "VALUES(?,?,?,?,?,?,?,datetime('now','localtime'))",
        (
            kind,
            agent,
            source,
            title,
            content,
            json.dumps(agents or [], ensure_ascii=False),
            "draft",
        ),
    )
    conn.commit()
    return cur.lastrowid


def update_draft_status(conn, draft_id, status):
    cur = conn.execute(
        "UPDATE knowledge_drafts SET status=?, accepted_at=datetime('now','localtime') "
        "WHERE id=? AND status='draft'",
        (status, draft_id),
    )
    conn.commit()
    return cur.rowcount > 0
