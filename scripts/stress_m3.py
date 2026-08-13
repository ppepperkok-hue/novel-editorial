"""M3 stage-close stress baseline for the event stream, retrieval, and isolation paths."""

from __future__ import annotations

import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from novel_editorial.core.chat import AUTHOR_ACTOR, record_message
from novel_editorial.core.config import load_settings
from novel_editorial.core.decision import decide
from novel_editorial.core.draft import generate_draft
from novel_editorial.core.memory import add_memory_note
from novel_editorial.core.plot import KIND_FORESHADOW, KIND_GOAL, KIND_HOOK, plant_thread
from novel_editorial.core.review import add_review
from novel_editorial.core.workspace import create_workspace
from novel_editorial.events import EventType
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events_since, record_event
from novel_editorial.store.models import Agent, AgentRole

ROOT = Path(__file__).resolve().parent.parent

EVENT_COUNT = 10000
EVENT_WRITE_SECONDS = 60.0
EVENT_SCAN_SECONDS = 10.0
CLI_EVENTS_SECONDS = 5.0
SEARCH_SECONDS = 10.0
WORKS_LIST_SECONDS = 5.0
SEARCH_RUNS = 3

DRAFT_MIN_CHARS = 5000
DRAFT_COUNT = 100
MESSAGE_COUNT = 500
REVIEW_COUNT = 200
NOTE_COUNT = 100
THREAD_COUNT = 50
DECISION_COUNT = 20
ISOLATION_WORKSPACES = 10

ACTORS = ("总编", "责编", "写手", "审稿")
KEYWORD = "旧车站"
MISS_KEYWORD = "不存在的词"
UNIQUE_WORD = "甲书密语"

LLM_KEYS = ("NOVEL_LLM_API_KEY", "NOVEL_LLM_BASE_URL", "NOVEL_LLM_MODEL")

ROLE_TO_ALIAS = {
    AgentRole.EDITOR_IN_CHIEF: "总编",
    AgentRole.EDITOR: "责编",
    AgentRole.WRITER: "写手",
    AgentRole.REVIEWER: "审稿",
}

T = TypeVar("T")

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if callable(_reconfigure):
        _reconfigure(encoding="utf-8", errors="replace")


def build_env(tmp: Path) -> dict[str, str]:
    """Return a clean sandbox env: temp data dir and no real LLM credentials."""
    env = dict(os.environ)
    for key in LLM_KEYS:
        env.pop(key, None)
    env["NOVEL_DATA_DIR"] = str(tmp / "data")
    env["NOVEL_CONFIG"] = str(tmp / "config.toml")
    return env


def run_cli(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "novel-editorial", *args],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        check=False,
    )


def timed_ms(operation: Callable[[], T]) -> tuple[float, T]:
    start = time.perf_counter()
    result = operation()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return elapsed_ms, result


def record(failures: list[str], label: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "FAIL"
    if not ok:
        failures.append(f"{label}: {detail}")
    print(f"[{status}] {label} ({detail})")


def writer_agent_id(db: DB, workspace_id: str) -> str:
    with db.workspace_session(workspace_id) as session:
        writer = (
            session.query(Agent).filter_by(workspace_id=workspace_id, role=AgentRole.WRITER).first()
        )
    if writer is None:
        raise RuntimeError(f"writer agent missing in workspace {workspace_id}")
    return writer.id


def workspace_agents(db: DB, workspace_id: str) -> list[Agent]:
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id)
            .order_by(Agent.created_at)
            .all()
        )


def scenario_a(db: DB, workspace_id: str, env: dict[str, str], failures: list[str]) -> None:
    print("=== 场景 A：事件流压力 ===")

    def write_events() -> None:
        for index in range(EVENT_COUNT):
            record_event(
                db,
                workspace_id,
                type=EventType.SYSTEM,
                actor=ACTORS[index % len(ACTORS)],
                payload={"n": index, "note": "stress"},
            )

    write_ms, _ = timed_ms(write_events)
    write_seconds = write_ms / 1000.0
    record(
        failures,
        f"A1 record_event 写入 {EVENT_COUNT} 条",
        write_seconds < EVENT_WRITE_SECONDS,
        f"{write_seconds:.2f}s（阈值 <{EVENT_WRITE_SECONDS:.0f}s）",
    )

    def scan_events() -> tuple[int, bool]:
        events = list_events_since(db, workspace_id, after_rowid=None)
        increasing = all(
            events[index].rowid < events[index + 1].rowid for index in range(len(events) - 1)
        )
        return len(events), increasing

    scan_ms, (count, increasing) = timed_ms(scan_events)
    scan_seconds = scan_ms / 1000.0
    record(
        failures,
        f"A2 list_events_since 遍历 {count} 条",
        count == EVENT_COUNT and increasing and scan_seconds < EVENT_SCAN_SECONDS,
        f"{scan_seconds:.2f}s（阈值 <{EVENT_SCAN_SECONDS:.0f}s；数量 {count}，"
        f"rowid 严格递增 {increasing}）",
    )

    cli_ms, result = timed_ms(lambda: run_cli(env, "events", "list", workspace_id, "--limit", "20"))
    cli_seconds = cli_ms / 1000.0
    record(
        failures,
        "A3 CLI events list --limit 20 冒烟",
        result.returncode == 0 and cli_seconds < CLI_EVENTS_SECONDS,
        f"{cli_seconds:.2f}s（阈值 <{CLI_EVENTS_SECONDS:.0f}s；exit {result.returncode}）",
    )
    if result.stdout.strip():
        print(f"  out: {result.stdout.strip().splitlines()[0][:120]}")


