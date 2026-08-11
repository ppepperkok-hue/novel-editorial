import http.cookiejar
import json
import sys
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

_token_cache = None


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


def auth_token():
    global _token_cache
    if _token_cache is not None:
        return _token_cache
    email, password = _credentials()
    req = urllib.request.Request(
        BASE + "/rest/login",
        data=json.dumps({"emailOrLdapLoginId": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    r = opener.open(req, timeout=10)
    for h in (r.headers.get_all("Set-Cookie") or []):
        if h.startswith("n8n-auth="):
            _token_cache = h.split(";", 1)[0].split("=", 1)[1]
            return _token_cache
    raise RuntimeError("no n8n-auth cookie")


def _open(method, path, body, token):
    headers = {"Cookie": "n8n-auth=" + token}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    r = opener.open(req, timeout=15)
    raw = r.read().decode()
    return r.status, (json.loads(raw) if raw else None)


def request(method, path, body=None):
    """Send one request, reusing the session token; on auth failure
    re-login exactly once and retry."""
    try:
        return _open(method, path, body, auth_token())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            global _token_cache
            _token_cache = None
            cj.clear()
            try:
                return _open(method, path, body, auth_token())
            except urllib.error.HTTPError as retry_err:
                e = retry_err
        raw = e.read().decode()
        print("HTTP error body:", raw[:2000])
        raise


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "list":
        status, body = request("GET", "/rest/workflows")
        items = body["data"] if isinstance(body, dict) else body
        print("count:", len(items))
        for w in items:
            print("-", w["id"], w["name"], "active=", w["active"])
    elif action == "delete":
        wf_id = sys.argv[2]
        status, body = request("DELETE", "/rest/workflows/" + wf_id)
        print("delete status:", status, body)
    elif action == "archive":
        wf_id = sys.argv[2]
        status, body = request("POST", "/rest/workflows/" + wf_id + "/archive")
        print("archive status:", status, body)
    elif action == "create":
        raw = sys.argv[2]
        payload = json.loads(raw) if raw.lstrip().startswith("{") else json.load(open(raw, encoding="utf-8"))
        status, body = request("POST", "/rest/workflows", payload)
        print("create status:", status)
        print("id:", body["data"]["id"], "name:", body["data"]["name"])
        print("nodes:", [n["name"] for n in body["data"]["nodes"]])
    elif action == "update":
        wf_id = sys.argv[2]
        raw = sys.argv[3]
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
        exec_id = sys.argv[2]
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
