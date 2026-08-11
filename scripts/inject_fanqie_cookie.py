"""Inject the saved Fanqie cookies into the debug Chrome via CDP."""

import json
import re
import sys
import time
import urllib.request
import websocket  # websocket-client
from pathlib import Path

ENV_FILE = r"C:\Users\Administrator\.n8n\.env"
CDP = "http://127.0.0.1:9222"


def load_env():
    env = {}
    for line in Path(ENV_FILE).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*)$", line)
        if m:
            env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return env


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


def click_select(ws_url, x, y):
    import websocket as _ws  # noqa: PLC0415

    ws = _ws.create_connection(ws_url, timeout=20, suppress_origin=True)
    seq = {"n": 0}

    def cmd(method, params=None):
        seq["n"] += 1
        mid = seq["n"]
        ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == mid:
                return msg

    cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    ws.close()
    print(f"clicked at ({x},{y})")


if __name__ == "__main__":
    main()