def draft_text(version: int) -> str:
    """Deterministic ~5000-char Chinese prose carrying the searchable keyword."""
    block_template = (
        "雨夜里他回到旧车站，站台上没有一个人，只有一盏灯在风里轻轻晃动。"
        "铁轨在远处泛着冷光，旧车站的钟停在十一点，售票窗口的玻璃结满雾气。"
    )
    parts: list[str] = []
    size = 0
    block = 0
    while size < DRAFT_MIN_CHARS:
        part = f"第{version}稿第{block}段：{block_template}"
        parts.append(part)
        size += len(part)
        block += 1
    return "".join(parts)


def scenario_b(db: DB, workspace_id: str, env: dict[str, str], failures: list[str]) -> None:
    print("=== 场景 B：检索压力（瓶颈 2 基线） ===")
    write_start = time.perf_counter()

    first_draft = generate_draft(
        db,
        workspace_id,
        title=KEYWORD,
        client=MockLLMClient(reply=draft_text(1)),
    )
    draft_id = first_draft.id
    for version in range(2, DRAFT_COUNT + 1):
        generate_draft(
            db,
            workspace_id,
            title=KEYWORD,
            client=MockLLMClient(reply=draft_text(version)),
        )

    for index in range(MESSAGE_COUNT):
        if index % 2:
            record_message(
                db,
                workspace_id,
                role="author",
                actor=AUTHOR_ACTOR,
                content=f"作者留言 {index}：{KEYWORD}的雨夜要不要写进结尾？",
            )
        else:
            record_message(
                db,
                workspace_id,
                role="agent",
                actor=ACTORS[index % len(ACTORS)],
                content=f"伙伴回应 {index}：{KEYWORD}那段先留白，节奏更稳。",
            )

    for index in range(REVIEW_COUNT):
        if index % 2:
            add_review(
                db,
                workspace_id,
                draft_id,
                role="author",
                actor=AUTHOR_ACTOR,
                content=f"作者意见 {index}：{KEYWORD}的钟声前后要一致。",
            )
        else:
            add_review(
                db,
                workspace_id,
                draft_id,
                role="agent",
                actor=ACTORS[index % len(ACTORS)],
                content=f"退稿意见 {index}：{KEYWORD}的细节有矛盾。",
            )

    agents = workspace_agents(db, workspace_id)
    for index in range(NOTE_COUNT):
        agent = agents[index % len(agents)]
        add_memory_note(
            db,
            workspace_id,
            agent.id,
            actor=ROLE_TO_ALIAS[agent.role],
            content=f"私密笔记 {index}：{KEYWORD}的钩子别急着回收。",
        )

    thread_kinds = (KIND_FORESHADOW, KIND_GOAL, KIND_HOOK)
    for index in range(THREAD_COUNT):
        plant_thread(
            db,
            workspace_id,
            kind=thread_kinds[index % len(thread_kinds)],
            content=f"{KEYWORD}线索 {index}：钟声在结尾敲响。",
            chapter=f"第{index % 20 + 1}章",
        )

    for index in range(DECISION_COUNT):
        decide(
            db,
            workspace_id,
            draft_id,
            action="note",
            content=f"决策备注 {index}：{KEYWORD}的结局方案待定。",
        )

    write_seconds = (time.perf_counter() - write_start) / 1.0
    print(
        f"  数据写入 {DRAFT_COUNT} 版草稿 / {MESSAGE_COUNT} 消息 / {REVIEW_COUNT} 意见 / "
        f"{NOTE_COUNT} 笔记 / {THREAD_COUNT} 线索 / {DECISION_COUNT} 决策：{write_seconds:.2f}s"
    )

    bench_search(
        env, failures, f"B1 memory search「{KEYWORD}」", "memory", "search", workspace_id, KEYWORD
    )
    bench_search(env, failures, f"B2 inspect「{KEYWORD}」", "inspect", workspace_id, KEYWORD)

    miss_ms, result = timed_ms(lambda: run_cli(env, "inspect", workspace_id, MISS_KEYWORD))
    miss_seconds = miss_ms / 1000.0
    record(
        failures,
        f"B3 inspect 无命中词「{MISS_KEYWORD}」",
        result.returncode == 0
        and result.stdout.strip() == "no matches"
        and miss_seconds < SEARCH_SECONDS,
        f"{miss_seconds:.2f}s（阈值 <{SEARCH_SECONDS:.0f}s；exit {result.returncode}）",
    )


