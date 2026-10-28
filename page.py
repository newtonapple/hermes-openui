"""Assemble a self-contained widget page.

The desktop reads a previewed file through a bridge capped at 512 KiB and loads it as a sandboxed `srcdoc` iframe (no sibling
files), so the runtime travels INSIDE the page as base64 gzip and is inflated with the browser's DecompressionStream. The
runtime is a core plus optional packs; only the packs whose components the source actually calls are embedded.
"""
from __future__ import annotations

import base64
import gzip
import html as _html
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

from . import bundle
from . import packs as _packs
from .lint import strip_strings

DESKTOP_READ_CAP = 512 * 1024  # hermes:readFileText hard cap (TEXT_PREVIEW_MAX_BYTES)
SAFE_BUDGET = 480 * 1024  # leave headroom under the cap
IMAGE_MAX = 100 * 1024  # per image; the whole page must still fit SAFE_BUDGET
IMG_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}
_IMG_CALL = re.compile(r'(\bImage\(\s*)"((?:[^"\\]|\\.)*)"')
_CALL = re.compile(r"(?<![@\w$])([A-Z][A-Za-z0-9_]*)\s*\(")


class WidgetError(Exception):
    """A problem the model can fix (bad image, page over budget); the message is returned to it verbatim."""


TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="color-scheme" content="light dark">
<title>__TITLE__</title>
<style>html{scrollbar-width:none}html::-webkit-scrollbar{display:none}body{padding:2px 0 6px;box-sizing:border-box}#root{min-width:0}
*{box-sizing:border-box}button:focus-visible{outline:2px solid var(--accent,AccentColor);outline-offset:2px}
#oui-err{font:12px ui-monospace,Menlo,monospace;color:#f85149;white-space:pre-wrap}</style>
</head><body>
<div id="root"></div><div id="oui-err"></div>
<script id="oui-src" type="application/json">__SOURCE__</script>
__BLOBS__
<script>
(async function () {
  var err = document.getElementById("oui-err");
  try {
    var blobs = Array.prototype.slice.call(document.querySelectorAll("script[data-oui]"));
    var inflate = async function (el) {
      var bin = Uint8Array.from(atob(el.textContent.trim()), function (c) { return c.charCodeAt(0); });
      return new Response(new Blob([bin]).stream().pipeThrough(new DecompressionStream("gzip"))).text();
    };
    var code = await Promise.all(blobs.map(inflate));
    code.forEach(function (js) { var s = document.createElement("script"); s.textContent = js; document.head.appendChild(s); });
    window.HermesOpenUI.mount(document.getElementById("root"), JSON.parse(document.getElementById("oui-src").textContent));
  } catch (e) {
    err.textContent = "OpenUI widget failed to start: " + (e && e.message ? e.message : e);
  }
})();
</script>
</body></html>
"""


def select_packs(source: str, everything: bool = False) -> List[str]:
    """Optional packs whose components `source` calls (sorted, stable). Text inside strings is ignored."""
    m = bundle.manifest()
    if everything:
        return sorted(m["packs"])
    used = set(_CALL.findall(strip_strings(source)))
    return sorted({m["components"][c] for c in used if c in m["components"]})


def inline_images(source: str, max_bytes: int = IMAGE_MAX) -> str:
    """Image("/local/file.png", ...) -> Image("data:image/png;base64,...", ...). The widget frame is sandboxed and cannot
    read local files, so the bytes must travel inside the page. Only image extensions are read, with a per-image cap
    (`max_bytes`: 100 KB for chat widgets, which share a 480 KB page budget; exported reports pass a larger one)."""

    def sub(m: "re.Match[str]") -> str:
        try:
            raw = json.loads('"' + m.group(2) + '"')
        except ValueError:
            return m.group(0)
        if raw.startswith(("data:", "http://", "https://")):
            return m.group(0)
        p = Path(raw[7:] if raw.startswith("file://") else raw).expanduser()
        if not p.is_absolute():
            raise WidgetError("Image path must be absolute (or start with ~): %s" % raw)
        mime = IMG_MIME.get(p.suffix.lower())
        if not mime:
            raise WidgetError("Unsupported image type %r (use png, jpg, webp, gif or svg): %s" % (p.suffix, raw))
        if not p.is_file():
            raise WidgetError("Image file not found: %s" % raw)
        data = p.read_bytes()
        if len(data) > max_bytes:
            raise WidgetError(
                "%s is %d KB; the limit is %d KB per image. Downscale it first, e.g. `sips -Z 800 in.png --out out.png` (macOS) or Pillow."
                % (p.name, len(data) // 1024, max_bytes // 1024)
            )
        return m.group(1) + json.dumps("data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii")))

    return _IMG_CALL.sub(sub, source)


def _blob(name: str, file: str) -> str:
    b64 = base64.b64encode((bundle.ASSETS / file).read_bytes()).decode("ascii")
    return '<script data-oui="%s" type="text/plain">%s</script>' % (name, b64)


def _custom_blob(pack: "_packs.Pack") -> str:
    """A user-linked pack, gzipped and base64'd like the built-in ones. mtime=0 keeps the bytes reproducible."""
    gz = gzip.compress(pack.source.encode("utf-8"), 9, mtime=0)
    return '<script data-oui="custom:%s" type="text/plain">%s</script>' % (pack.name, base64.b64encode(gz).decode("ascii"))


