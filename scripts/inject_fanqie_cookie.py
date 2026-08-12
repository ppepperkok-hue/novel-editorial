"""Inject the saved Fanqie cookies into the debug Chrome via CDP."""

import json
import sys
import time
import urllib.request
import websocket  # websocket-client
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import config  # noqa: E402

CDP = "http://127.0.0.1:9222"


def load_env():
    """Shared env loader: ~/.n8n/.env filled in by config.load_env()."""
    return config.load_env()


def parse_cookie(header):
    pairs = []
    for part in header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        pairs.append((k.strip(), v.strip()))
    return pairs


def find_fanqie_tab():
    tabs = json.loads(urllib.request.urlopen(CDP + "/json/list", timeout=10).read())
    for t in tabs:
        if "fanqienovel.com" in t.get("url", ""):
            return t
    return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    env = load_env()
    cookie = env.get("FANQIE_COOKIE", "")
    if not cookie:
        print("no FANQIE_COOKIE in env")
        return
    tab = find_fanqie_tab()
    if tab is None:
        print("no fanqie tab found")
        return
    ws = websocket.create_connection(
        tab["webSocketDebuggerUrl"], timeout=20, suppress_origin=True
    )
    seq = {"n": 0}

    def cmd(method, params=None):
        seq["n"] += 1
        mid = seq["n"]
        ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == mid:
                return msg

    cmd("Network.enable")
    pairs = parse_cookie(cookie)
    ok = 0
    for k, v in pairs:
        r = cmd(
            "Network.setCookie",
            {
                "name": k,
                "value": v,
                "domain": ".fanqienovel.com",
                "path": "/",
                "url": "https://fanqienovel.com",
                "httpOnly": True,
                "secure": True,
            },
        )
        if r.get("result", {}).get("success"):
            ok += 1
    print(f"set {ok}/{len(pairs)} cookies")
    cmd("Page.reload", {"ignoreCache": True})
    time.sleep(3)
    ws.close()


if __name__ == "__main__":
    main()
