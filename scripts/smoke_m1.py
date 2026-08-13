"""Phase 2 verification smoke: run the full M1 loop and edge cases via the CLI."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="m1-smoke-"))
    env = dict(os.environ)
    env["NOVEL_DATA_DIR"] = str(tmp / "data")
    env["NOVEL_CONFIG"] = str(tmp / "config.toml")
    failures: list[str] = []

    def check(label: str, expected: int, *args: str, extra_env: dict | None = None) -> str:
        run_env = dict(env)
        if extra_env:
            run_env.update(extra_env)
        result = run_cli(run_env, *args)
        status = "OK" if result.returncode == expected else "FAIL"
        if result.returncode != expected:
            failures.append(f"{label}: expected {expected}, got {result.returncode}")
        print(f"[{status}] {label} (exit {result.returncode})")
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        if stdout.strip():
            print(f"  out: {stdout.strip().replace(chr(10), ' | ')[:400]}")
        if stderr.strip():
            print(f"  err: {stderr.strip().replace(chr(10), ' | ')[:200]}")
        return stdout.strip()

    print("=== 正常链路 ===")
    check("init", 0, "init")
    check("init 幂等", 0, "init")
    created = check(
        "works create",
        0,
        "works",
        "create",
        "雨夜侦探",
        "--genre",
        "悬疑",
        "--description",
        "侦探雨夜回乡查旧案",
    )
    workspace_id = created.split()[2].rstrip(":")
    check("works show", 0, "works", "show", workspace_id)
    check("agents show", 0, "agents", "show", workspace_id)
    check(
        "style set",
        0,
        "style",
        "set",
        workspace_id,
        "--description",
        "平实克制短句",
        "--forbidden",
        "璀璨,宛如",
    )
    check("memory pack", 0, "memory", "pack", workspace_id)
    check("talk send", 0, "talk", "send", workspace_id, "我们写一个雨夜故事")
    check("talk @写手 中文标点", 0, "talk", "send", workspace_id, "@写手，写一段雨夜开场")
    generated = check(
        "draft generate",
        0,
        "draft",
        "generate",
        workspace_id,
        "--title",
        "第一章 雨夜",
    )
    draft_id = generated.split()[1]
    check("quality check", 0, "quality", "check", draft_id)
    check(
        "review 责编退稿",
        0,
        "review",
        "add",
        draft_id,
        "--from",
        "责编",
        "--content",
        "退稿：开场钩子不成立",
    )
    check(
        "draft revise 反驳",
        0,
        "draft",
        "revise",
        draft_id,
        "--reason",
        "写手反驳：重写铺垫",
    )
    check("draft list", 0, "draft", "list", workspace_id)
    check("decision accept", 0, "decision", "accept", draft_id)
    check("draft show", 0, "draft", "show", draft_id)
    check("review list", 0, "review", "list", draft_id)
    check("decision list", 0, "decision", "list", draft_id)
    check("log", 0, "log", workspace_id)
    check("demo", 0, "demo")
    check("works list", 0, "works", "list")

    print("=== 边界与失败 ===")
    check("works show 不存在", 1, "works", "show", "nope")
    check("talk 未知别名", 2, "talk", "send", workspace_id, "@路人 你好")
    check("draft show 不存在", 1, "draft", "show", "nope")
    check("重复 accept", 2, "decision", "accept", draft_id)
    check("revise accepted", 2, "draft", "revise", draft_id)
    check("regenerate accepted", 2, "draft", "generate", workspace_id, "--title", "第一章 雨夜")
    check("无效阈值", 1, "health", extra_env={"NOVEL_QUALITY_THRESHOLD": "high"})

    print("=== 质量门拦截（阈值 -1 强制失败）===")
    blocked = check(
        "generate quality_failed",
        0,
        "draft",
        "generate",
        workspace_id,
        "--title",
        "第二章 追踪",
        extra_env={"NOVEL_QUALITY_THRESHOLD": "-1"},
    )
    blocked_draft = blocked.split()[1]
    check(
        "accept quality_failed 被拒",
        2,
        "decision",
        "accept",
        blocked_draft,
        extra_env={"NOVEL_QUALITY_THRESHOLD": "-1"},
    )

    print(f"\n临时数据目录: {tmp}")
    if failures:
        print(f"\n失败 {len(failures)} 项:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\n冒烟验证全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
