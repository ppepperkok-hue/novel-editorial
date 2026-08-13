"""Phase 2 verification smoke: run the full M3 visibility loop via the real CLI."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if callable(_reconfigure):
        _reconfigure(encoding="utf-8", errors="replace")


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
    tmp = Path(tempfile.mkdtemp(prefix="m3-smoke-"))
    env = dict(os.environ)
    for llm_key in ("NOVEL_LLM_API_KEY", "NOVEL_LLM_BASE_URL", "NOVEL_LLM_MODEL"):
        env.pop(llm_key, None)
    env["NOVEL_DATA_DIR"] = str(tmp / "data")
    env["NOVEL_CONFIG"] = str(tmp / "config.toml")
    failures: list[str] = []

    def check(
        label: str,
        expected: int,
        *args: str,
        expect: str | tuple[str, ...] | None = None,
        extra_env: dict | None = None,
    ) -> str:
        run_env = dict(env)
        if extra_env:
            run_env.update(extra_env)
        result = run_cli(run_env, *args)
        stdout = result.stdout or ""
        status = "OK" if result.returncode == expected else "FAIL"
        if result.returncode != expected:
            failures.append(f"{label}: expected exit {expected}, got {result.returncode}")
        if expect is not None:
            for needle in (expect,) if isinstance(expect, str) else expect:
                if needle not in stdout:
                    status = "FAIL"
                    failures.append(f"{label}: output missing {needle!r}")
        print(f"[{status}] {label} (exit {result.returncode})")
        if stdout.strip():
            print(f"  out: {stdout.strip().replace(chr(10), ' | ')[:400]}")
        stderr = result.stderr or ""
        if stderr.strip():
            print(f"  err: {stderr.strip().replace(chr(10), ' | ')[:200]}")
        return stdout.strip()

    print("=== M3 可见性与协作闭环 ===")
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
    check("talk send", 0, "talk", "send", workspace_id, "我们写一个雨夜故事")
    check("talk @写手 路由", 0, "talk", "send", workspace_id, "@写手，写一段雨夜开场")
    check("memory pack", 0, "memory", "pack", workspace_id)
    generated = check(
        "draft generate 质量门通过",
        0,
        "draft",
        "generate",
        workspace_id,
        "--title",
        "第一章",
        expect="awaiting decision",
    )
    draft_id = generated.split()[1]
    check(
        "events list 事件流",
        0,
        "events",
        "list",
        workspace_id,
        expect=("quality_gate.passed", "decision.requested"),
    )
    check(
        "inspect 穿透查询",
        0,
        "inspect",
        workspace_id,
        "雨夜",
        expect=("[档案]", "[对话]", "来源"),
    )
    check(
        "review add 责编退稿",
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
        "draft revise 仍待拍板",
        0,
        "draft",
        "revise",
        draft_id,
        "--reason",
        "写手反驳：重写铺垫",
        expect="awaiting decision",
    )
    check("decision pending 列出草稿", 0, "decision", "pending", workspace_id, expect=draft_id)
    check("decision accept", 0, "decision", "accept", draft_id, expect="accepted")
    check(
        "decision pending 空态",
        0,
        "decision",
        "pending",
        workspace_id,
        expect="no pending decisions",
    )
    check("demo", 0, "demo")

    print(f"\n临时数据目录: {tmp}")
    if failures:
        print(f"\n失败 {len(failures)} 项:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
