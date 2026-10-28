#!/usr/bin/env python3
"""Render an OpenUI Lang file exactly as the plugin would, and save a PNG screenshot of it. Pure standard library + a local Chrome.

usage: python3 tools/shoot.py EXAMPLE.oui OUT.png [--theme dark|light] [--width 640] [--scale 2] [--chrome PATH] [--keep-html]
       python3 tools/shoot.py --html FILE.html OUT.png [--theme light|dark|auto] [--width 1100] [--scale 2] [--eval JS] [--before JS]

It builds the real widget page with the plugin's own page builder (the same bytes render_widget writes), wraps it in the app's theme
tokens, loads it in headless Chrome over the DevTools protocol, waits for the runtime to settle, measures the real content height, and
captures the screenshot at that height. (One-shot `chrome --headless --screenshot` was tried first and hangs on some macOS setups;
driving Chrome over its debugging port does not.) Chrome is found via --chrome, $CHROME, the Chrome for Testing bundled with Hermes,
Google Chrome, or chromium on PATH.

--html FILE screenshots an existing page instead (for example a report written by export_widgets): FILE is loaded from file://, nothing
is wrapped or rebuilt, and the whole page height is captured. --theme light|dark forces prefers-color-scheme through DevTools
(Emulation.setEmulatedMedia), auto leaves Chrome's default (light). It also prints how many console errors, failed requests and
requests outside file:/data: the page made, which is how to prove a page really works offline. --eval JS prints a JSON value
computed in the finished page (e.g. --eval 'document.querySelectorAll(".mount").length'); --before JS runs first, before the screenshot
(e.g. --before 'document.querySelector("button").click()' to capture what a click shows).
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
        self.events = []  # protocol events (console, network, ...) seen while waiting for a reply

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
            if "method" in msg:
                self.events.append(msg)

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
    return [importlib.import_module("hermes_openui." + n) for n in ("page", "lint", "bundle", "packs")]


def open_chrome(chrome, td):
    """Start headless Chrome with a throwaway profile inside `td` and connect to its first page over DevTools: (process, WS)."""
    port = free_port()
    cmd = [find_chrome(chrome), "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run", "--no-default-browser-check", "--use-mock-keychain",
           "--password-store=basic", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--hide-scrollbars",
           "--remote-debugging-port=%d" % port, "--user-data-dir=%s" % (Path(td) / "profile"), "about:blank"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        return proc, WS(ws_url)
    except BaseException:
        close_chrome(proc, None)
        raise


def close_chrome(proc, ws) -> None:
    if ws:
        ws.close()
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


def png_size(path: Path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24]) if head[:8] == b"\x89PNG\r\n\x1a\n" else (0, 0)


def docs_source(text: str) -> str:
    """Docs examples are written with a neutral placeholder path (`"/path/to/sample.png"`) so the source reads naturally on a page;
    when rendering, point it at the sample image shipped with the docs."""
    return text.replace('"/path/to/', '"%s/' % (ROOT / "docs" / "ui-components" / "examples" / "assets"))


def shoot(example: Path, out: Path, theme: str = "dark", width: int = 640, scale: int = 2, chrome: str = None, keep_html: bool = False, pack_files=None) -> str:
    page, lint, bundle, packs = load_modules()
    custom, pack_problems = packs.load([str(p) for p in (pack_files or [])], bundle.component_names())
    if pack_problems:
        raise SystemExit("pack problems:\n  - " + "\n  - ".join(pack_problems))
    source = lint.strip_fences(docs_source(example.read_text(encoding="utf-8")))
    problems = lint.check(source, bundle.component_names() | set(packs.by_component(custom)))
    if problems:
        raise SystemExit("%s has problems:\n  - %s" % (example, "\n  - ".join(problems)))
    html, packs = page.build_page(page.inline_images(source), title=example.stem, extra_packs=custom)
    prelude = (
        "<style>:root{%s}html,body{margin:0;background:var(--bg);color:var(--foreground);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif}"
        "body{padding:%dpx !important}#root{width:%dpx;max-width:100%%}</style>" % (THEMES[theme], PAD, width)
    )
    html = html.replace("</head>", prelude + "</head>", 1).replace("</body>", MEASURE + "</body>", 1)

    out.parent.mkdir(parents=True, exist_ok=True)
    win = width + 2 * PAD
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "widget.html"
        f.write_text(html, encoding="utf-8")
        proc, ws = open_chrome(chrome, td)
        try:
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
            close_chrome(proc, ws)
    w, h = png_size(out)
    if w == 0:
        raise SystemExit("screenshot was not written")
    return "%s: %dx%d px (css %dx%d, %s theme, packs: %s)" % (out.name, w, h, win, height, theme, ", ".join(packs) or "none")


# Waits until every `.mount` container of an exported report (if the page has any) has drawn something.
HTML_READY = (
    "(function(){var m=document.querySelectorAll('.mount');"
    "return document.readyState==='complete'&&Array.prototype.every.call(m,function(e){return e.children.length>0})})()"
)
HTML_HEIGHT = "Math.ceil(document.documentElement.getBoundingClientRect().height)"  # the content, not the viewport it sits in
LOCAL_SCHEMES = ("file:", "data:", "blob:", "about:")


def page_problems(events) -> dict:
    """What a page did wrong while it loaded, from DevTools events: console errors, failed requests, requests that left file:/data:."""
    errors, failed, outside = [], [], []
    for e in events:
        m, p = e.get("method"), e.get("params", {})
        if m == "Runtime.exceptionThrown":
            d = p.get("exceptionDetails", {})
            errors.append((d.get("exception") or {}).get("description") or d.get("text") or "exception")
        elif m == "Runtime.consoleAPICalled" and p.get("type") == "error":
            errors.append(" ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", [])))
        elif m == "Log.entryAdded" and p.get("entry", {}).get("level") == "error":
            errors.append(p["entry"].get("text", "log error") + " " + p["entry"].get("url", ""))
        elif m == "Network.loadingFailed":
            failed.append(p.get("errorText", "failed"))
        elif m == "Network.responseReceived" and p.get("response", {}).get("status", 0) >= 400:
            failed.append("%s %s" % (p["response"]["status"], p["response"].get("url", "")))
        elif m == "Network.requestWillBeSent":
            url = p.get("request", {}).get("url", "")
            if not url.startswith(LOCAL_SCHEMES):
                outside.append(url)
    return {"console_errors": errors, "failed_requests": failed, "outside_requests": outside}


def shoot_html(html_file: Path, out: Path, theme: str = "auto", width: int = 1100, scale: int = 2, chrome: str = None, probe: str = None, before: str = None) -> str:
    """Screenshot an existing HTML file loaded from file://, full page height. `theme` light|dark forces prefers-color-scheme."""
    html_file = html_file.resolve()
    if not html_file.is_file():
        raise SystemExit("no such file: %s" % html_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    value = None
    with tempfile.TemporaryDirectory() as td:
        proc, ws = open_chrome(chrome, td)
        try:
            for domain in ("Page", "Runtime", "Log", "Network"):
                ws.call(domain + ".enable")
            ws.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": theme}] if theme in ("light", "dark") else [])
            ws.call("Emulation.setDeviceMetricsOverride", width=width, height=900, deviceScaleFactor=scale, mobile=False)
            ws.call("Page.navigate", url=html_file.as_uri())
            height, last, stable = 0, -1, 0
            for _ in range(300):  # 60 s at most
                ready = ws.call("Runtime.evaluate", expression=HTML_READY, returnByValue=True)["result"].get("value")
                now = int(ws.call("Runtime.evaluate", expression=HTML_HEIGHT, returnByValue=True)["result"].get("value") or 0)
                stable = stable + 1 if (ready and now == last) else 0
                last = now
                if stable >= 6:  # 1.2 s without the height moving, after every section drew
                    height = now
                    break
                time.sleep(0.2)
            if not height:
                raise SystemExit("the page did not finish rendering within 60 s")
            ws.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=scale, mobile=False)
            if before:
                ws.call("Runtime.evaluate", expression=before, awaitPromise=True)
            time.sleep(1.0)  # chart animations
            shot = ws.call("Page.captureScreenshot", format="png", fromSurface=True)
            out.write_bytes(base64.b64decode(shot["data"]))
            if probe:
                res = ws.call("Runtime.evaluate", expression=probe, returnByValue=True, awaitPromise=True)
                value = res.get("result", {}).get("value", res.get("exceptionDetails", {}).get("text"))
            ws.call("Runtime.evaluate", expression="0")  # flush trailing events
            problems = page_problems(ws.events)
        finally:
            close_chrome(proc, ws)
    w, h = png_size(out)
    if w == 0:
        raise SystemExit("screenshot was not written")
    lines = [
        "%s: %dx%d px (css %dx%d, %s theme, html mode) | console errors: %d | failed requests: %d | requests outside file:/data: %d"
        % (out.name, w, h, width, height, theme, len(problems["console_errors"]), len(problems["failed_requests"]), len(problems["outside_requests"]))
    ]
    for key in ("console_errors", "failed_requests", "outside_requests"):
        lines += ["  %s: %s" % (key, item[:200]) for item in problems[key][:5]]
    if probe:
        lines.append("eval: %s" % json.dumps(value))
    return "\n".join(lines)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", metavar="EXAMPLE OUT", help="EXAMPLE.oui OUT.png; with --html only OUT.png")
    ap.add_argument("--html", metavar="FILE", help="screenshot this existing HTML file (loaded from file://) instead of building a widget page")
    ap.add_argument("--theme", choices=["dark", "light", "auto"], help="default: dark for an example, auto for --html (auto = Chrome's default)")
    ap.add_argument("--width", type=int, help="widget column width in CSS px (default 640, the chat column); with --html the viewport width (default 1100)")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--chrome")
    ap.add_argument("--pack", action="append", default=[], metavar="FILE", help="link a custom component pack (repeatable); a folder links every .js in it")
    ap.add_argument("--keep-html", action="store_true", help="also save OUT.html: a live, self-contained copy of the widget")
    ap.add_argument("--eval", dest="probe", metavar="JS", help="with --html: print the JSON value of this expression, evaluated in the finished page")
    ap.add_argument("--before", metavar="JS", help="with --html: run this expression in the finished page before the screenshot (e.g. click a button)")
    a = ap.parse_args(argv)
    if a.html:
        if len(a.paths) != 1:
            ap.error("with --html give exactly one positional argument: OUT.png")
        if a.pack or a.keep_html:
            ap.error("--pack and --keep-html belong to example mode, not --html")
        a.theme = a.theme or "auto"
        a.width = a.width or 1100
    else:
        if len(a.paths) != 2:
            ap.error("give EXAMPLE.oui and OUT.png (or use --html FILE OUT.png)")
        if a.probe or a.before:
            ap.error("--eval and --before need --html")
        if a.theme == "auto":
            ap.error("--theme auto is only for --html; an example needs dark or light")
        a.theme = a.theme or "dark"
        a.width = a.width or 640
    return a


def main() -> None:
    a = parse_args()
    if a.html:
        print(shoot_html(Path(a.html), Path(a.paths[0]).resolve(), a.theme, a.width, a.scale, a.chrome, a.probe, a.before))
    else:
        print(shoot(Path(a.paths[0]), Path(a.paths[1]).resolve(), a.theme, a.width, a.scale, a.chrome, a.keep_html, a.pack))


if __name__ == "__main__":
    main()
