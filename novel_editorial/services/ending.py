"""Ending lifecycle: status, next-book confirmation, book binding."""

import json

from novel_editorial import config
from novel_editorial.services import audit


def ending_status(conn):
    novels = conn.execute(
        "SELECT id, title, status, book_id, cover_prompt, target_chapters, "
        "finish_remaining, finish_note, updated_at, "
        "premise, abstract, selling_point, tags "
        "FROM novels ORDER BY id"
    ).fetchall()
    out = []
    for n in novels:
        d = dict(n)
        d["next_book_pending"] = n["status"] == "planning"
        out.append(d)
    return {"novels": out}


def confirm_next_book(conn, novel_id):
    row = conn.execute(
        "SELECT id FROM novels WHERE id=? AND status='planning'", (novel_id,)
    ).fetchone()
    if row is None:
        return {"ok": False, "error": "找不到待确认的新书"}
    conn.execute("UPDATE novels SET status='ready' WHERE id=?", (novel_id,))
    conn.commit()
    audit.log(conn, "ending", "confirm_next_book", target_type="novel", target_id=novel_id)
    return {"ok": True, "note": "新书创意已确认，请在番茄建书后绑定 book_id"}


def bind_book(conn, novel_id, book_id, volume_id=""):
    row = conn.execute(
        "SELECT id, title FROM novels WHERE id=? AND status='ready'", (novel_id,)
    ).fetchone()
    if row is None:
        return {"ok": False, "error": "新书未确认（先确认创意）"}
    book_id = str(book_id or "").strip()
    if not book_id:
        return {"ok": False, "error": "book_id 不能为空"}
    env_file = config.N8N_ENV_FILE
    lines = []
    replaced = {"FANQIE_BOOK_ID": False, "FANQIE_VOLUME_ID": False}
    try:
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("FANQIE_BOOK_ID="):
                    lines.append(f"FANQIE_BOOK_ID={book_id}")
                    replaced["FANQIE_BOOK_ID"] = True
                elif line.startswith("FANQIE_VOLUME_ID="):
                    lines.append(f"FANQIE_VOLUME_ID={volume_id}")
                    replaced["FANQIE_VOLUME_ID"] = True
                else:
                    lines.append(line)
        if not replaced["FANQIE_BOOK_ID"]:
            lines.append(f"FANQIE_BOOK_ID={book_id}")
        if not replaced["FANQIE_VOLUME_ID"]:
            lines.append(f"FANQIE_VOLUME_ID={volume_id}")
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {"ok": False, "error": f"n8n env 写入失败，未修改数据库: {exc}"}
    conn.execute(
        "UPDATE novels SET book_id=?, volume_id=?, status='publishing' WHERE id=?",
        (book_id, volume_id, novel_id),
    )
    conn.commit()
    audit.log(
        conn,
        "ending",
        "bind_book",
        target_type="novel",
        target_id=novel_id,
        detail={"book_id": book_id, "volume_id": volume_id},
    )
    return {"ok": True, "note": f"已绑定新书 {book_id}；重启 n8n 后日更自动切换"}
