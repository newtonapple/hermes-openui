"""Shared setup for the Notes browser checks: widget sources (generic data), the native harness page, and one shoot.py launch.

Used by tests/test_notes_native.py (opt-in: OPENUI_TEST_CHROME=1) and by hand for screenshots (python3 tests/notes_probe.py --help).
Chrome is launched ONLY through tools/shoot.py, which drives the page with real mouse and key events.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAALQAAABGCAIAAADq9Sl3AAAAlElEQVR42u3SAQkAAAgEsQ9nBSvYP4IFLCAMluC4VA+cIgHmwByYA3NgDsyBOTAH5sAcYA7MgTkwB+bAHJgDc2AOzAHmwByYA3NgDsyBOTAH5sAcYA7MgTkwB+bAHJgDc2AOzIE5wByYA3NgDsyBOTAH5sAcmAPMgTkwB+bAHJgDc2AOzIE5wByYA3NgDsyBOTAH3ywjGwmoFx5QYQAAAABJRU5ErkJggg=="

SOURCES = {
    "text": (
        'root = Stack([intro, para, note, faq, code, tbl])\n'
        'intro = Markdown("## Service report\\n\\nThe **api** service restarted twice this week. Please check the table below.")\n'
        'para = Text("Latency is stable across all regions.")\n'
        'note = Callout("The cache hit rate dropped after the deploy.", "warn")\n'
        'faq = Faq([q1], true)\nq1 = FaqItem("What changed?", "The queue worker was resized.")\n'
        'code = CodeBlock("def total(xs):\\n    return sum(xs)\\n\\nprint(total([1, 2, 3]))", "python", "calc.py")\n'
        'tbl = Table(["service", "status", "p95"], [["web", "up", "12"], ["api", "CrashLoop", "340"], ["db", "up", "8"]])\n'
    ),
    "hosts": (
        'root = Stack([dag, erd, infra, seq, tiles, bars, map, img, line])\n'
        'dag = Dag([d1, d2, d3], [["build", "test"], ["test", "ship"]], "LR")\n'
        'd1 = DagNode("build", "Build", "done")\nd2 = DagNode("test", "Test", "running")\nd3 = DagNode("ship", "Ship", "pending")\n'
        'erd = Erd([e1, e2], [Relation("users", "orders")])\n'
        'e1 = Entity("orders", ["id uuid PK", "user_id uuid FK"])\ne2 = Entity("users", ["id uuid PK", "email text"])\n'
        'infra = InfraMap([z1, z2], [InfraLink("web", "api"), InfraLink("api", "db", "SQL")])\n'
        'z1 = InfraZone("Edge", [nweb, napi])\nz2 = InfraZone("Data", [ndb])\n'
        'nweb = InfraNode("web", "Web", "service", "up")\nnapi = InfraNode("api", "API", "service", "up")\nndb = InfraNode("db", "DB", "database", "up")\n'
        'seq = SequenceDiagram([p1, p2, p3], [s1, s2, s3])\n'
        'p1 = SeqParticipant("client", "Client", "actor")\np2 = SeqParticipant("api", "API", "service")\np3 = SeqParticipant("db", "DB", "database")\n'
        's1 = SeqMessage("client", "api", "GET items", "sync", "m1")\ns2 = SeqMessage("api", "db", "query", "sync", "m2")\ns3 = SeqMessage("db", "api", "rows", "return", "m3")\n'
        'tiles = Stack([m1, m2], "row", "m", true)\nm1 = Metric("Error rate", "2.4%", "+1.9 pt", "bad")\nm2 = Metric("Queue depth", "12")\n'
        'bars = BarChart(["web", "api", "db"], [31, 82, 12], "CPU", "%")\n'
        'map = GeoMap([g1, g2], [["web", "api"]])\ng1 = GeoPoint("web", 52.5, 13.4)\ng2 = GeoPoint("api", 48.8, 2.3)\n'
        'img = Image("@IMG@", "Latency picture", "A picture")\n'
        'line = LineChart(["Mon", "Tue", "Wed"], [Series("web", [1, 3, 2]), Series("api", [2, 2, 4])])\n'
    ).replace("@IMG@", IMG),
    "tabs": (
        'root = Stack([tabs])\ntabs = Tabs([t1, t2])\n'
        't1 = TabItem("Overview", [a])\na = Text("Overview text lives here.")\n'
        't2 = TabItem("Details", [tb])\ntb = Table(["worker", "jobs"], [["w1", "4"], ["w2", "9"]])\n'
    ),
    "buttons": (
        'root = Stack([ask, actions])\n'
        'ask = Choice("Which node should I restart first?", ["web-1", "web-2"], "Pick one.")\n'
        'actions = Stack([a, b], "row", "s", true)\n'
        'a = Button("Restart web", @ToAssistant("Restart the web service"))\nb = Button("Show logs", @ToAssistant("Show the web logs"))\n'
    ),
    "tip": (
        'root = Stack([t])\nt = Table(["service", "status"], [["web", "up"], ["api", "down"]], [tt])\n'
        'tt = Tooltip("cell:2.status", "Down since noon")\n'
    ),
    "demo": (
        'root = Stack([title, tiles, tbl, bars])\n'
        'title = Markdown("## Service health\\n\\nThe **api** service restarted twice since the last deploy. Queue depth is back to normal.")\n'
        'tiles = Stack([m1, m2, m3], "row", "m", true)\n'
        'm1 = Metric("Error rate", "2.4%", "+1.9 pt", "bad")\nm2 = Metric("Queue depth", "12", "-4", "good")\nm3 = Metric("Workers", "6")\n'
        'tbl = Table(["service", "status", "restarts"], [["web", "up", "0"], ["api", "CrashLoop", "2"], ["worker", "up", "1"]])\n'
        'bars = BarChart(["web", "api", "db", "cache"], [31, 82, 12, 24], "CPU", "%")\n'
    ),
    "ux": (
        'root = Stack([title, tbl, code])\ntitle = Markdown("A short paragraph for the half typed note test.")\n'
        'tbl = Table(["service", "status"], [["web", "up"], ["api", "CrashLoop"], ["db", "up"]])\n'
        'code = CodeBlock("first line\\nsecond line\\nthird line\\nfourth line", "text", "lines.txt")\n'
    ),
    "big": (
        'root = Stack([intro, big])\nintro = Markdown("A big table.")\n'
        'big = Table(["a", "b", "c"], [' + ", ".join('["r%d-a", "r%d-b", "r%d-c"]' % (i, i, i) for i in range(1, 101)) + '])\n'
    ),
    "stale": (
        'root = Stack([title, tbl])\ntitle = Markdown("Stale test heading.")\n'
        'tbl = Table(["service", "status"], [["web", "up"], ["api", "CrashLoop"]])\n'
    ),
    "more": (
        'root = Stack([title, tbl])\ntitle = Markdown("A second draft test heading.")\n'
        'tbl = Table(["service", "status"], [["web", "up"], ["api", "CrashLoop"], ["db", "up"]])\n'
    ),
    "plain": 'root = Stack([p])\np = Markdown("A plain widget that must not change when another widget is in notes mode.")\n',
    "inline": 'root = Stack([Text("An inline text"), Markdown("An inline **markdown**")])\n',
}


# The agent redraws the "stale" widget: the same file, another type for `title` and other text in the table.
STALE_V2 = (
    'root = Stack([title, tbl])\ntitle = Text("Stale test heading.")\n'
    'tbl = Table(["service", "status"], [["web", "up"], ["api", "Recovered"]])\n'
)


def build_page(td, widths, widgets=None, theme="dark", app_css=None, plugin=None, extra_js=""):
    """Writes the native harness page for the named widgets and returns its path."""
    import shoot
    page, lint, _b, _p = shoot.load_modules()
    names = widgets or list(SOURCES)
    cfg = {"widths": list(widths), "widgets": [{"name": n, "source": page.inline_images(SOURCES[n])} for n in names]}
    td = Path(td)
    (td / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
    out = td / "page.html"
    # NOTES_PLUGIN: a mutated copy of the built plugin (mutation checks run the same tests against it)
    cmd = ["node", str(ROOT / "build" / "tests" / "native-harness.mjs"), "--plugin", str(plugin or os.environ.get("NOTES_PLUGIN") or ROOT / "desktop" / "plugin.js"),
           "--config", str(td / "cfg.json"), "--out", str(out), "--theme", theme]
    if app_css:
        cmd += ["--app-css", str(app_css)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise SystemExit("harness build failed:\n" + r.stdout + r.stderr)
    return out


def shoot_page(page, png, width, steps, theme="dark", scale=1, evaluate=None):
    """One Chrome launch through tools/shoot.py. Returns (recorded values of the eval steps, the tool's output text)."""
    cmd = [sys.executable, str(ROOT / "tools" / "shoot.py"), "--html", str(page), str(png), "--theme", theme, "--width", str(width), "--scale", str(scale)]
    if steps:
        cmd += ["--steps", json.dumps(steps)]
    if evaluate:
        cmd += ["--eval", evaluate]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    if r.returncode:
        raise SystemExit("shoot failed:\n" + r.stdout[-3000:] + r.stderr[-3000:])
    got = {}
    for line in r.stdout.splitlines():
        if line.startswith("steps: "):
            got = json.loads(line[len("steps: "):])
        if line.startswith("eval: "):
            got["__eval"] = json.loads(line[len("eval: "):])
    return got, r.stdout


# What the layout test compares with tests/fixtures/notes-layout-baseline.json: per widget and column width, the widget box and the boxes
# of its structural elements (the notes chip's own svg is skipped), and the body height; plus what the pointer hits at the middle of a
# thin line of two diagrams. window.__lay() and window.__hits() are installed by the first step.
LAYOUT_JS = r"""
window.__lay = function () {
  var o = {};
  var r1 = function (n) { return Math.round(n * 10) / 10; };
  document.querySelectorAll('.cell').forEach(function (c) {
    var r = c.querySelector('.hermes-openui-root'), key = c.dataset.widget + '@' + c.querySelector('.slot').style.width;
    if (!r) { o[key] = null; return; }
    var rb = r.getBoundingClientRect(), list = [];
    r.querySelectorAll('table,svg,img,pre,p,figure,h2,hr').forEach(function (e) {
      if (e.closest('[data-oui-notes-ui]')) return;
      var q = e.getBoundingClientRect();
      list.push([e.tagName.toLowerCase(), r1(q.left - rb.left), r1(q.top - rb.top), r1(q.width), r1(q.height)]);
    });
    o[key] = { w: r1(rb.width), h: r1(rb.height), rects: list };
  });
  o.body = r1(document.body.getBoundingClientRect().height);
  return o;
};
window.__all = function () { var o = {}; document.querySelectorAll('.cell').forEach(function (c) { var r = c.querySelector('.hermes-openui-root'); o[c.dataset.widget + '@' + c.querySelector('.slot').style.width] = r ? Math.round(r.getBoundingClientRect().height) : -1; }); o.body = Math.round(document.body.getBoundingClientRect().height); return o; };
window.__hits = function () {
  var cell = Array.prototype.find.call(document.querySelectorAll('.cell'), function (c) { return c.dataset.widget === 'hosts' && c.querySelector('.slot').style.width === '1000px'; });
  var out = {};
  var probe = function (name, path) {
    path.scrollIntoView({ block: 'center' });
    var len = path.getTotalLength(), pt = path.getPointAtLength(len / 2), m = path.getScreenCTM();
    var x = pt.x * m.a + pt.y * m.c + m.e, y = pt.x * m.b + pt.y * m.d + m.f;
    var el = document.elementFromPoint(x, y), t = el, title = false;
    while (t && t !== cell) { if (Array.prototype.some.call(t.children, function (ch) { return ch.tagName.toLowerCase() === 'title'; })) { title = true; break; } t = t.parentNode; }
    out[name] = { tag: el ? el.tagName.toLowerCase() : null, visible_line: el === path, title_ancestor: title, hit_shape: !!(el && el.hasAttribute('data-oui-hit')) };
  };
  probe('seq_m2', cell.querySelector('[data-seq-id="m2"] > path'));
  var t = Array.prototype.find.call(cell.querySelectorAll('svg path > title'), function (e) { return /web\s*\u2192\s*api/.test(e.textContent); });
  probe('infra_web_api', t.parentNode);
  return out;
};
"""
BASELINE_WIDTHS = [360, 700, 1000, 1800]
BASELINE_NAMES = ["text", "hosts", "tabs", "buttons", "plain", "inline", "tip"]


def measure_layout(plugin, app_css, td):
    """One Chrome launch: the layout numbers and the line-hit probe of the plugin file `plugin`."""
    td = Path(td)
    page = build_page(td, BASELINE_WIDTHS, BASELINE_NAMES, app_css=app_css, plugin=plugin)
    steps = [{"js": LAYOUT_JS}, {"eval": "JSON.stringify(__hits())", "name": "hits"}, {"eval": "JSON.stringify(__lay())", "name": "lay"}]
    got, _ = shoot_page(page, td / "lay.png", sum(BASELINE_WIDTHS) + 24 * 4, steps)
    return json.loads(got["lay"]), json.loads(got["hits"])


def write_baseline(plugin, out):
    """Dev-time step (not a test): measure a plugin file drawn WITHOUT Notes and store the numbers the layout test compares against.
    usage: python3 tests/notes_probe.py --baseline PLUGIN.js tests/fixtures/notes-layout-baseline.json"""
    css = _app_css()
    with tempfile.TemporaryDirectory() as td:
        lay, hits = measure_layout(plugin, css, td)
    ua = subprocess.run([sys.executable, "-c", "import platform;print(platform.system())"], capture_output=True, text=True).stdout.strip()
    data = {"_about": "Layout of the widgets of tests/test_notes_native.py drawn by the plugin of release 0.4.0 (before Notes), app stylesheet inlined. Machine bound: fonts and Chrome decide these numbers; the test skips on another platform or stylesheet. Regenerate: python3 tests/notes_probe.py --baseline <plugin file without Notes> <this file>.",
            "platform": ua, "app_css": css.name if css else None, "widths": BASELINE_WIDTHS, "names": BASELINE_NAMES, "layout": lay, "hits": hits}
    Path(out).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _squeeze(path, colors=128):
    """Palette-quantize a picture so it stays well under 100 KB (needs Pillow; without it the file is left as the browser wrote it)."""
    try:
        from PIL import Image
    except ImportError:
        return
    im = Image.open(path).convert("RGB")
    im.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)


