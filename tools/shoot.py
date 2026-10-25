#!/usr/bin/env python3
"""Render an OpenUI Lang file exactly as the plugin would, and save a PNG screenshot of it. Pure standard library + a local Chrome.

usage: python3 tools/shoot.py EXAMPLE.oui OUT.png [--theme dark|light] [--width 640] [--scale 2] [--chrome PATH] [--keep-html]

It builds the real widget page with the plugin's own page builder (the same bytes render_widget writes), wraps it in the app's theme
tokens, loads it in headless Chrome over the DevTools protocol, waits for the runtime to settle, measures the real content height, and
captures the screenshot at that height. (One-shot `chrome --headless --screenshot` was tried first and hangs on some macOS setups;
driving Chrome over its debugging port does not.) Chrome is found via --chrome, $CHROME, the Chrome for Testing bundled with Hermes,
Google Chrome, or chromium on PATH.
"""
from __future__ import annotations

import argparse
import base64
import glob
import importlib
import importlib.util
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAD = 16  # px of breathing room around the widget in the image

THEMES = {
    "dark": "--foreground:#e8eaed;--muted-foreground:#9aa0a6;--accent:#5B9CF6;--border:rgba(255,255,255,.16);--card:#202124;color-scheme:dark;--bg:#17181a",
    "light": "--foreground:#1f2328;--muted-foreground:#59636e;--accent:#0969da;--border:rgba(31,35,40,.16);--card:#f6f8fa;color-scheme:light;--bg:#ffffff",
}
MEASURE = (
    "<script>(function(){var last=Date.now();var r=document.getElementById('root');"
    "new MutationObserver(function(){last=Date.now()}).observe(r,{childList:true,subtree:true,attributes:true,characterData:true});"
    "var iv=setInterval(function(){if(r.children.length&&Date.now()-last>800){clearInterval(iv);"
    "window.__ouiHeight=Math.ceil(document.body.getBoundingClientRect().height)}},100)})()</script>"
)


