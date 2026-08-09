"""Desktop control panel (pywebview) for the novel pipeline.

Starts the monitoring API on 127.0.0.1 and opens a native window.
Run: python -m novel_pipeline.desktop
"""

import argparse
import socket
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline.web_api import make_handler  # noqa: E402


def pick_port(preferred):
    for port in (preferred, preferred + 10, preferred + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred + 100


def main():
    ap = argparse.ArgumentParser(description="小说流水线桌面控制台")
    ap.add_argument("--db", default=str(ROOT / "demo.db"))
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--smoke", action="store_true", help="启动 3 秒后自动关闭（自检用）")
    args = ap.parse_args()

    port = pick_port(args.port)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(args.db))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"控制台服务 http://127.0.0.1:{port}/")

    import webview  # imported lazily so headless/CLI use does not require it

    window = webview.create_window(
        "小说流水线控制台",
        f"http://127.0.0.1:{port}/",
        width=1280,
        height=880,
        min_size=(1024, 700),
    )

    def _smoke_close():
        import time

        time.sleep(3)
        window.destroy()
        server.shutdown()

    webview.start(_smoke_close if args.smoke else None, debug=False)
    if args.smoke:
        print("smoke ok")


if __name__ == "__main__":
    main()