def screenshots(outdir, width=652):
    """The documentation pictures (real events, native mode, the app's stylesheet): the dark ones in one Chrome launch, the light tray in a
    second. The column is 652 px and the page has 10 px of padding on each side, so the whole picture is 672 css px = 1344 px at 2x and the
    widget is inside it with its right edge, its chip and its focus rings. Returns the file names."""
    out = Path(outdir)
    hide = "document.head.insertAdjacentHTML('beforeend','<style>.col h2,.label{display:none}.slot{outline:none}.col{margin:0}#page{gap:0}body{padding:10px}</style>')"
    td_status = '[data-oui-id="tbl"] td[data-oui-k="cell:2.status"]'
    common = [
        {"click": td_status},
        {"type": "Is CrashLoop expected here?"},
        {"key": "Enter"},
        {"click": '[data-oui-id="bars"] [data-oui-k="api"]'},
        {"type": "Why is api at 82%?"},
        {"key": "Enter"},
        {"key": "Escape"},
        {"move": [3, 3]},
    ]
    dark = [
        {"js": hide},
        {"move": ".hermes-openui-root", "at": [0.5, 0.45]},
        {"shot": "notes-chip.png"},
        {"click": "[data-oui-chip]"},
        {"move": td_status},
        {"shot": "notes-mode.png"},
        {"drag": '[data-oui-id="title"] p', "from": [0.163, 0.5], "to": [0.53, 0.5]},
        {"type": "Why did it restart twice?"},
        {"shot": "notes-editor.png"},
        {"key": "Enter"},
    ] + common
    light = [{"js": hide}, {"click": "[data-oui-chip]"}, {"drag": '[data-oui-id="title"] p', "from": [0.163, 0.5], "to": [0.53, 0.5]},
             {"type": "Why did it restart twice?"}, {"key": "Enter"}] + common
    with tempfile.TemporaryDirectory() as td:
        page = build_page(td, [width], ["demo"], theme="dark", app_css=_app_css())
        shoot_page(page, out / "notes-tray.png", width + 20, dark, theme="dark", scale=2)
        (Path(td) / "l").mkdir()
        page = build_page(Path(td) / "l", [width], ["demo"], theme="light", app_css=_app_css())
        shoot_page(page, out / "notes-tray-light.png", width + 20, light, theme="light", scale=2)
    names = ["notes-chip.png", "notes-mode.png", "notes-editor.png", "notes-tray.png", "notes-tray-light.png"]
    for n in names:
        _squeeze(out / n)
    return names


def _app_css():
    found = sorted((Path.home() / ".hermes/hermes-agent/apps/desktop/dist/assets").glob("index-*.css"))
    return found[-1] if found else None


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build the notes harness page and run a JS probe in it (one Chrome launch).")
    ap.add_argument("--width", type=int, default=1000)
    ap.add_argument("--eval", dest="evaluate")
    ap.add_argument("--screens", help="write the four documentation pictures into this folder")
    ap.add_argument("--app-css", default=None)
    ap.add_argument("--png", default=None)
    ap.add_argument("--baseline", nargs=2, metavar=("PLUGIN", "OUT"), help="measure a plugin file and write the layout baseline fixture")
    a = ap.parse_args()
    if a.baseline:
        write_baseline(a.baseline[0], a.baseline[1])
        raise SystemExit(0)
    if a.screens:
        print("\n".join(screenshots(a.screens)))
        raise SystemExit(0)
    with tempfile.TemporaryDirectory() as td:
        pg = build_page(td, [a.width], app_css=a.app_css)
        got, text = shoot_page(pg, a.png or str(Path(td) / "o.png"), a.width, None, evaluate=a.evaluate)
        print(text)
