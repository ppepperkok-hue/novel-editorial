import http.cookiejar
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import config  # noqa: E402

BASE = (
    config.env_value("N8N_BASE", "http://127.0.0.1:5678") or "http://127.0.0.1:5678"
).rstrip("/")

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# Sessions expire server-side; re-login once the cached login is this old.
_LOGIN_TTL_SECONDS = 1800
_login_at = None


def _credentials():
    env = config.load_env()
    email = env.get("N8N_EMAIL", "")
    password = env.get("N8N_TMP_PW", "")
    missing = [k for k, v in (("N8N_EMAIL", email), ("N8N_TMP_PW", password)) if not v]
    if missing:
        raise RuntimeError(
            "n8n credentials missing (" + ", ".join(missing) + "): set them in "
            "~/.n8n/.env or the process environment"
        )
    return email, password


def _login():
    global _login_at
    email, password = _credentials()
    req = urllib.request.Request(
        BASE + "/rest/login",
        data=json.dumps({"emailOrLdapLoginId": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    r = opener.open(req, timeout=10)
    if not any(
        h.startswith("n8n-auth=")
        for h in (r.headers.get_all("Set-Cookie") or [])
    ):
        raise RuntimeError("no n8n-auth cookie")
    _login_at = time.monotonic()


def _ensure_session():
    """Log in unless the cached session is still within its TTL."""
    global _login_at
    if _login_at is None or time.monotonic() - _login_at >= _LOGIN_TTL_SECONDS:
        _login()


def _open(method, path, body):
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    r = opener.open(req, timeout=15)
    raw = r.read().decode()
    return r.status, (json.loads(raw) if raw else None)


def request(method, path, body=None):
    """Send one request through the CookieJar; on auth failure
    discard the stale session, re-login exactly once and retry."""
    _ensure_session()
    try:
        return _open(method, path, body)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            global _login_at
            _login_at = None
            cj.clear()
            try:
                _ensure_session()
                return _open(method, path, body)
            except urllib.error.HTTPError as retry_err:
                e = retry_err
        raw = e.read().decode()
        print("HTTP error body:", raw[:2000])
        raise


_USAGE = (
    "usage: python tools/n8n_api.py <list|delete|archive|create|update|run|exec> [args]\n"
    "  list                          list workflows\n"
    "  delete|archive <workflow-id>  delete or archive a workflow\n"
    "  create <payload-json-or-file> create a workflow\n"
    "  update <workflow-id> <payload-json-or-file>  update a workflow\n"
    "  run [workflow-id]             run a workflow (default N8N_WORKFLOW_DAILY)\n"
    "  exec <execution-id>           show execution status"
)


def _arg(index, label):
    """Return sys.argv[index] or print usage and exit 1 when missing."""
    if len(sys.argv) <= index:
        print(f"missing argument: {label}")
        print(_USAGE)
        sys.exit(1)
    return sys.argv[index]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(_USAGE)
        sys.exit(1)
    action = sys.argv[1]
    if action == "list":
        status, body = request("GET", "/rest/workflows")
        items = body["data"] if isinstance(body, dict) else body
        print("count:", len(items))
        for w in items:
            print("-", w["id"], w["name"], "active=", w["active"])
    elif action == "delete":
        wf_id = _arg(2, "workflow id")
        status, body = request("DELETE", "/rest/workflows/" + wf_id)
        print("delete status:", status, body)
    elif action == "archive":
        wf_id = _arg(2, "workflow id")
        status, body = request("POST", "/rest/workflows/" + wf_id + "/archive")
        print("archive status:", status, body)
    elif action == "create":
        raw = _arg(2, "payload JSON or file path")
        payload = json.loads(raw) if raw.lstrip().startswith("{") else json.load(open(raw, encoding="utf-8"))
        status, body = request("POST", "/rest/workflows", payload)
        print("create status:", status)
        print("id:", body["data"]["id"], "name:", body["data"]["name"])
        print("nodes:", [n["name"] for n in body["data"]["nodes"]])
    elif action == "update":
        wf_id = _arg(2, "workflow id")
        raw = _arg(3, "payload JSON or file path")
        payload = json.loads(raw) if raw.lstrip().startswith("{") else json.load(open(raw, encoding="utf-8"))
        status, body = request("PATCH", "/rest/workflows/" + wf_id, payload)
        print("update status:", status)
        if isinstance(body, dict) and "data" in body:
            print("id:", body["data"]["id"], "nodes:", [n["name"] for n in body["data"]["nodes"]])
        else:
            print("body:", body)
    elif action == "run":
        wf_id = (
            sys.argv[2]
            if len(sys.argv) > 2
            else config.env_value("N8N_WORKFLOW_DAILY", "")
        )
        if not wf_id:
            print("run requires a workflow id or N8N_WORKFLOW_DAILY in env")
            sys.exit(1)
        status, body = request("GET", "/rest/workflows/" + wf_id)
        wf = body["data"]
        trigger = (
            config.env_value("N8N_WORKFLOW_TRIGGER", "每日触发") or "每日触发"
        )
        run_payload = {"workflowData": wf, "triggerToStartFrom": {"name": trigger}}
        status, body = request("POST", "/rest/workflows/" + wf_id + "/run", run_payload)
        print("run status:", status, body)
    elif action == "exec":
        exec_id = _arg(2, "execution id")
        status, body = request("GET", "/rest/executions/" + exec_id)
        d = body["data"]
        print("status:", d.get("status"))
        print("finished:", d.get("finished"))
        print("stoppedAt:", d.get("stoppedAt"))
        raw_data = d.get("data")
        if isinstance(raw_data, str):
            raw_data = json.loads(raw_data)
        if isinstance(raw_data, list):
            raw_data = raw_data[0] if raw_data else {}
        rd = (raw_data or {}).get("resultData", {})
        last = rd.get("lastNodeExecuted")
        error = rd.get("error")
        print("lastNodeExecuted:", last)
        print("error:", json.dumps(error, ensure_ascii=False)[:1000] if error else None)
    else:
        print(f"unknown action: {action}")
        print(_USAGE)
        sys.exit(1)
