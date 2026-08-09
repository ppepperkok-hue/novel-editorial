import json
import os
import sys
import urllib.request

sys.path.insert(0, r"C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2\work")
import n8n_api  # noqa: E402

WF_ID = os.environ["WF_ID"]
try:
    status, body = n8n_api.request("GET", "/rest/workflows/" + WF_ID)
    print("status:", status)
    print("keys:", list(body.keys()) if isinstance(body, dict) else type(body))
    if isinstance(body, dict):
        wf = body.get("data", body)
        nodes = wf.get("nodes", [])
        print("node count:", len(nodes))
        print("node names:", [n.get("name") for n in nodes])
        print("active:", wf.get("active"))
except Exception as e:
    print("error:", e)
    if hasattr(e, "read"):
        print("body:", e.read().decode()[:2000])
    raise
