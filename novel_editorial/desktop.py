"""DEPRECATED Desktop control panel (pywebview) for the novel pipeline.

当前无调用方，保留为回退后备；现役桌面壳为 Electron（desktop/）。

Uses a normal system-framed window (stable drag/resize/close) with a
dark title bar via the Windows DWM immersive-dark-mode attribute, so the
panel never flashes a white frame.

Run: python -m novel_editorial.desktop
"""

import argparse
import ctypes
import socket
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial.web_api import make_handler  # noqa: E402

# DWMWA_USE_IMMERSIVE_DARK_MODE: 20 on Win10 2004+/Win11, 19 on older builds
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_dwmapi = ctypes.windll.dwmapi


def log(*args):
    if sys.stdout:
        print(*args)


def pick_port(preferred):
    for port in (preferred, preferred + 10, preferred + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred + 100


def _dark_titlebar(handle):
    """Dark title bar + border + caption text (Win11 22H2+ supports attrs 34-36)."""
    h = ctypes.c_void_p(int(handle))
    enabled = ctypes.c_int(1)
    for attr in (20, 19):  # immersive dark mode
        try:
            _dwmapi.DwmSetWindowAttribute(
                h,
                attr,
                ctypes.byref(enabled),
                ctypes.sizeof(enabled),
            )
        except (OSError, AttributeError):
            pass
    bg = ctypes.c_int(0x001A1A1A)  # COLORREF RGB(26,26,26)
    fg = ctypes.c_int(0x00EDEAE8)  # COLORREF RGB(232,234,237)
    for attr, val in ((34, bg), (35, bg), (36, fg)):
        try:
            _dwmapi.DwmSetWindowAttribute(
                h, attr, ctypes.byref(val), ctypes.sizeof(val)
            )
        except (OSError, AttributeError):
            pass


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
    log(f"控制台服务 http://127.0.0.1:{port}/")

    import webview  # imported lazily so headless/CLI use does not require it

    window = webview.create_window(
        "小说流水线控制台",
        f"http://127.0.0.1:{port}/",
        width=1280,
        height=880,
        min_size=(1024, 700),
    )

    def _on_ready():
        # Runs on the UI thread: WinForms handle access is only valid here.
        try:
            native = window.native
            if native is not None and native.Handle:
                _dark_titlebar(native.Handle)
        except Exception:  # noqa: BLE001
            pass
        if args.smoke:
            time.sleep(3)
            window.destroy()
            server.shutdown()

    webview.start(_on_ready, debug=False)
    if args.smoke:
        log("smoke ok")


if __name__ == "__main__":
    main()
