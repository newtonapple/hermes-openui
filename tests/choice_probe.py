"""Shared setup for the Choice browser checks: widget sources (generic data), the native harness page, a recorder of steps, and the page helpers.

Used by tests/test_choice_native.py (opt-in: OPENUI_TEST_CHROME=1) and by hand for the documentation pictures (python3 tests/choice_probe.py --help).
Chrome is launched ONLY through tools/shoot.py, which drives the page with real mouse and key events.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import notes_probe as NP  # noqa: E402  (its harness page builder, one Chrome launch, the app stylesheet)

ROOT = NP.ROOT
LONG = "Check the whole fleet one machine at a time and report every anomaly you can find in the logs of each"  # 100 characters of option text
OTHER500 = "x" * 500

SOURCES = {
    # three questions in a Card, one multiple, one without the Other row (the documentation example)
    "cq": (
        'root = Stack([plan])\nplan = Card([q1, q2, q3], "Before I restart")\n'
        'q1 = Choice("Which node should I restart first?", ["web-1", "web-2"])\n'
        'q2 = Choice("Which checks should I run?", ["Disk", "Memory", "Network"], null, true)\n'
        'q3 = Choice("Clear the cache on db?", ["Yes", "No"], null, null, false)\n'
    ),
    # two questions on the first tab, one on a tab that is never shown before the count is read
    "tabs": (
        'root = Stack([tabs])\ntabs = Tabs([t1, t2])\n'
        't1 = TabItem("Restart", [r1, r2])\nt2 = TabItem("Cleanup", [c1])\n'
        'r1 = Choice("Which node should I restart first?", ["web-1", "web-2"])\n'
        'r2 = Choice("Drain the node first?", ["Yes", "No"])\n'
        'c1 = Choice("Clear the cache on db?", ["Yes", "No"])\n'
    ),
    # the same shape as `tabs`: the question on the second tab is never shown before the message is sent
    "tabs2": (
        'root = Stack([tabs])\ntabs = Tabs([t1, t2])\n'
        't1 = TabItem("Restart", [r1, r2])\nt2 = TabItem("Cleanup", [c1])\n'
        'r1 = Choice("Which node should I restart first?", ["web-1", "web-2"])\n'
        'r2 = Choice("Drain the node first?", ["Yes", "No"])\n'
        'c1 = Choice("Clear the cache on db?", ["Yes", "No"])\n'
    ),
    "one": 'root = Stack([ask])\nask = Choice("Which node should I restart first?", ["web-1", "web-2", "web-3"], "I will restart it and report back.")\n',
    # a multiple question whose message is over 500 characters and well under 4,000
    "long": 'root = Stack([ask])\nask = Choice("Which checks should I run?", ["A ' + LONG + '", "B ' + LONG + '", "C ' + LONG + '", "D ' + LONG + '", "E ' + LONG + '"], null, true, false)\n',
    # eight single questions: a 500 character Other text on each is over 4,000 characters
    "huge": "root = Stack([" + ", ".join("h%d" % i for i in range(8)) + "])\n" + "".join('h%d = Choice("Question number %d?", ["a", "b"])\n' % (i, i + 1) for i in range(8)),
    "btn": (
        'root = Stack([a, b, c, d])\n'
        'a = Button("Long", @ToAssistant("' + "L" * 600 + '"))\nb = Button("Edge", @ToAssistant("' + "E" * 500 + '"))\n'
        'c = Button("Over", @ToAssistant("' + "O" * 501 + '"))\nd = Button("Ok", @ToAssistant("Restart the web service"))\n'
    ),
    # a Choice next to a Table: notes mode makes the Choice inert and still lets the table be noted
    "nt": (
        'root = Stack([ask, tbl])\nask = Choice("Which node should I restart first?", ["web-1", "web-2"])\n'
        'tbl = Table(["service", "status"], [["web", "up"], ["api", "CrashLoop"]])\n'
    ),
    "plain": 'root = Stack([p])\np = Markdown("A plain widget with no Choice.")\n',
    # a multiple question with the Other row, for the checkbox indicator on that row
    "mo": 'root = Stack([ask])\nask = Choice("Which checks should I run?", ["Disk", "Memory"], null, true)\n',
}
# the same one-question widget four times: the composer address the bar sends to (a tile, the main chat with a session, the main chat of a new draft, no marker)
for _i in range(1, 5):
    SOURCES["r%d" % _i] = 'root = Stack([ask])\nask = Choice("Restart the web service?", ["Yes", "No"])\n'
SOURCES["rf"] = SOURCES["r1"]  # the host refuses the message (no chat input took it)
SOURCES["brt"] = 'root = Stack([a, b, c, d])\n' + "".join('%s = Button("%s", @ToAssistant("Restart the %s service"))\n' % (v, n, n.lower()) for v, n in zip("abcd", ("Web", "Api", "Db", "Cache")))
# a saved board whose widget is redrawn under the same name with another set of questions (the first question is still there)
SOURCES["st"] = ('root = Stack([a, b])\na = Choice("Which node should I restart first?", ["web-1", "web-2"])\nb = Choice("Drain the node first?", ["Yes", "No"])\n')
ST_REDRAWN = ('root = Stack([a, c])\na = Choice("Which node should I restart first?", ["web-1", "web-2"])\nc = Choice("Clear the cache on db?", ["Yes", "No"])\n')
NAMES = list(SOURCES)

# preview only: five questions of exactly 100 characters, so the full message is over the 500 the app allows and the clipped one fits
FIT_QUESTIONS = [("Question %d of five: which machine should the fleet roll restart first, and why does it matter to us tonight?" % n)[:100].rstrip() for n in range(1, 6)]
FIT_QUESTIONS = [q + "x" * (100 - len(q)) for q in FIT_QUESTIONS]
assert all(len(q) == 100 and not q.endswith(" ") for q in FIT_QUESTIONS)
PREVIEW_FIT = "root = Stack([" + ", ".join("f%d" % n for n in range(1, 6)) + "])\n" + "".join('f%d = Choice("%s", ["yes", "no"])\n' % (n, q) for n, q in enumerate(FIT_QUESTIONS, 1))


def build_page(td, widths, names=None, theme="dark", app_css=None, plugin=None, sources=None):
    """Writes the native harness page for the named widgets (the real desktop/plugin.js, a stub SDK) and returns its path."""
    import shoot
    page, _lint, _b, _p = shoot.load_modules()
    sources = sources or SOURCES
    names = names or list(sources)
    cfg = {"widths": list(widths), "widgets": [{"name": n, "source": page.inline_images(sources[n])} for n in names]}
    td = Path(td)
    (td / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
    out = td / "page.html"
    cmd = ["node", str(ROOT / "build" / "tests" / "native-harness.mjs"), "--plugin", str(plugin or os.environ.get("CHOICE_PLUGIN") or ROOT / "desktop" / "plugin.js"),
           "--config", str(td / "cfg.json"), "--out", str(out), "--theme", theme]
    if app_css:
        cmd += ["--app-css", str(app_css)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise SystemExit("harness build failed:\n" + r.stdout + r.stderr)
    return out


# Page helpers (installed by the first step). The recorders see what the app would: keys (and whether they were prevented), what the composer's
# type-to-focus would take, and the double-click the app turns into a heart.
HELPERS = r"""
window.__C = (function () {
  var cell = function (w) { return document.querySelector('.cell[data-widget="' + w + '"]'); };
  var root = function (w) { return cell(w).querySelector('.hermes-openui-root'); };
  var cards = function (w) { return Array.prototype.slice.call(root(w).querySelectorAll('[data-oui-choice]')); };
  var keys = [], steal = 0, hearts = 0, dbl = 0;
  // every key, in the capture phase (before the widget can stop it); dp is read after the whole dispatch, when handlers had their say
  addEventListener('keydown', function (e) { var r = { k: e.key, t: e.target.tagName, dp: null }; keys.push(r); setTimeout(function () { r.dp = e.defaultPrevented; }, 0); }, true);
  // The app's type-to-focus (app/hooks/use-keybinds.ts: window.addEventListener('keydown', ..., { capture: true }) with composer-focus-keys.ts rules): it runs in the
  // CAPTURE phase, BEFORE any handler of the widget, so a widget cannot stop it. A printable key with no modifier, not composing, not in an editable field, and not
  // Enter or Space on a control that activates itself (isActivateOnEnterTarget) goes to the composer. This only counts; it prevents nothing, so the card's own
  // handling can still be seen. bubbled: the keys a bubble-phase listener on document got (a card that called stopPropagation would hide a key from it).
  addEventListener('keydown', function (e) { var t = e.target; var ed = t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)); var act = (e.key === 'Enter' || e.key === ' ') && t && t.closest && t.closest('button, a[href], summary, select, input'); if (!e.isComposing && !e.metaKey && !e.ctrlKey && !e.altKey && !ed && !act && e.key.length === 1) steal++; }, true);
  var bubbled = [];
  document.addEventListener('keydown', function (e) { bubbled.push(e.key); });
  // use-message-reactions.ts isTapbackDoubleClick: detail 2 and not inside one of these
  var NOT = 'a, button, input, pre, select, textarea, [contenteditable="true"], [role="button"]';
  document.querySelectorAll('[data-host]').forEach(function (h) { h.addEventListener('dblclick', function (e) { dbl++; if (e.detail === 2 && !e.target.closest(NOT)) hearts++; }); });
  var ws = function (s) { return String(s).replace(/\s+/g, ' ').trim(); };
  var after = function (n) { return new Promise(function (res) { var i = 0; var tick = function () { if (++i < (n || 8)) requestAnimationFrame(tick); else res(true); }; requestAnimationFrame(tick); }); };
  var st = function (w) {
    var r = root(w), bar = r.querySelector('[data-oui-bar]');
    var send = bar && bar.querySelector('[data-oui-send]'), clear = bar && bar.querySelector('[data-oui-clear]'), a = document.activeElement;
    return {
      q: cards(w).map(function (c) {
        var ta = c.querySelector('textarea'), g = c.querySelector('[role=group],[role=radiogroup]');
        return { name: ws(c.querySelector('[id]').textContent), tag: ws(c.querySelector('[data-oui-pick]').textContent),
          checked: Array.prototype.map.call(c.querySelectorAll('[data-oui-opt]'), function (b) { return b.getAttribute('aria-checked') === 'true' ? 1 : 0; }).join(''),
          roles: Array.prototype.map.call(c.querySelectorAll('[data-oui-opt]'), function (b) { return b.getAttribute('role'); }).join(','),
          pressedAttr: c.querySelectorAll('[aria-pressed]').length,
          disabled: Array.prototype.map.call(c.querySelectorAll('[data-oui-opt]'), function (b) { return b.disabled ? 1 : 0; }).join(''),
          marktext: Array.prototype.map.call(c.querySelectorAll('[data-oui-opt]'), function (b) { return b.firstElementChild.textContent; }).join(''),
          tabstops: Array.prototype.filter.call(c.querySelectorAll('[data-oui-opt]'), function (b) { return b.tabIndex === 0; }).length,
          group: g ? g.getAttribute('role') + ':' + ws(document.getElementById(g.getAttribute('aria-labelledby')).textContent) : null,
          ta: ta ? { value: ta.value, ph: ta.placeholder, max: ta.maxLength, ro: ta.readOnly, focused: document.activeElement === ta, h: Math.round(ta.getBoundingClientRect().height), note: ws(ta.parentNode.textContent.replace(ta.value, '')) } : null,
          text: ws(c.innerText) };
      }),
      count: bar ? ws(bar.querySelector('[data-oui-count]').textContent) : null,
      send: send ? { dis: send.disabled, text: send.textContent } : null, clear: clear ? { dis: clear.disabled } : null,
      alert: bar && bar.querySelector('[role=alert]') ? ws(bar.querySelector('[role=alert]').textContent) : null,
      barText: bar ? ws(bar.innerText) : null, bars: r.querySelectorAll('[data-oui-bar]').length, shortcuts: r.querySelectorAll('[aria-keyshortcuts]').length,
      focus: a ? a.tagName + (a.getAttribute('data-oui-opt') !== null ? '#opt' + a.getAttribute('data-oui-opt') : '') + (a.hasAttribute('data-oui-send') ? '#send' : '') + (a.hasAttribute('data-oui-clear') ? '#clear' : '') + (a.hasAttribute('data-oui-other') ? '#ta' : '') + (a.hasAttribute('data-oui-count') ? '#count' : '') + ':' + (a.closest('[data-oui-choice]') ? cards(w).indexOf(a.closest('[data-oui-choice]')) : '-') : null,
      store: sessionStorage.getItem('hermes-openui:answers:' + w), h: Math.round(r.getBoundingClientRect().height),
    };
  };
  // The selection indicators as the page really draws them: roles, aria-checked, the computed shape, the inner dot or check path, and the WCAG contrast of the
  // unselected outline (and of the text) against what is behind it, from the real computed colours (a 1x1 canvas resolves any CSS colour, color-mix included).
  var rgba = function (c) { var cv = document.createElement('canvas'); cv.width = cv.height = 1; var x = cv.getContext('2d', { willReadFrequently: true }); x.fillStyle = '#000'; x.fillStyle = c; x.clearRect(0, 0, 1, 1); x.fillRect(0, 0, 1, 1); var d = x.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; };
  var over = function (t, b) { var a = t[3]; return [t[0] * a + b[0] * (1 - a), t[1] * a + b[1] * (1 - a), t[2] * a + b[2] * (1 - a), 1]; };
  var bgOf = function (el) { var ls = []; for (var n = el; n; n = n.parentElement) { var c = rgba(getComputedStyle(n).backgroundColor); if (c[3] > 0) { ls.push(c); if (c[3] >= 1) break; } } var acc = [255, 255, 255, 1]; for (var i = ls.length - 1; i >= 0; i--) acc = over(ls[i], acc); return acc; };
  var lum = function (c) { var f = function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  var ratio = function (a, b) { var x = lum(a), y = lum(b); return Math.round((Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05) * 100) / 100; };
  var opac = function (el, stop) { var o = 1; for (var n = el; n && n !== stop; n = n.parentElement) o *= parseFloat(getComputedStyle(n).opacity); return o; };
  var look = function (w) {
    return cards(w).map(function (c) {
      var g = c.querySelector('[role=group],[role=radiogroup]');
      var probe = document.createElement('div'); probe.style.cssText = 'position:absolute;width:1px;height:1px;background:var(--card, Canvas)'; g.appendChild(probe);
      var cardBg = rgba(getComputedStyle(probe).backgroundColor); g.removeChild(probe);
      return { group: g.getAttribute('role'), tag: ws(c.querySelector('[data-oui-pick]').textContent), rows: Array.prototype.map.call(c.querySelectorAll('[data-oui-opt]'), function (b) {
        var m = b.querySelector('[data-oui-mark]') || document.createElement('span'), cs = getComputedStyle(m), r = m.getBoundingClientRect(), bg = bgOf(b), surface = cardBg[3] < 1 ? over(cardBg, bg) : cardBg;
        var rad = cs.borderTopLeftRadius, radPx = rad.indexOf('%') > 0 ? parseFloat(rad) / 100 * r.width : parseFloat(rad);
        var path = m.querySelector('[data-oui-check] path'), label = b.lastElementChild;
        var line = rgba(cs.borderTopColor), fill = rgba(cs.backgroundColor), text = rgba(getComputedStyle(label).color), o = opac(b, c);
        var shown = over([text[0], text[1], text[2], text[3] * o], bg);
        return { role: b.getAttribute('role'), checked: b.getAttribute('aria-checked'), pressed: b.hasAttribute('aria-pressed'), tag: b.tagName, other: b.hasAttribute('data-oui-other-row'),
          kind: m.getAttribute('data-oui-mark'), radius: rad, radiusPx: Math.round(radPx * 10) / 10, w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10,
          dot: !!m.querySelector('[data-oui-dot]'), check: path ? path.getAttribute('d') : null, checkStroke: path ? getComputedStyle(path).stroke : null,
          lineColor: cs.borderTopColor, fillColor: cs.backgroundColor, outline: ratio(line, bg), outlineCard: ratio(line, surface), fill: ratio(fill, bg), checkOnFill: path ? ratio([255, 255, 255, 1], fill) : null,
          opacity: o, text: ratio(shown, bg), visible: r.width > 0 && r.height > 0 && r.left >= 0 && r.top >= 0 && r.right <= innerWidth + 1, rowH: Math.round(b.getBoundingClientRect().height * 10) / 10, label: ws(label.textContent) };
      }) };
    });
  };
  var rects = function (w) { return cards(w).map(function (c) { return Array.prototype.map.call(c.querySelectorAll('[data-oui-mark]'), function (m) { var r = m.getBoundingClientRect(); return [r.left + scrollX, r.top + scrollY, r.width, r.height, m.getAttribute('data-oui-mark')]; }); }); };
  var tag = function (w, q, sel, name) { var base = q < 0 ? root(w) : cards(w)[q]; var el = base.querySelector(sel); if (!el) throw new Error('no ' + sel + ' in ' + w + ' ' + q); el.setAttribute('data-t', name); return true; };
  var lastKeys = function (n) { return after(4).then(function () { return keys.slice(-n); }); };
  return { look: look, rects: rects, lastKeys: lastKeys, cell: cell, root: root, cards: cards, st: st, tag: tag, after: after, keys: keys, bubbled: function () { return bubbled.slice(); }, steal: function () { return steal; }, hearts: function () { return hearts; }, dbl: function () { return dbl; },
    calls: function () { return JSON.parse(JSON.stringify(window.__hostCalls)).filter(function (c) { return c.submit; }).map(function (c) { return c.submit[1]; }); },
    args: function () { return JSON.parse(JSON.stringify(window.__hostCalls)).filter(function (c) { return c.submit; }).map(function (c) { return c.submit; }); }, ws: ws };
})();
// every Date.now() reads two seconds later than the last: the 1 s gap between two sends never blocks a step (no sleeps)
(function () { var t = 1.8e12; Date.now = function () { t += 2000; return t; }; })();
"""


# The same helpers for a preview page (tools/shoot.py EXAMPLE.oui) or an exported page: one widget, no cell around it. window.hermes.send is a stub that records.
PREVIEW_HELPERS = HELPERS.replace(
    """  var cell = function (w) { return document.querySelector('.cell[data-widget="' + w + '"]'); };
  var root = function (w) { return cell(w).querySelector('.hermes-openui-root'); };""",
    """  var root = function (w) { return document.getElementById('root') || document.querySelector('.mount'); };
  var cell = root;""",
) + r"""
window.__sent = [];
if (!document.getElementById('oui-hermes-shim')) window.hermes = { send: function (t) { window.__sent.push(t); return Promise.resolve({ ok: true }); } };
window.__C.calls = function () { return window.__sent.slice(); };
"""
assert "document.getElementById('root')" in PREVIEW_HELPERS


class Prog:
    """A list of --steps: tags an element of a widget (so a CSS selector can reach it), clicks it, records values."""

    def __init__(self):
        self.steps = []
        self.n = 0

    def js(self, expr):
        self.steps.append({"js": expr})
        return self

    def ev(self, name, expr):
        self.steps.append({"eval": "JSON.stringify(" + expr + ")", "name": name})
        return self

    def keys(self, name, n=1):  # the last n keys the page saw, with whether a handler prevented them (a raw eval: the value is a promise)
        self.steps.append({"eval": "__C.lastKeys(%d)" % n, "name": name})
        return self

    def st(self, name, w):
        return self.ev(name, "__C.st('%s')" % w)

    def tag(self, w, q, sel):
        self.n += 1
        name = "t%d" % self.n
        self.steps.append({"js": "__C.tag(%s, %d, %s, %s)" % (json.dumps(w), q, json.dumps(sel), json.dumps(name))})
        return "[data-t=%s]" % name

    def click(self, w, q, sel):
        self.steps.append({"click": self.tag(w, q, sel)})
        return self

    def dblclick(self, w, q, sel):
        self.steps.append({"dblclick": self.tag(w, q, sel)})
        return self

    def opt(self, w, q, o):
        return self.click(w, q, '[data-oui-opt="%d"]' % o)

    def click_text(self, w, text):  # a plain button by its text (a tab)
        self.n += 1
        name = "t%d" % self.n
        self.steps.append({"js": "(function(){var b=Array.prototype.find.call(__C.root(%s).querySelectorAll('button'),function(x){return x.textContent===%s});if(!b)throw new Error('no button');b.setAttribute('data-t','%s')})()" % (json.dumps(w), json.dumps(text), name)})
        self.steps.append({"click": "[data-t=%s]" % name})
        return self

    def send(self, w):
        return self.click(w, -1, "[data-oui-send]")

    def key(self, k):
        self.steps.append({"key": k})
        return self

    def type(self, text):
        self.steps.append({"type": text})
        return self

    def focus(self, w, q, sel):
        return self.js("__C.cards(%s)[%d].querySelector(%s).focus()" % (json.dumps(w), q, json.dumps(sel)))

    def wait(self):
        self.steps.append({"eval": "__C.after(8)", "name": "w%d" % len(self.steps)})
        return self


def png_pixels(path, points):
    """Reads pixels of a PNG with the standard library (8-bit RGB or RGBA, not interlaced): {(x, y): (r, g, b)}. Only the rows up to the lowest point are decoded."""
    import struct
    import zlib
    data = Path(path).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat = 8, b""
    while pos < len(data):
        n, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if typ == b"IHDR":
            w, h, depth, ctype, _c, _f, inter = struct.unpack(">IIBBBBB", body)
        elif typ == b"IDAT":
            idat += body
    assert depth == 8 and ctype in (2, 6) and inter == 0, (depth, ctype, inter)
    bpp = 3 if ctype == 2 else 4
    stride = w * bpp
    raw = zlib.decompress(idat)
    last = max(y for _x, y in points)
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(last + 1):
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        rows.append(line)
        prev = line
    return {(x, y): tuple(rows[y][x * bpp:x * bpp + 3]) for x, y in points}


def check_shapes_in_picture(tc, png, marks):
    """marks: [x, y, w, h, kind] rectangles of the indicators in a picture taken at scale 1 (page pixels). The corner pixel one step inside the box is the
    row's own colour for a round indicator (the circle leaves the corner empty) and a mixed colour for a square one (its corner is drawn): the two kinds
    differ in the picture itself, not only in the computed style."""
    pts = {}
    for x, y, _w, _h, _k in marks:
        pts[(round(x) + 1, round(y) + 1)] = None
        pts[(round(x) - 3, round(y) - 3)] = None
    px = png_pixels(png, list(pts))
    seen = set()
    for x, y, _w, _h, kind in marks:
        corner, ref = px[(round(x) + 1, round(y) + 1)], px[(round(x) - 3, round(y) - 3)]
        d = max(abs(a - b) for a, b in zip(corner, ref))
        if kind == "radio":
            tc.assertLessEqual(d, 3, (kind, corner, ref))
        else:
            tc.assertGreaterEqual(d, 40, (kind, corner, ref))
        seen.add(kind)
    tc.assertEqual(seen, {"radio", "checkbox"})  # both kinds are in the same picture


def check_indicators(tc, qs, kinds, locked=False):
    """qs: __C.look() of a widget; kinds: 'single' or 'multiple' per question. The role, the aria-checked state, the shape, the inner mark and the contrast."""
    tc.assertEqual(len(qs), len(kinds))
    for q, kind in zip(qs, kinds):
        single = kind == "single"
        tc.assertEqual(q["group"], "radiogroup" if single else "group")
        tc.assertEqual(q["tag"], "Choose one" if single else "Choose all that apply")
        for r in q["rows"]:
            tc.assertEqual((r["tag"], r["role"]), ("BUTTON", "radio" if single else "checkbox"))
            tc.assertIn(r["checked"], ("true", "false"))  # always set, never left out
            tc.assertFalse(r["pressed"])  # aria-pressed is gone
            tc.assertEqual(r["kind"], "radio" if single else "checkbox")
            tc.assertEqual((r["w"], r["h"]), (18, 18))
            tc.assertTrue(r["visible"], r)
            if single:
                tc.assertGreaterEqual(r["radiusPx"], 8.9, r)  # a circle: half the side
            else:
                tc.assertTrue(3 <= r["radiusPx"] <= 5, r)  # square with softened corners
            if r["checked"] == "true":
                if not (locked and r["other"] and r["opacity"] < 1):  # a chosen row is never dimmed; the one exception is a locked Other row left empty, which is not an answer
                    tc.assertEqual(r["opacity"], 1, r)
                tc.assertEqual(r["fillColor"], r["lineColor"], r)  # filled in one colour (the accent)
                tc.assertGreaterEqual(r["fill"], 3, r)
                if single:
                    tc.assertTrue(r["dot"] and r["check"] is None, r)
                else:
                    tc.assertTrue(r["check"] and not r["dot"], r)
                    tc.assertEqual(r["checkStroke"], "rgb(255, 255, 255)")
            else:
                tc.assertTrue(not r["dot"] and r["check"] is None, r)
                tc.assertNotEqual(r["fillColor"], r["lineColor"], r)  # hollow
                if not locked:  # non-text contrast of the outline against what is behind it, and against the card colour: WCAG 1.4.11
                    tc.assertGreaterEqual(r["outline"], 3, r)
                    tc.assertGreaterEqual(r["outlineCard"], 3, r)
            tc.assertGreaterEqual(r["text"], 4.5, r)  # also the dimmed rows of a locked card stay readable


def indicator_program(w):
    """The same walk on a preview page (w ignored) and in the native harness (w = the widget name): idle, picks, both Other rows, Send. For the light runs."""
    p = Prog()
    p.js(PREVIEW_HELPERS if w == "x" else HELPERS)
    p.ev("look_idle", "__C.look('%s')" % w)
    p.opt(w, 0, 1).opt(w, 1, 0).opt(w, 1, 2).ev("look_multi", "__C.look('%s')" % w)
    p.opt(w, 0, 2).type("The standby node").opt(w, 1, 3).type("Also the logs").ev("look_other", "__C.look('%s')" % w)
    p.send(w).ev("look_sent", "__C.look('%s')" % w).ev("marks_final", "__C.rects('%s')" % w)
    return p.steps


def shoot_oui(path, png, steps, scale=1, theme="dark", width=640):
    """One Chrome launch through tools/shoot.py for a preview page of an .oui file. Returns (recorded values, the tool's output text)."""
    cmd = [sys.executable, str(ROOT / "tools" / "shoot.py"), str(path), str(png), "--theme", theme, "--width", str(width), "--scale", str(scale), "--steps", json.dumps(steps)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    if r.returncode:
        raise SystemExit("shoot failed:\n" + r.stdout[-3000:] + r.stderr[-3000:])
    got = {}
    for line in r.stdout.splitlines():
        if line.startswith("steps: "):
            got = json.loads(line[len("steps: "):])
    return got, r.stdout


def app_css():
    return NP._app_css()


def run(page, png, width, steps, scale=1, theme="dark"):
    return NP.shoot_page(page, png, width, steps, theme=theme, scale=scale)


def _squeeze(path, colors=128):
    """Palette-quantize a picture so it stays well under 100 KB (needs Pillow, which the Hermes venv has; without it the file is left as written)."""
    try:
        from PIL import Image
    except ImportError:
        return
    im = Image.open(path).convert("RGB")
    im.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)


EXTRA_PICTURES = {"choice-card-other.png", "choice-card-answers.png", "choice-card-sent.png"}
DOC_EXAMPLES = {"basic": "choice-basic", "confirm": "choice-confirm", "multiple": "choice-multiple", "cq": "choice-card-questions", "tabs": "choice-tabs", "sv": "choice-single-vs-multiple"}
HIDE = "document.head.insertAdjacentHTML('beforeend','<style>.col h2,.label{display:none}.slot{outline:none}.col{margin:0}#page{gap:0}body{padding:10px}.cell{margin-bottom:0}</style>')"


def screenshots(outdir, width=652, extra_dir=None):
    """The documentation pictures of docs/ui-components/Choice.md: native mode, the app's stylesheet, REAL mouse and key events, one Chrome launch.
    The column is 652 px and the page has 10 px of padding on each side: 672 css px, 1344 px at 2x. Returns the file names."""
    out = Path(outdir)
    src = {n: (ROOT / "docs" / "ui-components" / "examples" / (f + ".oui")).read_text(encoding="utf-8") for n, f in DOC_EXAMPLES.items()}
    hide = HIDE
    only = lambda n: {"js": "document.querySelectorAll('.cell').forEach(function (c) { c.style.display = c.dataset.widget === '%s' ? '' : 'none'; })" % n}  # noqa: E731
    away = {"move": [2, 2]}
    p = Prog()
    p.js(HELPERS).js(hide)
    p.steps += [only("basic"), away, {"shot": "choice-basic.png"}]
    p.steps += [only("confirm"), away, {"shot": "choice-confirm.png"}]
    p.steps += [only("multiple")]
    p.opt("multiple", 0, 0).opt("multiple", 0, 2)
    p.steps += [away, {"shot": "choice-multiple.png"}]
    p.steps += [only("cq"), away, {"shot": "choice-card-questions.png"}]
    p.opt("cq", 0, 2).type("The standby node")  # the Other box opens, takes the focus, and the answer is typed
    p.steps += [{"shot": "choice-card-other.png"}]
    p.opt("cq", 1, 0).opt("cq", 1, 2)
    p.steps += [away, {"shot": "choice-card-answers.png"}]
    p.send("cq")
    p.steps += [away, {"shot": "choice-card-sent.png"}]
    p.steps += [only("tabs")]
    p.opt("tabs", 0, 0).click_text("tabs", "Cleanup").opt("tabs", 0, 1)
    p.steps += [away, {"shot": "choice-tabs.png"}]
    p.steps += [only("sv")]
    p.opt("sv", 0, 1).opt("sv", 1, 0)  # one pick in each: the filled round and the filled square show together
    p.steps += [away, {"shot": "choice-single-vs-multiple.png"}]
    with tempfile.TemporaryDirectory() as td:
        page = build_page(td, [width], list(DOC_EXAMPLES), theme="dark", app_css=app_css(), sources=src)
        run(page, out / "_last.png", width + 20, p.steps, scale=2)  # the tool also writes the final page to this name: not one of the pictures
    names = ["choice-basic.png", "choice-confirm.png", "choice-multiple.png", "choice-card-questions.png", "choice-card-other.png", "choice-card-answers.png", "choice-card-sent.png", "choice-tabs.png", "choice-single-vs-multiple.png"]
    (out / "_last.png").unlink()
    extra = Path(extra_dir) if extra_dir else out
    for n in names:
        if n in EXTRA_PICTURES and extra != out:  # the states of the card go to docs/images: docs/ui-components/images holds one picture per example file
            (extra / n).write_bytes((out / n).read_bytes())
            (out / n).unlink()
        _squeeze((extra if n in EXTRA_PICTURES else out) / n)
    return names


def screenshot_light(path, width=652):
    """The single-versus-multiple picture in the light theme (one more launch): same example, same two picks, real events."""
    src = {"sv": (ROOT / "docs" / "ui-components" / "examples" / "choice-single-vs-multiple.oui").read_text(encoding="utf-8")}
    p = Prog()
    p.js(HELPERS).js(HIDE)
    p.opt("sv", 0, 1).opt("sv", 1, 0)
    p.steps += [{"move": [2, 2]}]
    with tempfile.TemporaryDirectory() as td:
        page = build_page(td, [width], ["sv"], theme="light", app_css=app_css(), sources=src)
        run(page, Path(path), width + 20, p.steps, scale=2, theme="light")  # the final page of the run is the picture
    _squeeze(path)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Draw the documentation pictures of Choice (one Chrome launch, native mode, the app's stylesheet, real events).")
    ap.add_argument("--shots", metavar="DIR", required=True, help="write the pictures of the examples into DIR (docs/ui-components/images)")
    ap.add_argument("--extra", metavar="DIR", help="write the three pictures of the card's states into DIR (docs/images)")
    ap.add_argument("--light", metavar="FILE", help="also write the light picture of the single-versus-multiple example to FILE (docs/images/choice-single-vs-multiple-light.png)")
    a = ap.parse_args()
    print("\n".join(screenshots(a.shots, extra_dir=a.extra)))
    if a.light:
        screenshot_light(a.light)
        print(a.light)
