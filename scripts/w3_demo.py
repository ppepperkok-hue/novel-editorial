"""W3 HTTP end-to-end demo: quality/style tools + freewill visibility chain.

The script is idempotent: every run builds a fresh temporary data directory
and drives ``create_app()`` through ``fastapi.testclient.TestClient``, without
starting a port or depending on pre-seeded data. A failing step prints
``DEMO FAILED`` and exits non-zero immediately.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The demo is meant to run with `uv run python scripts/w3_demo.py`; the
# src-layout package stays importable under a plain interpreter as well.
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if callable(_reconfigure):
        _reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def _ensure_project_env() -> None:
    """Re-run under the project environment when dependencies are missing."""
    try:
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401
    except ModuleNotFoundError:
        print("当前解释器缺少项目依赖，改用 uv run python 重跑 ...")
        result = subprocess.run(
            ["uv", "run", "python", str(Path(__file__).resolve())],
            cwd=str(ROOT),
        )
        raise SystemExit(result.returncode) from None


def _prepare_env(tmp: Path) -> None:
    """Point config at the temporary directory and force the mock LLM mode.

    Drop every caller-supplied ``NOVEL_*`` variable first so each run starts
    from a fresh, self-contained environment.
    """
    for key in list(os.environ):
        if key.startswith("NOVEL_"):
            os.environ.pop(key, None)
    os.environ["NOVEL_DATA_DIR"] = str(tmp / "data")
    os.environ["NOVEL_CONFIG"] = str(tmp / "config.toml")


def main() -> int:
    _ensure_project_env()

    from fastapi.testclient import TestClient

    from novel_editorial.api.app import create_app
    from novel_editorial.core.config import load_settings
    from novel_editorial.core.motives import list_motives
    from novel_editorial.store.db import DB

    tmp = Path(tempfile.mkdtemp(prefix="w3-demo-"))
    _prepare_env(tmp)

    def require(label: str, ok: bool, detail: str = "") -> None:
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {label}")
        if detail:
            print(f"  {detail}")
        if not ok:
            print("\nDEMO FAILED")
            raise SystemExit(1)

    print("=== W3 HTTP 端到端演示（mock LLM）===")
    print(f"临时数据目录: {tmp}")

    style_corpus = tmp / "style_corpus.txt"
    style_corpus.write_text(
        "雨夜的旧车站，铁轨在灯光下泛着水光。广播声断断续续，像在说最后的话。"
        "她站在月台上，行李箱轮子碾过积水。\n\n"
        "风从站台尽头灌进来，带着铁锈和雨水的气味。灯管忽明忽暗，把影子拉得很长。"
        "她数着墙上的裂缝，等着末班车开走。\n\n"
        "天亮之前，她决定不再回头。钥匙在口袋里硌着手心，那是回城的唯一凭证。"
        "汽笛声起，站台渐渐安静下来。\n",
        encoding="utf-8",
    )
    calibration_corpus = tmp / "calibration_corpus.txt"
    calibration_corpus.write_text(
        "她深刻地意识到，仿佛整个世界都在刹那间被彻底改变，令人感到无比震撼。\n\n"
        "雨夜，旧车站的灯忽明忽暗，广播声在空站台里回响。\n\n"
        "她攥紧口袋里的钥匙，没有回头。风从站台尽头灌进来，带着铁锈和雨水的气味。\n",
        encoding="utf-8",
    )
    feedback_path = tmp / "feedback.jsonl"
    feedback_path.write_text(
        '{"label":"bad","text":"她深刻地意识到，仿佛整个世界都在刹那间被彻底改变了，'
        '不禁让人感到无比震撼。"}\n'
        '{"label":"good","text":"雨夜，她推开旧车站的木门，广播声在空站台里回响。"}\n',
        encoding="utf-8",
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/works",
            json={
                "title": "W3 演示之书",
                "genre": "悬疑",
                "description": "质量风格工具 + 自由意志可见全链路",
            },
        )
        created = response.json()
        require(
            "POST /works 建作品 (status 201)",
            response.status_code == 201 and bool(created.get("id")),
            f"status={response.status_code} body={response.text}",
        )
        workspace_id = created["id"]

        style_description = "冷峻，克制，短句，雨夜意象"
        style_forbidden = "突然，宛如"
        response = client.post(
            f"/works/{workspace_id}/style",
            json={"description": style_description, "forbidden": style_forbidden},
        )
        anchor = response.json()
        require(
            "POST /works/{id}/style 设风格锚点 (status 200)",
            response.status_code == 200
            and anchor.get("description") == style_description
            and anchor.get("forbidden_words") == style_forbidden,
            f"status={response.status_code} body={response.text}",
        )
        response = client.get(f"/works/{workspace_id}/style")
        anchor_read = response.json()
        require(
            "GET /works/{id}/style 回读一致 (status 200)",
            response.status_code == 200
            and anchor_read.get("description") == style_description
            and anchor_read.get("forbidden_words") == style_forbidden,
            f"status={response.status_code} body={response.text}",
        )

        response = client.post(
            f"/works/{workspace_id}/drafts/new",
            json={"title": "第一章"},
        )
        draft_new = response.json()
        require(
            "POST /works/{id}/drafts/new 作者空稿 (status 201)",
            response.status_code == 201
            and draft_new.get("status") == "draft"
            and draft_new.get("current_version") == 0,
            f"status={response.status_code} body={response.text}",
        )
        draft_id = draft_new["id"]

        content = (
            "雨夜，她推开旧车站的木门，广播声在空站台里回响。"
            "灯忽明忽暗，影子贴着墙游走。"
            "她攥紧口袋里的钥匙，没有回头。"
        )
        response = client.put(
            f"/works/{workspace_id}/drafts/{draft_id}/content",
            json={"content": content, "reason": "作者初稿"},
        )
        saved = response.json()
        require(
            "PUT /works/{id}/drafts/{id}/content 保存正文 (status 200)",
            response.status_code == 200
            and saved.get("status") == "draft"
            and saved.get("current_version") == 1,
            f"status={response.status_code} body={response.text}",
        )

        response = client.get(
            f"/works/{workspace_id}/drafts/{draft_id}/quality/check"
        )
        require(
            "GET .../quality/check 质量报告 (status 200)",
            response.status_code == 200 and "score:" in response.text,
            f"status={response.status_code} body={response.text}",
        )
        response = client.get(
            f"/works/{workspace_id}/drafts/{draft_id}/quality/explain"
        )
        require(
            "GET .../quality/explain AI 味定位 (status 200)",
            response.status_code == 200 and bool(response.text),
            f"status={response.status_code} body={response.text}",
        )
        response = client.get(
            f"/works/{workspace_id}/drafts/{draft_id}/consistency"
        )
        require(
            "GET .../consistency 一致性核查 (status 200)",
            response.status_code == 200 and bool(response.text),
            f"status={response.status_code} body={response.text}",
        )

        response = client.post(
            f"/works/{workspace_id}/style/learn",
            json={"path": str(style_corpus), "apply": False},
        )
        require(
            "POST /works/{id}/style/learn 风格学习 (status 200)",
            response.status_code == 200
            and "suggested description:" in response.text,
            f"status={response.status_code} body={response.text}",
        )
        response = client.get(f"/works/{workspace_id}/style/drift")
        require(
            "GET /works/{id}/style/drift 漂移检测 (status 200)",
            response.status_code == 200 and "drift" in response.text,
            f"status={response.status_code} body={response.text}",
        )

        response = client.post(
            "/quality/calibrate",
            json={"path": str(calibration_corpus), "apply": False},
        )
        require(
            "POST /quality/calibrate 阈值报告 (status 200)",
            response.status_code == 200
            and "suggested threshold:" in response.text
            and "distribution:" in response.text,
            f"status={response.status_code} body={response.text}",
        )
        response = client.post(
            "/quality/feedback",
            json={"path": str(feedback_path), "apply": False},
        )
        require(
            "POST /quality/feedback 试读反馈 (status 200)",
            response.status_code == 200 and "samples:" in response.text,
            f"status={response.status_code} body={response.text}",
        )

        response = client.get(f"/works/{workspace_id}/motives")
        require(
            "GET /works/{id}/motives 动机读面 (status 200)",
            response.status_code == 200
            and ("no motives" in response.text or bool(response.text.strip())),
            f"status={response.status_code} body={response.text}",
        )

        db = DB(load_settings())
        motives = list_motives(db, workspace_id)
        if not motives:
            print("  （本链路未产生真实动机，跳过 DELETE 动机演示）")
        else:
            response = client.delete(
                f"/works/{workspace_id}/motives/{motives[0].id}"
            )
            require(
                "DELETE /works/{id}/motives/{id} 放下动机 (status 200)",
                response.status_code == 200 and "dropped motive" in response.text,
                f"status={response.status_code} body={response.text}",
            )
            response = client.get(f"/works/{workspace_id}/behavior/timeline")
            require(
                "GET .../behavior/timeline 含 author_feedback:drop (status 200)",
                response.status_code == 200
                and "author_feedback:drop" in response.text,
                f"status={response.status_code} body={response.text}",
            )

        response = client.get(f"/works/{workspace_id}/patience")
        require(
            "GET /works/{id}/patience 耐心池 (status 200)",
            response.status_code == 200 and bool(response.text.strip()),
            f"status={response.status_code} body={response.text}",
        )
        response = client.get(f"/works/{workspace_id}/behavior/timeline")
        require(
            "GET /works/{id}/behavior/timeline 行为时间线 (status 200)",
            response.status_code == 200 and bool(response.text.strip()),
            f"status={response.status_code} body={response.text}",
        )
        response = client.get(f"/works/{workspace_id}/behavior")
        require(
            "GET /works/{id}/behavior 行为状态 (status 200)",
            response.status_code == 200 and bool(response.text.strip()),
            f"status={response.status_code} body={response.text}",
        )

    print("\nDEMO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
