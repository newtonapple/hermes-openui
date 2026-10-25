"""Assemble a self-contained widget page.

The desktop reads a previewed file through a bridge capped at 512 KiB and loads it as a sandboxed `srcdoc` iframe (no sibling
files), so the runtime travels INSIDE the page as base64 gzip and is inflated with the browser's DecompressionStream. The
runtime is a core plus optional packs; only the packs whose components the source actually calls are embedded.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import List, Tuple

from . import bundle
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


def inline_images(source: str) -> str:
    """Image("/local/file.png", ...) -> Image("data:image/png;base64,...", ...). The widget frame is sandboxed and cannot
    read local files, so the bytes must travel inside the page. Only image extensions are read, with a per-image cap."""

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
        if len(data) > IMAGE_MAX:
            raise WidgetError(
                "%s is %d KB; the limit is %d KB per image. Downscale it first, e.g. `sips -Z 800 in.png --out out.png` (macOS) or Pillow."
                % (p.name, len(data) // 1024, IMAGE_MAX // 1024)
            )
        return m.group(1) + json.dumps("data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii")))

    return _IMG_CALL.sub(sub, source)


def _blob(name: str, file: str) -> str:
    b64 = base64.b64encode((bundle.ASSETS / file).read_bytes()).decode("ascii")
    return '<script data-oui="%s" type="text/plain">%s</script>' % (name, b64)


def build_page(source: str, title: str = "Hermes widget", everything: bool = False) -> Tuple[str, List[str]]:
    """(html, packs) for `source`. `source` must already have had its images inlined. Raises WidgetError if over budget."""
    m = bundle.manifest()
    packs = select_packs(source, everything)
    blobs = [_blob("core", m["core"]["file"])] + [_blob(p, m["packs"][p]["file"]) for p in packs]
    # '<' is escaped so no sequence in the source can close the surrounding <script>.
    source_json = json.dumps(source).replace("<", "\\u003c")
    html = TEMPLATE.replace("__TITLE__", re.sub(r"[<>&]", "", title)).replace("__SOURCE__", source_json).replace("__BLOBS__", "\n".join(blobs))
    size = len(html.encode("utf-8"))
    if size > SAFE_BUDGET:
        costs = ", ".join("%s ~%d KB" % (p, m["packs"][p]["gz"] * 4 // 3 // 1024) for p in packs) or "no optional packs"
        raise WidgetError(
            "The widget page would be %d KB (core + %s); the desktop reads at most %d KB and a cut-off page renders blank. "
            "Use fewer rows or cards, smaller images, or drop a pack's components to save its weight (%s)."
            % (size // 1024, " + ".join(packs) or "no packs", SAFE_BUDGET // 1024, costs)
        )
    return html, packs
