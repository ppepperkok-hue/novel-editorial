"""Generic article producer: plan -> write -> polish -> review -> save to disk.

Registered in `tools/producers.py` as "article". The workday dispatches here
when `settings.workday_producer` is "article"; the novel chain is untouched.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import config  # noqa: E402
from tools import agent_tool_loop, app_settings  # noqa: E402


def _slug(text, fallback="article"):
    """Filesystem-safe slug from a title (strip dangerous chars)."""
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", str(text or ""), flags=re.UNICODE)
    s = s.strip("-").strip(".")[:60]
    return s or fallback


def _out_dir(conn):
    name = app_settings.get_str(conn, "article_output_dir", "")
    if name:
        p = Path(name)
        if not p.is_absolute():
            p = ROOT / p
    else:
        p = ROOT / "exports" / "articles"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _call(agent, task, *, dry_run, db_path, target_words=None, mock_text="占位内容"):
    """One agent call via the tool loop; dry-run uses a placeholder."""
    if dry_run:
        return {"ok": True, "text": mock_text, "used_knowledge": [], "attempts": 1}
    return agent_tool_loop.run(
        agent,
        task,
        target_words=target_words,
        novel_id=0,
        db_path=str(db_path),
    )


def produce_article(
    conn,
    *,
    target=None,
    trigger="manual",
    dry_run=False,
    db_path=None,
    workday_run_id=None,
    lock_held=False,
    skip_diaries=False,
    boss_instruction="",
    plan=None,
):
    """Produce one generic article and save it as markdown under exports/."""
    plan = plan or {}
    topic = str(boss_instruction or plan.get("focus") or "自由写作").strip()
    target_words = int(target or app_settings.get_int(conn, "article_target_words", 2000))
    steps = []
    errors = []

    # 1. Planner: topic -> structure (free-form JSON or plain outline)
    plan_task = (
        f"为下面的写作主题做一份内容策划（主题、角度、结构、要点）：\n{topic}\n"
        "只输出 JSON：{title, angle, structure(数组), key_points(数组)}。"
    )
    plan_res = _call("planner", plan_task, dry_run=dry_run, db_path=db_path,
                     mock_text='{"title": "占位标题", "angle": "占位角度", '
                               '"structure": ["开场", "主体", "收束"], "key_points": []}')
    plan_ok = bool(plan_res.get("ok"))
    steps.append({"step": "plan", "ok": plan_ok,
                  "error": plan_res.get("error") if not plan_ok else ""})
    if not plan_ok:
        errors.append(f"plan: {plan_res.get('error') or 'unknown'}")
    try:
        plan_data = json.loads(plan_res.get("text") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        plan_data = {}
    title = str(plan_data.get("title") or topic)[:120]

    # 2. Writer: body
    write_task = (
        f"写作主题：{topic}\n内容策划：{json.dumps(plan_data, ensure_ascii=False)}\n"
        "按策划写正文，只输出正文。"
    )
    write_res = _call("writer", write_task, dry_run=dry_run, db_path=db_path,
                      target_words=target_words,
                      mock_text="这是占位正文。\n\n第二段占位内容。")
    write_ok = bool(write_res.get("ok"))
    steps.append({"step": "write", "ok": write_ok,
                  "error": write_res.get("error") if not write_ok else ""})
    body = str(write_res.get("text") or "").strip()
    if not write_ok or not body:
        write_err = write_res.get("error") or ("产出为空" if not body else "unknown")
        errors.append(f"write: {write_err}")
        return {
            "ok": False,
            "status": "failed",
            "published": 0,
            "files": [],
            "steps": steps,
            "error": f"写稿步骤失败，未落盘：{write_err}",
            "errors": errors,
            "dry_run": dry_run,
        }

    # 3. Editor: polish
    polish_res = _call("editor", "润色下面正文，输出润色后的正文：\n" + body[:20000],
                       dry_run=dry_run, db_path=db_path, mock_text=body)
    polish_ok = bool(polish_res.get("ok"))
    steps.append({"step": "polish", "ok": polish_ok,
                  "error": polish_res.get("error") if not polish_ok else ""})
    if not polish_ok:
        errors.append(f"polish: {polish_res.get('error') or 'unknown'}（降级用原文）")
    polished = str(polish_res.get("text") or body).strip()

    # 4. Reviewer: review JSON
    review_res = _call("reviewer", "审稿下面正文，按你的 JSON 契约输出：\n" + polished[:20000],
                       dry_run=dry_run, db_path=db_path,
                       mock_text='{"passed": true, "issues": [], "suggestions": []}')
    review_ok = bool(review_res.get("ok"))
    steps.append({"step": "review", "ok": review_ok,
                  "error": review_res.get("error") if not review_ok else ""})
    if not review_ok:
        errors.append(f"review: {review_res.get('error') or 'unknown'}（按未通过处理）")
    try:
        review = json.loads(review_res.get("text") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        review = {}
    passed = bool(review.get("passed", True))

    # 5. Save markdown (dry-run skips persistence)
    files = []
    status = "completed" if passed else "completed_with_pending"
    if not dry_run:
        out_dir = _out_dir(conn)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = out_dir / f"{stamp}-{_slug(title)}.md"
        head = (
            f"# {title}\n\n"
            f"> 主题：{topic}\n"
            f"> 产出时间：{datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"> 审稿：{'通过' if passed else '未通过（见审稿意见）'}\n\n---\n\n"
        )
        review_note = ""
        if review.get("issues"):
            review_note = "\n\n---\n\n## 审稿意见\n" + "\n".join(
                f"- [{i.get('severity', 'minor')}] {i.get('desc', '')}"
                for i in review["issues"][:10]
            )
        path.write_text(head + polished + review_note, encoding="utf-8")
        files.append(str(path))

    return {
        "ok": True,
        "status": status,
        "published": 1 if not dry_run else 0,
        "files": files,
        "title": title,
        "steps": steps,
        "review_passed": passed,
        "errors": errors,
        "dry_run": dry_run,
    }
