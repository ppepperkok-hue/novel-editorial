"""M5/N12 S4 end-to-end panel demo: seed -> serve -> assert -> cleanup.

The script is idempotent: every run uses a fresh temporary data directory and
a random free port, builds the frontend when the dist is missing, and tears
down the server and the directory on every exit path (including failures).

It exercises the same HTTP surface the panel consumes: /config, /overview,
/events, /works/{id}/pending, /works/{id}/drafts, /works/{id}/log and the
decision write, then checks the CLI sees the same new state.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = ROOT / "frontend" / "dist"

# The demo is meant to run with a plain `python scripts/panel_demo.py`, so it
# resolves the src-layout package itself instead of requiring an editable install.
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if callable(_reconfigure):
        _reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _http_json(
    url: str, *, method: str = "GET", body: dict | None = None
) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload


def _http_text(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"Accept": "text/plain"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read().decode("utf-8")


def _run_cli(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "novel-editorial", *args],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        check=False,
    )


def _seed() -> tuple[str, str]:
    """Insert one workspace and one pending draft directly via core functions."""
    from novel_editorial.core.config import load_settings
    from novel_editorial.core.workspace import create_workspace
    from novel_editorial.events import EventType
    from novel_editorial.store.db import DB
    from novel_editorial.store.events import record_event
    from novel_editorial.store.models import Draft, DraftVersion

    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    created = create_workspace(db, title="面板演示之书", genre="悬疑")
    workspace_id = created.id
    with db.workspace_session(workspace_id) as session:
        draft = Draft(
            workspace_id=workspace_id,
            title="第一章",
            status="draft",
            current_version=1,
        )
        session.add(draft)
        session.flush()
        session.add(
            DraftVersion(
                draft_id=draft.id,
                version=1,
                content="演示正文：雨夜开场，钩子埋下。",
                reason="initial",
            )
        )
        session.commit()
        draft_id = draft.id
    record_event(
        db,
        workspace_id,
        type=EventType.DECISION_REQUESTED,
        actor="system",
        payload={"draft_id": draft_id, "version": 1},
    )
    # Release SQLite file handles held by the seeding process; otherwise the
    # final cleanup cannot remove the temporary data directory on Windows.
    db.dispose()
    return workspace_id, draft_id


def _wait_health(
    base_url: str, server: subprocess.Popen[str], failures: list[str]
) -> bool:
    deadline = time.monotonic() + 60
    last_error = ""
    while time.monotonic() < deadline:
        if server.poll() is not None:
            output = server.stdout.read() if server.stdout else ""
            failures.append(
                f"server exited early (code {server.returncode}): {output[-2000:]}"
            )
            return False
        try:
            status, _ = _http_json(f"{base_url}/health")
            if status == 200:
                print("[OK] 服务就绪 /health")
                return True
        except Exception as exc:  # noqa: BLE001 - server may still be booting
            last_error = str(exc)
        time.sleep(0.5)
    failures.append(f"server not ready within 60s: {last_error}")
    return False


def _stop_server(server: subprocess.Popen[str]) -> None:
    if server.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(server.pid)],
                capture_output=True,
                check=False,
            )
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
        else:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
    except Exception:  # noqa: BLE001 - cleanup must not mask the demo result
        pass


def _remove_tree_with_retry(path: Path) -> bool:
    """Remove a directory tree, retrying until file handles are released."""
    for attempt in range(10):
        try:
            shutil.rmtree(path)
            return True
        except OSError as exc:
            if attempt == 9:
                print(f"  rmtree 最终失败: {exc}", file=sys.stderr)
                return False
            time.sleep(1.0)
    return False


def _ensure_project_env() -> None:
    """Re-run under the project environment when deps are missing.

    The acceptance command is `python scripts/panel_demo.py`, which may hit a
    bare interpreter without the project dependencies. In that case the script
    re-executes itself through `uv run python` so the demo stays reproducible.
    """
    try:
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401
        import uvicorn  # noqa: F401
    except ModuleNotFoundError:
        print("当前解释器缺少项目依赖，改用 uv run python 重跑 ...")
        result = subprocess.run(
            ["uv", "run", "python", str(Path(__file__).resolve())],
            cwd=str(ROOT),
        )
        raise SystemExit(result.returncode) from None


def main() -> int:
    _ensure_project_env()

    if not (FRONTEND_DIST / "index.html").is_file():
        print("frontend/dist 缺失，先执行 npm run build ...")
        subprocess.run(
            ["npm", "run", "build"],
            cwd=str(ROOT / "frontend"),
            check=True,
        )

    tmp = Path(tempfile.mkdtemp(prefix="panel-demo-"))
    for llm_key in ("NOVEL_LLM_API_KEY", "NOVEL_LLM_BASE_URL", "NOVEL_LLM_MODEL"):
        os.environ.pop(llm_key, None)
    os.environ["NOVEL_DATA_DIR"] = str(tmp / "data")
    os.environ["NOVEL_CONFIG"] = str(tmp / "config.toml")
    os.environ["NOVEL_FRONTEND_DIST"] = str(FRONTEND_DIST)

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    server: subprocess.Popen[str] | None = None
    failures: list[str] = []
    cleanup_ok = True

    try:
        workspace_id, draft_id = _seed()
        print(f"作品: {workspace_id}  草稿: {draft_id}")

        server = subprocess.Popen(
            [
                "uv",
                "run",
                "uvicorn",
                "novel_editorial.api.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=str(ROOT),
            env=dict(os.environ),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )

        def check(label: str, ok: bool, detail: str = "") -> bool:
            status = "OK" if ok else "FAIL"
            if not ok:
                failures.append(f"{label}: {detail}")
            print(f"[{status}] {label}")
            if detail:
                print(f"  {detail}")
            return ok

        if not _wait_health(base_url, server, failures):
            raise SystemExit(1)

        status, config = _http_json(f"{base_url}/config")
        check(
            "GET /config",
            status == 200 and config.get("panel_poll_interval") == 3,
            f"status={status} body={config}",
        )

        status, overview = _http_json(f"{base_url}/overview")
        check(
            "GET /overview",
            status == 200
            and overview.get("total") == 1
            and overview["overviews"][0]["pending_count"] == 1,
            f"status={status} body={overview}",
        )

        status, events = _http_json(f"{base_url}/events")
        has_decision = any(
            event.get("type") == "decision.requested"
            and event.get("payload", {}).get("draft_id") == draft_id
            for event in events.get("events", [])
        )
        check(
            "GET /events",
            status == 200 and has_decision,
            f"status={status} events={len(events.get('events', []))}",
        )

        status, pending = _http_json(f"{base_url}/works/{workspace_id}/pending")
        check(
            "GET /works/{id}/pending",
            status == 200
            and any(item.get("id") == draft_id for item in pending),
            f"status={status} body={pending}",
        )

        status, drafts = _http_json(f"{base_url}/works/{workspace_id}/drafts")
        check(
            "GET /works/{id}/drafts",
            status == 200
            and any(item.get("id") == draft_id for item in drafts),
            f"status={status} body={drafts}",
        )

        status, log_text = _http_text(f"{base_url}/works/{workspace_id}/log")
        check(
            "GET /works/{id}/log",
            status == 200
            and "第一章" in log_text
            and "演示正文：雨夜开场" in log_text,
            f"status={status}",
        )

        with urllib.request.urlopen(f"{base_url}/", timeout=10) as response:
            status = response.status
            index_body = response.read().decode("utf-8")
        check(
            "GET / (frontend dist)",
            status == 200 and "Novel Editorial" in index_body,
        )

        cli_before = _run_cli(
            dict(os.environ), "decision", "pending", workspace_id
        )
        check(
            "CLI decision pending（accept 前）",
            cli_before.returncode == 0 and draft_id in cli_before.stdout,
            f"exit={cli_before.returncode} out={cli_before.stdout.strip()[:200]}",
        )

        status, decided = _http_json(
            f"{base_url}/works/{workspace_id}/decisions",
            method="POST",
            body={"draft_id": draft_id, "action": "accept"},
        )
        check(
            "POST /works/{id}/decisions (accept)",
            status == 201 and decided == {"id": draft_id, "status": "accepted"},
            f"status={status} body={decided}",
        )

        status, pending_after = _http_json(
            f"{base_url}/works/{workspace_id}/pending"
        )
        check(
            "GET /works/{id}/pending（accept 后为空）",
            status == 200 and pending_after == [],
            f"status={status} body={pending_after}",
        )

        cli_after = _run_cli(dict(os.environ), "decision", "pending", workspace_id)
        check(
            "CLI decision pending（accept 后空态）",
            cli_after.returncode == 0
            and "no pending decisions" in cli_after.stdout
            and draft_id not in cli_after.stdout,
            f"exit={cli_after.returncode} out={cli_after.stdout.strip()[:200]}",
        )
    finally:
        if server is not None:
            _stop_server(server)
        cleanup_ok = _remove_tree_with_retry(tmp)

    if not cleanup_ok:
        failures.append(f"临时目录清理失败: {tmp}")

    if failures:
        print(f"\n失败 {len(failures)} 项:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nPANEL DEMO PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