class WS:
    """Just enough RFC 6455 for the DevTools protocol: text frames in both directions, ping/pong, fragmented messages."""

    def __init__(self, url: str):
        assert url.startswith("ws://")
        hostport, _, path = url[5:].partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(("GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key)).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("websocket handshake failed")
            buf += chunk
        if b" 101 " not in buf.split(b"\r\n", 1)[0]:
            raise ConnectionError("websocket upgrade refused: %r" % buf[:80])
        self.rest = buf.split(b"\r\n\r\n", 1)[1]
        self.next_id = 0

    def _read(self, n: int) -> bytes:
        while len(self.rest) < n:
            chunk = self.sock.recv(max(65536, n - len(self.rest)))
            if not chunk:
                raise ConnectionError("websocket closed")
            self.rest += chunk
        out, self.rest = self.rest[:n], self.rest[n:]
        return out

    def _frame(self, opcode: int, payload: bytes) -> None:
        head = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def recv(self) -> dict:
        data = b""
        while True:
            b1, b2 = self._read(2)
            fin, opcode, n = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if opcode == 0x9:
                self._frame(0xA, payload)
            elif opcode == 0x8:
                raise ConnectionError("websocket closed by Chrome")
            elif opcode in (0x0, 0x1, 0x2):
                data += payload
                if fin:
                    return json.loads(data.decode("utf-8"))

    def call(self, method: str, **params):
        self.next_id += 1
        mid = self.next_id
        self._frame(0x1, json.dumps({"id": mid, "method": method, "params": params}).encode())
        while True:
            msg = self.recv()
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError("%s: %s" % (method, msg["error"]))
                return msg.get("result", {})

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def find_chrome(explicit):
    cands = [explicit, os.environ.get("CHROME")]
    cands += glob.glob(os.path.expanduser("~/.hermes/tools/chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"))
    cands += glob.glob(os.path.expanduser("~/.hermes/tools/chromium-*/chrome-linux*/chrome"))
    cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser")]
    for c in cands:
        if c and Path(c).exists():
            return c
    sys.exit("No Chrome found. Pass --chrome PATH or set $CHROME.")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def load_modules():
    spec = importlib.util.spec_from_file_location("hermes_openui", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_openui"] = mod
    spec.loader.exec_module(mod)
    return [importlib.import_module("hermes_openui." + n) for n in ("page", "lint", "bundle")]


def png_size(path: Path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24]) if head[:8] == b"\x89PNG\r\n\x1a\n" else (0, 0)


def docs_source(text: str) -> str:
    """Docs examples are written with a neutral placeholder path (`"/path/to/sample.png"`) so the source reads naturally on a page;
    when rendering, point it at the sample image shipped with the docs."""
    return text.replace('"/path/to/', '"%s/' % (ROOT / "docs" / "ui-components" / "examples" / "assets"))


def shoot(example: Path, out: Path, theme: str = "dark", width: int = 640, scale: int = 2, chrome: str = None, keep_html: bool = False) -> str:
    page, lint, bundle = load_modules()
    source = lint.strip_fences(docs_source(example.read_text(encoding="utf-8")))
    problems = lint.check(source, bundle.component_names())
    if problems:
        raise SystemExit("%s has problems:\n  - %s" % (example, "\n  - ".join(problems)))
    html, packs = page.build_page(page.inline_images(source), title=example.stem)
    prelude = (
        "<style>:root{%s}html,body{margin:0;background:var(--bg);color:var(--foreground);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif}"
        "body{padding:%dpx !important}#root{width:%dpx;max-width:100%%}</style>" % (THEMES[theme], PAD, width)
    )
    html = html.replace("</head>", prelude + "</head>", 1).replace("</body>", MEASURE + "</body>", 1)

    out.parent.mkdir(parents=True, exist_ok=True)
    win = width + 2 * PAD
    port = free_port()
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "widget.html"
        f.write_text(html, encoding="utf-8")
        cmd = [find_chrome(chrome), "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run", "--no-default-browser-check", "--use-mock-keychain",
               "--password-store=basic", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--hide-scrollbars",
               "--remote-debugging-port=%d" % port, "--user-data-dir=%s" % (Path(td) / "profile"), "about:blank"]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws = None
        try:
            ws_url = None
            for _ in range(100):
                try:
                    targets = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port, timeout=2))
                    ws_url = next(t["webSocketDebuggerUrl"] for t in targets if t["type"] == "page")
                    break
                except Exception:
                    time.sleep(0.2)
            if not ws_url:
                raise SystemExit("Chrome did not open a debugging port")
            ws = WS(ws_url)
            ws.call("Page.enable")
            ws.call("Emulation.setDeviceMetricsOverride", width=win, height=1400, deviceScaleFactor=scale, mobile=False)
            ws.call("Page.navigate", url=f.as_uri())
            height = None
            for _ in range(200):
                r = ws.call("Runtime.evaluate", expression="window.__ouiHeight||0", returnByValue=True)["result"].get("value", 0)
                if r:
                    height = int(r)
                    break
                time.sleep(0.15)
            if not height:
                err = ws.call("Runtime.evaluate", expression="(document.getElementById('oui-err')||{}).textContent||''", returnByValue=True)["result"].get("value", "")
                raise SystemExit("widget did not render%s" % (": " + err if err else " (no height reported after 30 s)"))
            ws.call("Emulation.setDeviceMetricsOverride", width=win, height=height, deviceScaleFactor=scale, mobile=False)
            time.sleep(0.5)
            shot = ws.call("Page.captureScreenshot", format="png", fromSurface=True)
            out.write_bytes(base64.b64decode(shot["data"]))
            if keep_html:
                shutil.copy(f, out.with_suffix(".html"))
        finally:
            if ws:
                ws.close()
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
    w, h = png_size(out)
    if w == 0:
        raise SystemExit("screenshot was not written")
    return "%s: %dx%d px (css %dx%d, %s theme, packs: %s)" % (out.name, w, h, win, height, theme, ", ".join(packs) or "none")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("example")
    ap.add_argument("out")
    ap.add_argument("--theme", choices=sorted(THEMES), default="dark")
    ap.add_argument("--width", type=int, default=640, help="widget column width in CSS px (the chat column is 640)")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--chrome")
    ap.add_argument("--keep-html", action="store_true", help="also save OUT.html: a live, self-contained copy of the widget")
    a = ap.parse_args()
    print(shoot(Path(a.example), Path(a.out).resolve(), a.theme, a.width, a.scale, a.chrome, a.keep_html))


if __name__ == "__main__":
    main()