def bench_search(
    env: dict[str, str],
    failures: list[str],
    label: str,
    *args: str,
) -> None:
    samples: list[float] = []
    exits: list[int] = []
    hits: list[bool] = []
    for _ in range(SEARCH_RUNS):
        elapsed_ms, result = timed_ms(lambda: run_cli(env, *args))
        samples.append(elapsed_ms)
        exits.append(result.returncode)
        hits.append("[版本]" in (result.stdout or ""))
        print(f"  run {len(samples)}: {elapsed_ms:.0f} ms")
    median = statistics.median(samples)
    record(
        failures,
        label,
        median / 1000.0 < SEARCH_SECONDS
        and all(exit_code == 0 for exit_code in exits)
        and all(hits),
        f"median {median:.0f} ms（阈值 <{SEARCH_SECONDS:.0f}s；"
        f"{SEARCH_RUNS} 次 exit {exits}，命中版本层 {hits}）",
    )


def scenario_c(db: DB, env: dict[str, str], failures: list[str]) -> None:
    print("=== 场景 C：多作品隔离压力 ===")
    workspace_ids: list[str] = []
    for index in range(ISOLATION_WORKSPACES):
        workspace = create_workspace(
            db,
            title=f"压测书{index + 1}",
            genre="悬疑",
            description=f"隔离压力测试作品 {index + 1}",
        )
        workspace_ids.append(workspace.id)

    for index, workspace_id in enumerate(workspace_ids):
        record_message(
            db,
            workspace_id,
            role="author",
            actor=AUTHOR_ACTOR,
            content=f"开场消息 {index}：雨夜，旧街。",
        )
        plant_thread(
            db,
            workspace_id,
            kind=KIND_FORESHADOW,
            content=f"线索 {index}：门没有锁。",
        )
        add_memory_note(
            db,
            workspace_id,
            writer_agent_id(db, workspace_id),
            actor="写手",
            content=f"笔记 {index}：第三幕反转。",
        )

    record_message(
        db,
        workspace_ids[0],
        role="author",
        actor=AUTHOR_ACTOR,
        content=f"{UNIQUE_WORD}：只有甲书知道这句话。",
    )

    cross_hits = 0
    for workspace_id in workspace_ids[1:]:
        result = run_cli(env, "inspect", workspace_id, UNIQUE_WORD)
        if result.returncode != 0 or result.stdout.strip() != "no matches":
            cross_hits += 1
            failures.append(
                f"C1 inspect 隔离: workspace {workspace_id} 串词 "
                f"(exit {result.returncode}, out {result.stdout.strip()[:80]})"
            )
    isolated = cross_hits == 0
    record(
        failures,
        f"C1 inspect 其余 {len(workspace_ids) - 1} 个作品查「{UNIQUE_WORD}」",
        isolated,
        f"{len(workspace_ids) - 1} 次全部 no matches" if isolated else f"{cross_hits} 次串词",
    )

    list_ms, result = timed_ms(lambda: run_cli(env, "works", "list"))
    list_seconds = list_ms / 1000.0
    record(
        failures,
        "C2 works list",
        result.returncode == 0 and list_seconds < WORKS_LIST_SECONDS,
        f"{list_seconds:.2f}s（阈值 <{WORKS_LIST_SECONDS:.0f}s；exit {result.returncode}）",
    )


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="m3-stress-"))
    env = build_env(tmp)
    settings = load_settings(env)
    db = DB(settings)
    db.init_schema()
    failures: list[str] = []

    print("=== M3 阶段收关压力基线 ===")
    workspace = create_workspace(
        db,
        title="压力测试甲",
        genre="悬疑",
        description="事件流与检索压力场景",
    )
    print(f"workspace A: {workspace.id}")

    scenario_a(db, workspace.id, env, failures)
    scenario_b(db, workspace.id, env, failures)
    scenario_c(db, env, failures)

    print(f"\n临时数据目录（保留）: {tmp}")
    if failures:
        print(f"\n失败 {len(failures)} 项:")
        for failure in failures:
            print(f"  - {failure}")
        print("\nSTRESS FAIL")
        return 1
    print("\nSTRESS OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