def build_page(source: str, title: str = "Hermes widget", everything: bool = False, extra_packs: "List[_packs.Pack] | None" = None) -> Tuple[str, List[str]]:
    """(html, packs) for `source`. `source` must already have had its images inlined. Raises WidgetError if over budget.
    `extra_packs` are user-linked packs; only the ones whose components `source` calls are embedded, and they are named
    `custom:<name>` in the returned list."""
    m = bundle.manifest()
    packs = select_packs(source, everything)
    custom = _packs.used(source, extra_packs or [])
    blobs = [_blob("core", m["core"]["file"])] + [_blob(p, m["packs"][p]["file"]) for p in packs] + [_custom_blob(p) for p in custom]
    # '<' is escaped so no sequence in the source can close the surrounding <script>.
    source_json = json.dumps(source).replace("<", "\\u003c")
    html = TEMPLATE.replace("__TITLE__", re.sub(r"[<>&]", "", title)).replace("__SOURCE__", source_json).replace("__BLOBS__", "\n".join(blobs))
    size = len(html.encode("utf-8"))
    if size > SAFE_BUDGET:
        costs = ", ".join("%s ~%d KB" % (p, m["packs"][p]["gz"] * 4 // 3 // 1024) for p in packs) or "no optional packs"
        costs += "".join(", custom:%s ~%d KB" % (p.name, len(gzip.compress(p.source.encode("utf-8"), 9, mtime=0)) * 4 // 3 // 1024) for p in custom)
        raise WidgetError(
            "The widget page would be %d KB (core + %s); the desktop reads at most %d KB and a cut-off page renders blank. "
            "Use fewer rows or cards, smaller images, or drop a pack's components to save its weight (%s)."
            % (size // 1024, " + ".join(packs + ["custom:" + p.name for p in custom]) or "no packs", SAFE_BUDGET // 1024, costs)
        )
    return html, packs + ["custom:%s" % p.name for p in custom]


# ---------------------------------------------------------------------------------------------------------------------
# Standalone export: many widgets in ONE self-contained report page that opens from disk in any browser (no Hermes, no network).
# Unlike a chat widget this page is not read through the desktop's 512 KiB bridge, so its budget is EXPORT_MAX_BYTES.
# ---------------------------------------------------------------------------------------------------------------------

EXPORT_MAX_BYTES = 8 * 1024 * 1024
THEMES = ("auto", "light", "dark")

EXPORT_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="__SCHEME__">
<meta name="generator" content="hermes-openui __VERSION__">
<title>__TITLE__</title>
<style>
html{color-scheme:__SCHEME__;-webkit-text-size-adjust:100%}
__ACCENT__*{box-sizing:border-box}
body{margin:0;background:Canvas;color:CanvasText;font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,Roboto,"Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}
.page{max-width:960px;margin:0 auto;padding:48px 24px 40px}
h1{font-size:28px;line-height:1.2;font-weight:650;letter-spacing:-.015em;margin:0 0 32px;overflow-wrap:anywhere}
.sec{margin:0 0 40px;min-width:0}
.sec h2{font-size:17px;line-height:1.3;font-weight:600;margin:0 0 14px;overflow-wrap:anywhere}
.mount{min-width:0}
.sec-err{font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;color:#f85149;white-space:pre-wrap}
.sec-err:empty{display:none}
footer{margin-top:56px;padding-top:16px;border-top:1px solid color-mix(in srgb,CanvasText 14%,transparent);font-size:12px;line-height:1.4;color:GrayText}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
#oui-note{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);max-width:calc(100% - 32px);padding:8px 14px;border-radius:8px;background:CanvasText;color:Canvas;font-size:13px;line-height:1.4;box-shadow:0 4px 16px rgba(0,0,0,.25)}
#oui-note[hidden]{display:none}
@media (max-width:600px){.page{padding:28px 16px 28px}h1{font-size:24px;margin-bottom:24px}.sec{margin-bottom:32px}}
@page{margin:14mm}
@media print{html{color-scheme:light}body{background:#fff;color:#000}.page{max-width:none;padding:0}*{box-shadow:none!important;text-shadow:none!important}.sec{break-inside:avoid;page-break-inside:avoid}#oui-note{display:none!important}footer{margin-top:24px}}
</style>
__THEME_SHIM__<script id="oui-hermes-shim">
// Widget buttons message the Hermes chat through window.hermes.send. A standalone file has no chat: say so instead of failing silently.
(function () {
  if (window.hermes && typeof window.hermes.send === "function") return;
  var timer;
  window.hermes = {
    send: function () {
      var note = document.getElementById("oui-note");
      if (note) { note.hidden = false; clearTimeout(timer); timer = setTimeout(function () { note.hidden = true; }, 4500); }
      return Promise.resolve({ ok: false, error: "standalone export: buttons only reach a chat inside Hermes" });
    }
  };
})();
</script>
</head><body>
<main class="page">
<h1>__TITLE__</h1>
__SECTIONS__
<div id="oui-err" class="sec-err"></div>
<div id="oui-fatal" class="sec-err" hidden></div>
<noscript><p class="sec-err">This report needs JavaScript to draw its charts and tables.</p></noscript>
<footer>Exported from Hermes (hermes-openui __VERSION__)</footer>
</main>
<div id="oui-note" role="status" aria-live="polite" hidden>Interactive buttons work inside Hermes only</div>
<script id="oui-src" type="application/json">__SOURCES__</script>
__BLOBS__
<script id="oui-boot">
(async function () {
  var msg = function (e) { return e && e.message ? e.message : String(e); };
  var data;
  try {
    data = JSON.parse(document.getElementById("oui-src").textContent);
    var blobs = Array.prototype.slice.call(document.querySelectorAll("script[data-oui]"));
    var inflate = async function (el) {
      var bin = Uint8Array.from(atob(el.textContent.trim()), function (c) { return c.charCodeAt(0); });
      return new Response(new Blob([bin]).stream().pipeThrough(new DecompressionStream("gzip"))).text();
    };
    var code = await Promise.all(blobs.map(inflate));
    code.forEach(function (js) { var s = document.createElement("script"); s.textContent = js; document.head.appendChild(s); });
  } catch (e) {
    var fatal = document.getElementById("oui-fatal");
    fatal.textContent = "This report could not start: " + msg(e) + ". Open it in a current Chrome, Edge, Safari or Firefox.";
    fatal.hidden = false;
    return;
  }
  var mounts = document.querySelectorAll(".mount");
  data.forEach(function (source, i) {
    try {
      window.HermesOpenUI.mount(mounts[i], source);
    } catch (e) {
      mounts[i].className += " sec-err";
      mounts[i].textContent = "This section could not be drawn: " + msg(e);
    }
  });
})();
</script>
</body></html>
"""

# Forcing a theme needs two things: CSS color-scheme (page chrome and the runtime's CanvasText/Canvas fallbacks) and this tiny
# matchMedia shim, because the runtime picks its light/dark mode with matchMedia("(prefers-color-scheme: dark)"). It must run
# before the runtime does; every other media query is passed through untouched.
EXPORT_THEME_SHIM = r"""<script id="oui-theme-shim">
(function () {
  var dark = __DARK__, orig = window.matchMedia, none = function () {};
  window.matchMedia = function (q) {
    var m = /prefers-color-scheme\s*:\s*(dark|light)/.exec(String(q));
    if (!m) return orig ? orig.call(window, q) : { matches: false, media: String(q), onchange: null, addListener: none, removeListener: none, addEventListener: none, removeEventListener: none, dispatchEvent: function () { return false; } };
    return { matches: (m[1] === "dark") === dark, media: String(q), onchange: null, addListener: none, removeListener: none, addEventListener: none, removeEventListener: none, dispatchEvent: function () { return false; } };
  };
})();
</script>
"""


# The runtime reads --accent (the Hermes app injects it) and falls back to the CSS keyword AccentColor, which Chrome does not support, so a
# plain browser page would lose button borders and tab underlines. The standalone page therefore supplies a concrete accent per theme.
_ACCENT_LIGHT, _ACCENT_DARK = "#0969da", "#5b9cf6"
_ACCENT_CSS = {
    "light": ":root{--accent:%s}\n" % _ACCENT_LIGHT,
    "dark": ":root{--accent:%s}\n" % _ACCENT_DARK,
    "auto": ":root{--accent:%s}\n@media (prefers-color-scheme:dark){:root{--accent:%s}}\n" % (_ACCENT_LIGHT, _ACCENT_DARK),
}


@lru_cache(maxsize=1)
def plugin_version() -> str:
    """The version in plugin.yaml (the single source of truth for releases)."""
    try:
        m = re.search(r"^version:\s*([^\s#]+)", (bundle.ROOT / "plugin.yaml").read_text(encoding="utf-8"), re.M)
    except OSError:
        m = None
    return m.group(1).strip("\"'") if m else "dev"


def _fill(template: str, values: "dict") -> str:
    """Replace __NAME__ markers in ONE pass, so text inside a value (a title, a source) is never mistaken for a marker."""
    return re.sub(r"__([A-Z_]+)__", lambda m: values.get(m.group(1), m.group(0)), template)


def build_export_page(sections: list, title: str = "Hermes report", theme: str = "auto", extra_packs: "List[_packs.Pack] | None" = None) -> Tuple[str, List[str]]:
    """(html, packs) for a report. `sections` is a list of {"title": str or None, "source": str}; every source must already have its
    images inlined. The runtime is embedded once, with only the built-in and user packs the sources actually call. Each section is
    mounted into its own element. Raises WidgetError above EXPORT_MAX_BYTES or for an unknown theme."""
    if theme not in THEMES:
        raise WidgetError("theme must be one of %s, got %r" % (", ".join(THEMES), theme))
    m = bundle.manifest()
    sources = [str(s["source"]) for s in sections]
    joined = "\n".join(sources)
    packs = select_packs(joined)
    custom = _packs.used(joined, extra_packs or [])
    blobs = [_blob("core", m["core"]["file"])] + [_blob(p, m["packs"][p]["file"]) for p in packs] + [_custom_blob(p) for p in custom]
    esc = lambda text: _html.escape(" ".join(str(text).split()), quote=True)  # noqa: E731
    blocks = []
    for s in sections:
        heading = "<h2>%s</h2>" % esc(s["title"]) if s.get("title") and str(s["title"]).strip() else ""
        blocks.append('<section class="sec">%s<div class="mount"></div></section>' % heading)
    html = _fill(
        EXPORT_TEMPLATE,
        {
            "SCHEME": {"auto": "light dark", "light": "light", "dark": "dark"}[theme],
            "ACCENT": _ACCENT_CSS[theme],
            "VERSION": _html.escape(plugin_version()),
            "TITLE": esc(title) or "Hermes report",
            "THEME_SHIM": "" if theme == "auto" else EXPORT_THEME_SHIM.replace("__DARK__", "true" if theme == "dark" else "false"),
            "SECTIONS": "\n".join(blocks),
            # '<' is escaped so no sequence in a source can close the surrounding <script>.
            "SOURCES": json.dumps(sources).replace("<", "\\u003c"),
            "BLOBS": "\n".join(blobs),
        },
    )
    size = len(html.encode("utf-8"))
    if size > EXPORT_MAX_BYTES:
        raise WidgetError(
            "The exported page would be %.1f MB; the limit is %d MB. Use smaller images or fewer sections (or export two files)."
            % (size / (1024.0 * 1024.0), EXPORT_MAX_BYTES // (1024 * 1024))
        )
    return html, packs + ["custom:%s" % p.name for p in custom]
