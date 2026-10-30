"""Tooltips on Table, Metric, BarChart, GeoMap and Image (round two of the Tooltip work; the four diagrams are in test_tooltips_builtin.py).

Layers: the pure target tables and checkers under Node (tooltips-core.js, tooltips-check.js); the real validator (`node assets/validate.cjs`);
the markup the five views draw (esbuild bundles the real components, React renders them to a string); the shared interaction module and the
pack sizes; the reference and the docs; the guidance for the agent. What a browser does with a hover, a click or a key is NOT tested here: it was
driven in Chrome with tools/shoot.py --steps (see the report).
"""
import gzip
import hashlib
import html as htmllib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402
import test_tooltips_builtin as base  # noqa: E402

bundle = base.bundle
ROOT, BUILD, SRC, DOCS, EXAMPLES, ENV = base.ROOT, base.BUILD, base.SRC, base.DOCS, base.EXAMPLES, base.ENV
el, T, q, tt = base.el, base.T, base.q, base.tt

KINDS = ("Table", "Metric", "BarChart", "GeoMap", "Image")
RESERVED_WORD = "annot" + "ation"  # reserved for a later feature; written in two pieces so this file does not contain it
ALL_NINE = "Dag, Erd, InfraMap, SequenceDiagram, Table, Metric, BarChart, GeoMap or Image"

# sha256 of the render_widget tool description and parameter text (schemas.py). This branch does not change it: the agent finds the tool by those
# words, and tests/test_plugin.py pins the words. Update the hash only when the description is changed on purpose.
SCHEMA_SHA256 = "769d9ed910df68ae67f4cf505c7148885861e2c2d89a944e0572b8688a493f5d"

# Sizes of the generated files before the packs shared the interaction module, in bytes (gzip).
BEFORE = {"core": 205717, "charts": 64638, "diagrams": 11841, "infra": 13198, "map": 11628, "sequence": 13232, "text": 4750, "plugin": 883633}


# ---- props as the parser hands them to the pure modules ---------------------------------------------------------------

TABLE = {"columns": ["name", "status", "p95.ms"], "rows": [["web", "up", "12"], ["api", "down", "340"], ["db", "up", "7", "extra"]]}
DUP_TABLE = {"columns": ["a", "a"], "rows": [["1", "2"]]}
GEO = {
    "points": [el("GeoPoint", label="web", lat=1, lon=2), el("GeoPoint", label="api", lat=3, lon=4), el("GeoPoint", label="db", lat=5, lon=6)],
    "links": [["web", "api"], ["web", "api"], ["web", "ghost"], ["api", "api"], ["api", "db"]],
}

def skeleton(markup):
    """The structure of some markup: the opening and closing tag names in order (runs collapsed as `div*3`), the few attributes that change
    what is drawn (`src`, `alt`, the map hook), and the text. Styles, ids and every other attribute are left out on purpose, so a style tweak
    or a React upgrade (its useId string) does not fail the suite; a tag that appears, goes or moves does."""
    tags, texts = [], []
    for m in re.finditer(r"<(/?)([A-Za-z][\w:-]*)((?:\s[^>]*)?)>|([^<]+)", markup):
        closing, name, attrs, text = m.groups()
        if name:
            if closing:
                tok = "/" + name
            else:
                keep = ["%s=%s" % (a, v) for a, v in re.findall(r'\s(data-hermes-openui-map|src|alt|colspan)="([^"]*)"', attrs)]
                tok = name + ("[" + ";".join(keep) + "]" if keep else "")
            if tags and tags[-1][0] == tok:
                tags[-1][1] += 1
            else:
                tags.append([tok, 1])
        elif text.strip():
            texts.append(htmllib.unescape(text.strip()))
    return {"tags": [t if n == 1 else "%s*%d" % (t, n) for t, n in tags], "text": texts}


HARNESS = r"""
const cfg = JSON.parse(process.env.TIP_CFG);
const core = await import(cfg.core);
const check = await import(cfg.check);
const out = {};
out.targets = cfg.targets.map((c) => core.targetSummary(c.kind, c.props));
out.checks = cfg.checks.map((c) => check.checkTooltips(c.kind, c.props));
out.hosts = core.TIP_HOSTS;
out.stray = [check.strayTooltip("t1"), check.strayTooltip(undefined)];
out.flows = (cfg.flows || []).map((f) => core.rowFlow(f));
out.hints = {
  skipped: check.misplacedListHint("BarChart", "t7"),
  skippedAll: core.TIP_HOSTS.map((k) => check.misplacedListHint(k, "t1")),
  nonHost: check.misplacedListHint("Markdown", "t1"),
  orphan: check.orphanTooltipHint(),
  holds: (cfg.holds || []).map(([text, names]) => check.holdsTooltipList(text, names)),
};
process.stdout.write(JSON.stringify(out));
"""


def run_pure(cfg):
    cfg = dict(cfg, core=(SRC / "components" / "tooltips-core.js").as_uri(), check=(SRC / "components" / "tooltips-check.js").as_uri())
    r = subprocess.run(["node", "--input-type=module", "-e", HARNESS], capture_output=True, text=True, timeout=60, env=dict(ENV, TIP_CFG=json.dumps(cfg)))
    if r.returncode != 0:
        raise AssertionError("node harness failed:\n" + (r.stderr or r.stdout)[-2000:])
    return json.loads(r.stdout)


@unittest.skipUnless(base.node_ok(), "needs Node")
class PureModules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tips = lambda *ts: [T(t, hint="x") for t in ts]  # noqa: E731
        cls.cfg = {
            "targets": [
                {"kind": "Table", "props": TABLE}, {"kind": "Table", "props": DUP_TABLE},
                {"kind": "Metric", "props": {"label": "Latency", "value": "1"}}, {"kind": "Metric", "props": {"label": "", "value": "1"}},
                {"kind": "BarChart", "props": {"labels": ["web", "api", "web", ""], "values": [1, 2, 3, 4]}},
                {"kind": "GeoMap", "props": GEO}, {"kind": "Image", "props": {"src": "x.png"}},
            ],
            "checks": [
                {"kind": "Table", "props": dict(TABLE, tooltips=tips("row:2", "col:status", "cell:2.status", "cell:1.p95.ms"))},
                {"kind": "Table", "props": dict(TABLE, tooltips=tips("row:0", "row:4", "col:nope", "cell:2.nope", "cell:9.name", "status"))},
                {"kind": "Table", "props": dict(DUP_TABLE, tooltips=tips("col:a", "cell:1.a", "row:1"))},
                {"kind": "Table", "props": dict(TABLE, tooltips=tips("row:2", "row:2"))},
                {"kind": "Metric", "props": {"label": "Latency", "value": "1", "tooltips": tips("Latency")}},
                {"kind": "Metric", "props": {"label": "Latency", "value": "1", "tooltips": tips("Latency", "Other")}},
                {"kind": "Metric", "props": {"label": "Latency", "value": "1", "tooltips": tips("Latency", "Latency")}},
                {"kind": "BarChart", "props": {"labels": ["web", "api", "web"], "values": [1, 2, 3], "tooltips": tips("api", "web", "zzz")}},
                {"kind": "GeoMap", "props": dict(GEO, tooltips=tips("web", "api>db", "web>api", "web>ghost", "api>api", "nowhere"))},
                {"kind": "Image", "props": {"src": "x", "tooltips": tips("image")}},
                {"kind": "Image", "props": {"src": "x", "tooltips": tips("picture")}},
                {"kind": "Table", "props": {"columns": ["v1.2", "v1.2"], "rows": [["a", "b"]], "tooltips": tips("col:v1.2", "cell:1.v1.2")}},
                {"kind": "Image", "props": {"src": "x", "tooltips": tips("image", "picture")}},
            ],
            "flows": [
                {"display": "flex", "flexDirection": "row", "flexWrap": "wrap", "rowGap": "12px"},
                {"display": "flex", "flexDirection": "row", "flexWrap": "wrap", "rowGap": "normal"},
                {"display": "inline-flex", "flexDirection": "row-reverse", "flexWrap": "wrap-reverse", "rowGap": "4px"},
                {"display": "flex", "flexDirection": "row", "flexWrap": "nowrap", "rowGap": "12px"},
                {"display": "flex", "flexDirection": "column", "flexWrap": "wrap", "rowGap": "12px"},
                {"display": "block", "flexDirection": "row", "flexWrap": "wrap", "rowGap": "12px"},
                None,
            ],
            "holds": [
                ['c = Markdown("hi", [t1])', ["t1"]], ['c = Markdown("hi", [ t1, t2 ])', ["t2"]], ['c = Text("hi", null, [Tooltip("a", "b")])', []],
                ['c = Text("a [t1] b")', ["t1"]], ['c = Text("hi", [other])', ["t1"]], ['c = Card([x, y])', ["t1"]], ["", ["t1"]],
            ],
        }
        cls.r = run_pure(cls.cfg)

    def test_the_table_targets_are_rows_columns_and_cells_and_a_header_may_contain_a_dot(self):
        t = self.r["targets"][0]
        for key in ("col:name", "col:status", "col:p95.ms", "row:1", "row:2", "row:3", "cell:1.name", "cell:2.status", "cell:3.p95.ms", "cell:1.p95.ms"):
            self.assertEqual(len(t["count"].get(key, [])), 1, key)
        self.assertNotIn("cell:3.undefined", t["count"])
        self.assertEqual(len([k for k in t["keys"] if k.startswith("cell:3.")]), 3, "an extra cell with no header is not a target")
        self.assertEqual(t["keys"][:3], ["col:name", "col:status", "col:p95.ms"], "columns come first, so the first five valid targets show the forms")

    def test_duplicate_headers_make_col_and_cell_targets_ambiguous(self):
        t = self.r["targets"][1]
        self.assertEqual(t["count"]["col:a"], ["column", "column"])
        self.assertEqual(t["count"]["cell:1.a"], ["cell", "cell"])
        self.assertEqual(t["count"]["row:1"], ["row"])

    def test_metric_bar_and_image_targets(self):
        self.assertEqual(self.r["targets"][2]["keys"], ["Latency"])
        self.assertEqual(self.r["targets"][3]["keys"], [], "a Metric with no label has nothing a tooltip can name")
        bar = self.r["targets"][4]
        self.assertEqual(bar["count"]["web"], ["bar", "bar"])
        self.assertEqual(bar["count"]["api"], ["bar"])
        self.assertEqual(bar["keys"], ["web", "api"], "an empty label cannot be a target")
        self.assertEqual(self.r["targets"][6]["keys"], ["image"])

    def test_geomap_targets_are_point_labels_and_link_pairs_between_points(self):
        g = self.r["targets"][5]
        self.assertEqual(g["keys"], ["web", "api", "db", "web>api", "api>db"])
        self.assertEqual(g["count"]["web>api"], ["link", "link"])
        self.assertEqual(g["ends"]["web>api"], [["web", "api"], ["web", "api"]])
        self.assertNotIn("web>ghost", g["count"])
        self.assertNotIn("api>api", g["count"])

    def test_good_targets_pass_the_pure_checker(self):
        for n in (0, 4, 9):
            self.assertEqual(self.r["checks"][n], [], n)
        self.assertEqual(self.r["checks"][8], [x for x in self.r["checks"][8] if "api>api" in x or "nowhere" in x or "web>ghost" in x or "ambiguous" in x])

    def test_unknown_targets_name_the_target_list_five_valid_ones_and_say_the_forms(self):
        msgs = self.r["checks"][1]
        self.assertEqual(len(msgs), 6, msgs)
        for target in ("row:0", "row:4", "col:nope", "cell:2.nope", "cell:9.name", "status"):
            m = [x for x in msgs if "`%s`" % target in x]
            self.assertEqual(len(m), 1, (target, msgs))
            self.assertTrue(m[0].startswith("Table tooltip target "), m[0])
            self.assertIn("matches no element", m[0])
            self.assertIn("valid targets: col:name, col:status, col:p95.ms, row:1, row:2 and 10 more", m[0])
            self.assertIn("row:N, col:HEADER or cell:N.HEADER", m[0], "the message says which forms exist")

    def test_ambiguous_and_duplicate_targets(self):
        amb = self.r["checks"][2]
        self.assertEqual(len(amb), 2, amb)
        self.assertTrue(any("`col:a` is ambiguous" in m and "2 columns are headed `a`" in m for m in amb), amb)
        self.assertTrue(any("`cell:1.a` is ambiguous" in m and "2 columns are headed `a`" in m for m in amb), amb)
        self.assertEqual(self.r["checks"][3], ["Table has more than one tooltip for target `row:2` (keep one Tooltip per element)."])
        bar = self.r["checks"][7]
        self.assertEqual(len(bar), 2, bar)
        self.assertTrue(any("`web` is ambiguous" in m and "2 bars are labelled `web`" in m for m in bar), bar)
        self.assertTrue(any("`zzz` matches no element" in m and "valid targets: web, api" in m for m in bar), bar)
        geo = self.r["checks"][8]
        self.assertTrue(any("`web>api` is ambiguous" in m and "2 links join `web` to `api`" in m for m in geo), geo)
        for target in ("web>ghost", "api>api", "nowhere"):
            self.assertTrue(any("`%s` matches no element" % target in m for m in geo), (target, geo))
        self.assertFalse(any(m.startswith("GeoMap tooltip target `web` ") or m.startswith("GeoMap tooltip target `api>db` ") for m in geo), "valid targets are not reported")

    def test_a_metric_and_an_image_take_one_tooltip_at_most(self):
        self.assertEqual(self.r["checks"][4], [])
        two = self.r["checks"][5]
        self.assertTrue(any("Metric takes one tooltip at most" in m and "`Latency`" in m for m in two), two)
        self.assertTrue(any("`Other` matches no element" in m and "valid targets: Latency" in m for m in two), two)
        self.assertEqual(self.r["checks"][6], ["Metric has more than one tooltip for target `Latency` (keep one Tooltip per element)."])
        self.assertTrue(any("`picture` matches no element" in m and "valid targets: image" in m for m in self.r["checks"][10]), self.r["checks"][10])

    def test_a_duplicate_header_with_a_dot_is_named_whole_in_the_message(self):
        msgs = self.r["checks"][11]
        self.assertEqual(len(msgs), 2, msgs)
        for m in msgs:
            self.assertIn("2 columns are headed `v1.2`", m)
            self.assertNotIn("headed `2`", m)
            self.assertNotIn("headed `1.2`", m)

    def test_an_image_takes_one_tooltip_at_most(self):
        msgs = self.r["checks"][12]
        self.assertTrue(any("Image takes one tooltip at most" in m and "`image`" in m for m in msgs), msgs)

    def test_a_row_that_wraps_is_told_apart_from_every_other_parent(self):
        flows = self.r["flows"]
        self.assertEqual(flows[0], {"gap": 12})
        self.assertEqual(flows[1], {"gap": 0}, "a gap of `normal` is no gap")
        self.assertEqual(flows[2], {"gap": 4}, "a reversed row that wraps is a row that wraps too")
        self.assertEqual(flows[3:], [None, None, None, None], "a row that does not wrap, a column, a block and nothing at all keep the panel under its tile")

    def test_the_hints_for_a_misplaced_tooltip_list(self):
        h = self.r["hints"]
        self.assertEqual(h["skipped"], "`tooltips` is the LAST argument: write `null` for each skipped optional argument before it, for example `BarChart(labels, values, null, null, [t7])`.")
        for kind, text in zip(self.r["hosts"], h["skippedAll"]):
            with self.subTest(kind=kind):
                self.assertIn("write `null`", text)
                self.assertIn("`" + kind + "(", text)
                self.assertIn("[t1])`", text)
        self.assertIn("Markdown takes no tooltips", h["nonHost"])
        for text in (h["nonHost"], h["orphan"]):
            self.assertIn("of " + ALL_NINE, text)
        self.assertEqual(h["holds"], [True, True, True, False, False, False, False])

    def test_the_free_standing_rule_lists_every_component_that_takes_tooltips(self):
        self.assertEqual(self.r["hosts"], ["Dag", "Erd", "InfraMap", "SequenceDiagram", "Table", "Metric", "BarChart", "GeoMap", "Image"])
        for m in self.r["stray"]:
            self.assertIn("of " + ALL_NINE, m)
            self.assertIn("outside a component that takes tooltips", m)
        self.assertTrue(self.r["stray"][0].startswith("Tooltip `t1` is used outside"))
        self.assertTrue(self.r["stray"][1].startswith("A Tooltip written inline is used outside"))


# ---- the real validator ---------------------------------------------------------------------------------------------------

def table_src(*tips, dup=False):
    cols = '["a", "a"]' if dup else '["name", "status", "p95.ms"]'
    rows = '[["1", "2"]]' if dup else '[["web", "up", "12"], ["api", "down", "340"]]'
    return "root = Stack([t])\nt = Table(%s, %s, [%s])\n" % (cols, rows, ", ".join(tips))


def metric_src(*tips):
    return 'root = Stack([m])\nm = Metric("Latency", "120 ms", null, null, [%s])\n' % ", ".join(tips)


def bar_src(*tips):
    return 'root = Stack([b])\nb = BarChart(["web", "api", "db"], [3, 5, 2], null, null, [%s])\n' % ", ".join(tips)


def geo_src(*tips, extra_link=False):
    links = '[["web", "api"], ["api", "db"]' + (', ["web", "api"]' if extra_link else "") + "]"
    return ('root = Stack([m])\nm = GeoMap([p1, p2, p3], %s, null, [%s])\n' % (links, ", ".join(tips))
            + 'p1 = GeoPoint("web", 52.5, 13.4)\np2 = GeoPoint("api", 48.8, 2.3)\np3 = GeoPoint("db", 40.4, -3.7)\n')


def image_src(*tips):
    return 'root = Stack([i])\ni = Image("data:image/gif;base64,R0lGODlhAQABAAAAACw=", null, null, [%s])\n' % ", ".join(tips)


@unittest.skipUnless(base.node_ok() and bundle.VALIDATOR.is_file(), "needs Node and assets/validate.cjs")
class Validator(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)

    def check(self, text):
        rc, out = base.validate(text, self.td.name)
        return rc, base.problems_of(out), out

    def ok(self, text):
        rc, problems, out = self.check(text)
        self.assertEqual((rc, problems), (0, []), out)

    def bad(self, text, *needles):
        rc, problems, out = self.check(text)
        self.assertEqual(rc, 1, out)
        for n in needles:
            self.assertTrue(any(n in p for p in problems), "%r not in %r" % (n, problems))
        return problems

    def test_valid_targets_for_all_five_pass(self):
        self.ok(table_src(tt("row:2", "Failed"), tt("col:status", "State"), tt("cell:1.p95.ms", "Fast")))
        self.ok(metric_src(tt("Latency", "p95 over 5 min")))
        self.ok(bar_src(tt("api", "Busiest"), tt("db", "Idle")))
        self.ok(geo_src(tt("web", "Frankfurt"), tt("web>api", "Fibre"), tt("api>db", "Backup")))
        self.ok(image_src(tt("image", "A pixel")))

    def test_optional_arguments_before_tooltips_are_null_and_the_last_argument_is_tooltips(self):
        self.ok('root = Stack([m])\nm = Metric("Latency", "120 ms", "+3 ms", "bad", [t])\nt = ' + tt("Latency", "x") + "\n")
        self.ok('root = Stack([b])\nb = BarChart(["a"], [1], "Load", "%", [t])\nt = ' + tt("a", "x") + "\n")
        self.ok('root = Stack([i])\ni = Image("data:image/gif;base64,R0lGODlhAQABAAAAACw=", "alt", "cap", [t])\nt = ' + tt("image", "x") + "\n")
        self.ok('root = Stack([m])\nm = GeoMap([p1], null, "Title", [t])\np1 = GeoPoint("web", 1, 2)\nt = ' + tt("web", "x") + "\n")

    def test_an_unknown_target_names_it_and_lists_up_to_five_valid_ones(self):
        p = self.bad(table_src(tt("cell:2.nope", "x")), "Table tooltip target `cell:2.nope` matches no element", "valid targets: col:name, col:status, col:p95.ms, row:1, row:2 and 6 more", "row:N, col:HEADER or cell:N.HEADER")
        self.assertEqual(len(p), 1, p)
        self.bad(metric_src(tt("Speed", "x")), "Metric tooltip target `Speed` matches no element", "valid targets: Latency")
        self.bad(bar_src(tt("cache", "x")), "BarChart tooltip target `cache` matches no element", "valid targets: web, api, db")
        self.bad(geo_src(tt("cache", "x")), "GeoMap tooltip target `cache` matches no element", "valid targets: web, api, db, web>api, api>db")
        self.bad(image_src(tt("picture", "x")), "Image tooltip target `picture` matches no element", "valid targets: image")

    def test_duplicate_and_ambiguous_targets(self):
        self.bad(table_src(tt("row:1", "a"), tt("row:1", "b")), "Table has more than one tooltip for target `row:1`")
        self.bad(table_src(tt("col:a", "a"), dup=True), "`col:a` is ambiguous", "2 columns are headed `a`")
        self.bad(table_src(tt("cell:1.a", "a"), dup=True), "`cell:1.a` is ambiguous")
        self.bad(geo_src(tt("web>api", "a"), extra_link=True), "GeoMap tooltip target `web>api` is ambiguous", "2 links join `web` to `api`")
        self.bad('root = Stack([b])\nb = BarChart(["a", "a"], [1, 2], null, null, [' + tt("a", "x") + "])\n", "`a` is ambiguous", "2 bars are labelled `a`")
        self.bad(metric_src(tt("Latency", "a"), tt("Other", "b")), "Metric takes one tooltip at most")

    def test_the_limits_and_the_link_rules_are_the_diagrams(self):
        self.bad(metric_src(tt("Latency", "x" * 141)), "hint is 141 characters; the limit is 140")
        self.bad(metric_src(tt("Latency", "x", link="javascript:alert(1)")), "uses the javascript: scheme")
        self.bad(image_src(tt("image", "x", link="https://\u0430pple.com/")), "U+0430")
        self.bad(metric_src(tt("Latency")), "has none of hint, detail, code or link")
        self.bad(bar_src(*[tt("a%d" % i, "x") for i in range(61)]), "has 61 tooltips; use at most 60")

    def test_a_tooltip_anywhere_else_is_the_free_standing_error_and_lists_all_nine(self):
        for src in ('root = Stack([t1])\nt1 = Tooltip("x", "y")\n',
                    'root = Stack([c])\nc = Card([t1], "T")\nt1 = Tooltip("x", "y")\n',
                    'root = Stack([b, t1])\nb = Button("go")\nt1 = Tooltip("x", "y")\n',
                    'root = Stack([b])\nb = Tabs([i])\ni = TabItem("one", [t1])\nt1 = Tooltip("x", "y")\n'):
            with self.subTest(src=src):
                p = [x for x in self.check(src)[1] if "Tooltip `t1`" in x and "outside" in x]
                self.assertEqual(len(p), 1, self.check(src)[2])
                self.assertIn("of " + ALL_NINE, p[0])

    # A Tooltip list written in the trailing slot of a component that takes no tooltips, or left in a slot of the wrong type because an
    # optional argument was skipped: the agent gets the rule, not only an arity or a type error.
    NO_TIPS = {
        "Markdown": 'c = Markdown("hi", [t1])', "CodeBlock": 'c = CodeBlock("x = 1", "python", "T", [t1])', "CodeBlock, skipped": 'c = CodeBlock("x = 1", [t1])',
        "Callout": 'c = Callout("hi", "info", [t1])', "Faq": 'c = Faq([f], true, [t1])\nf = FaqItem("q", "a")', "Choice": 'c = Choice("q", ["a", "b"], "h", [t1])',
        "Button": 'c = Button("go", null, [t1])', "Tabs": 'c = Tabs([i], [t1])\ni = TabItem("one", [])', "Stack": 'c = Stack([], "row", "m", true, [t1])',
        "LineChart": 'c = LineChart(["a", "b"], [s], "linear", null, null, null, [t1])\ns = Series("x", [1, 2])',
        "AreaChart": 'c = AreaChart(["a", "b"], [s], "linear", null, null, null, [t1])\ns = Series("x", [1, 2])',
        "PieChart": 'c = PieChart(["a", "b"], [1, 2], "pie", "circular", [t1])', "RadarChart": 'c = RadarChart(["a", "b"], [s], [t1])\ns = Series("x", [1, 2])',
        "Text": 'c = Text("hi", "body", [t1])', "Card": 'c = Card([], "T", [t1])', "Markdown, inline": 'c = Markdown("hi", [Tooltip("x", "y")])',
    }

    def test_a_tooltip_list_in_the_last_slot_of_a_component_without_tooltips_names_the_nine_hosts(self):
        for name, stmt in self.NO_TIPS.items():
            with self.subTest(component=name):
                src = "root = Stack([c])\n" + stmt + '\nt1 = Tooltip("x", "y")\n'
                rc, problems, out = self.check(src)
                self.assertEqual(rc, 1, out)
                self.assertTrue(any("takes no tooltips" in p and "of " + ALL_NINE in p for p in problems), problems)

    SKIPPED = {
        "BarChart": ('c = BarChart(["a", "b"], [1, 2], [t1])', "a", "BarChart(labels, values, null, null, [t1])"),
        "Image": ('c = Image("data:image/gif;base64,R0lGODlhAQABAAAAACw=", [t1])', "image", "Image(src, null, null, [t1])"),
        "GeoMap": ('c = GeoMap([p], "Title", [t1])\np = GeoPoint("web", 1, 2)', "web", "GeoMap(points, null, null, [t1])"),
        "Metric": ('c = Metric("L", "1", [t1])', "L", "Metric(label, value, null, null, [t1])"),
        "Erd": ('c = Erd([e], [], [t1])\ne = Entity("users", ["id uuid PK"])', "users", "Erd(entities, relations, null, [t1])"),
        "InfraMap": ('c = InfraMap([z], [], [t1])\nz = InfraZone("Core", [n])\nn = InfraNode("a", "A")', "a", "InfraMap(zones, links, null, null, [t1])"),
        "SequenceDiagram": ('c = SequenceDiagram([p], [], [t1])\np = SeqParticipant("a", "A")', "a", "SequenceDiagram(participants, steps, null, null, [t1])"),
        "Table, one list too many": ('c = Table(["a"], [["1"]], [t1], [t1])', "row:1", "Table(columns, rows, [t1])"),
    }

    def test_skipped_optional_arguments_before_tooltips_get_the_write_null_rule_with_an_example_for_the_component(self):
        for name, (stmt, target, example) in self.SKIPPED.items():
            with self.subTest(component=name):
                src = "root = Stack([c])\n" + stmt + '\nt1 = Tooltip("%s", "y")\n' % target
                rc, problems, out = self.check(src)
                self.assertEqual(rc, 1, out)
                self.assertTrue(any("`tooltips` is the LAST argument" in p and "write `null` for each skipped optional argument" in p and "`" + example + "`" in p for p in problems), problems)

    def test_an_unreachable_tooltip_gets_the_nine_host_sentence(self):
        problems = self.check('root = Stack([c])\nc = Text("hi")\nt1 = Tooltip("x", "y")\n')[1]
        hit = [p for p in problems if p.startswith("`t1` is defined but not reachable from root")]
        self.assertEqual(len(hit), 1, problems)
        self.assertIn("of " + ALL_NINE, hit[0])
        other = self.check('root = Stack([c])\nc = Text("hi")\nu = Text("x")\n')[1]
        self.assertTrue(any("`u` is defined but not reachable" in p and "Tooltip" not in p for p in other), other)

    def test_a_tooltip_in_the_tooltips_of_a_library_chart_is_not_accepted(self):
        src = 'root = Stack([c])\nc = LineChart(["a", "b"], [s], null, null, null, null, [t1])\ns = Series("x", [1, 2])\nt1 = Tooltip("a", "y")\n'
        rc, problems, out = self.check(src)
        self.assertEqual(rc, 1, out)

    def test_without_tooltips_nothing_changes(self):
        self.ok('root = Stack([t, m, b, i])\nt = Table(["a"], [["1"]])\nm = Metric("L", "1")\nb = BarChart(["a"], [1])\ni = Image("data:image/gif;base64,R0lGODlhAQABAAAAACw=")\n')


# ---- the markup the five views draw ---------------------------------------------------------------------------------------

PIXEL = "data:image/gif;base64,R0lGODlhAQABAAAAACw="
PLAIN = {
    "table": 'root = Stack([x])\nx = Table(["name", "status"], [["web", "up"], ["api", "down"]])\n',
    "metric": 'root = Stack([x])\nx = Metric("Latency", "120 ms", "+3 ms", "bad")\n',
    "bar": 'root = Stack([x])\nx = BarChart(["web", "api", "db"], [3, 5, 2], "Load", "%")\n',
    "geo": 'root = Stack([x])\nx = GeoMap([p1, p2], [["web", "api"]], "Regions")\np1 = GeoPoint("web", 52.5, 13.4, "good")\np2 = GeoPoint("api", 48.8, 2.3)\n',
    "image": 'root = Stack([x])\nx = Image("%s", "a pixel", "A pixel")\n' % PIXEL,
}
TIPPED = {
    "table": 'root = Stack([x])\nx = Table(["name", "status"], [["web", "up"], ["api", "down"]], [a, b, c])\n'
             'a = Tooltip("row:2", "Failed since noon", "Restart it.", null, null, "bad")\nb = Tooltip("col:status", "Up or down")\nc = Tooltip("cell:1.name", "The front door", null, null, null, "good")\n',
    "metric": 'root = Stack([x])\nx = Metric("Latency", "120 ms", "+3 ms", "bad", [a])\na = Tooltip("Latency", "p95 over five minutes", null, null, null, "warn")\n',
    "bar": 'root = Stack([x])\nx = BarChart(["web", "api", "db"], [3, 5, 2], "Load", "%", [a, b])\na = Tooltip("api", "Busiest", null, null, null, "warn")\nb = Tooltip("db", "Idle")\n',
    "geo": 'root = Stack([x])\nx = GeoMap([p1, p2], [["web", "api"]], "Regions", [a, b])\np1 = GeoPoint("web", 52.5, 13.4, "good")\np2 = GeoPoint("api", 48.8, 2.3)\n'
           'a = Tooltip("web", "Frankfurt", null, null, null, "good")\nb = Tooltip("web>api", "Fibre link", null, null, null, "bad")\n',
    "image": 'root = Stack([x])\nx = Image("%s", "a pixel", "A pixel", [a])\na = Tooltip("image", "The whole picture", null, null, null, "good")\n' % PIXEL,
}

RENDER_HARNESS = r"""
const path = require("path");
const cfg = JSON.parse(process.env.TIP_CFG);
const req = require("module").createRequire(path.join(cfg.build, "package.json"));
const esbuild = req("esbuild");
const entry = [
  'import React from "react";',
  'import { renderToStaticMarkup } from "react-dom/server";',
  'import * as lang from "@openuidev/react-lang";',
  'import { createParser } from "@openuidev/lang-core";',
  'import { coreComponents } from "./core-components.jsx";',
  'import { pack as map } from "./packs/map.jsx";',
  'export { React, renderToStaticMarkup, lang, createParser, coreComponents, map };',
].join("\n");
const built = esbuild.buildSync({
  stdin: { contents: entry, resolveDir: path.join(cfg.build, "src"), loader: "js", sourcefile: "tip-harness.js" },
  bundle: true, platform: "node", format: "cjs", jsx: "automatic", write: false, logLevel: "error",
  define: { "process.env.NODE_ENV": '"production"' },
});
const mod = { exports: {} };
new Function("module", "exports", "require", built.outputFiles[0].text)(mod, mod.exports, require);
const { React, renderToStaticMarkup, lang, createParser, coreComponents, map } = mod.exports;
const all = [].concat(coreComponents, map.components);
const library = lang.createLibrary({ root: "Stack", components: all });
const parser = createParser(library.toJSONSchema(), library.root);
const out = {};
const walk = (n, fn) => { if (n && typeof n === "object") { if (n.typeName) fn(n); for (const v of Object.values(n.props || {})) (Array.isArray(v) ? v : [v]).forEach((c) => walk(c, fn)); } };
for (const [name, src] of Object.entries(cfg.sources)) {
  const { root, meta } = parser.parse(src);
  const ex = { parsed: !!root, errors: (meta.errors || []).map((e) => e.message || String(e)), unresolved: meta.unresolved, html: "" };
  walk(root, (n) => {
    const comp = all.find((c) => c.name === n.typeName);
    if (comp && ["Table", "Metric", "BarChart", "GeoMap", "Image"].includes(n.typeName)) ex.html = renderToStaticMarkup(React.createElement(comp.component, { props: n.props }));
  });
  out[name] = ex;
}
process.stdout.write(JSON.stringify(out));
"""


def render(sources):
    r = subprocess.run(["node", "-"], input=RENDER_HARNESS, capture_output=True, text=True, cwd=str(BUILD), timeout=120, env=dict(ENV, TIP_CFG=json.dumps({"build": str(BUILD), "sources": sources})))
    if r.returncode != 0:
        raise AssertionError("node render harness failed:\n" + (r.stderr or r.stdout)[-2000:])
    return json.loads(r.stdout)


@unittest.skipIf(base.node_missing_reason(), base.node_missing_reason() or "")
class Markup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources = {"plain_" + k: v for k, v in PLAIN.items()}
        sources.update({"tip_" + k: v for k, v in TIPPED.items()})
        cls.r = render(sources)
        cls.baseline = json.loads((Path(__file__).resolve().parent / "fixtures" / "tooltips-more-baseline.json").read_text(encoding="utf-8"))

    def html(self, name):
        ex = self.r[name]
        self.assertTrue(ex["parsed"], ex)
        self.assertEqual((ex["unresolved"], ex["errors"]), ([], []), ex)
        self.assertTrue(ex["html"], name)
        return ex["html"]

    def tags(self, html, key):
        return re.findall(r'<(?:g|div|tr|td|th)[^>]*data-tip="%s"[^>]*>' % re.escape(key.replace("&", "&amp;").replace(">", "&gt;")), html)

    def test_without_tooltips_the_five_have_the_structure_they_had_before(self):
        # tests/fixtures/tooltips-more-baseline.json holds the skeleton (tag names in order, the attributes that decide what is drawn, the text)
        # of the five components WITHOUT tooltips, captured from the code before tooltips existed. It protects "a component with no tooltips
        # draws as it always did": no extra wrapper, no new tag, no tooltip attribute. Styles and ids are not compared on purpose.
        for k in PLAIN:
            with self.subTest(component=k):
                html = self.html("plain_" + k)
                self.assertEqual(skeleton(html), self.baseline[k], "the structure of a %s without tooltips changed" % k)
                for needle in ("data-tip", "tabindex", "role=", "aria-"):
                    self.assertNotIn(needle, html)

    def test_every_tooltip_element_outside_a_table_is_a_focusable_button_with_a_label_and_a_dot(self):
        want = {"metric": ["Latency"], "bar": ["api", "db"], "geo": ["web", "web>api"], "image": ["image"]}
        for k, keys in want.items():
            html = self.html("tip_" + k)
            for key in keys:
                with self.subTest(component=k, target=key):
                    tags = self.tags(html, key)
                    self.assertEqual(len(tags), 1, (key, tags))
                    tag = tags[0]
                    self.assertIn('tabindex="0"', tag)
                    self.assertIn('role="button"', tag)
                    self.assertIn("aria-label=", tag)
                    self.assertIn('aria-expanded="false"', tag)
                    self.assertIn("cursor:pointer", tag)
            self.assertEqual(html.count('role="button"'), len(keys), k)
            self.assertEqual(html.count("data-tip-dot"), len(keys), "one dot for each tooltip")

    def test_table_parts_with_a_tooltip_keep_their_native_role_and_are_not_buttons(self):
        html = self.html("tip_table")
        self.assertEqual(html.count("role="), 0, "a row, a header and a cell keep the role the table gives them (no role override, so no button inside a button)")
        self.assertNotIn("aria-label=", html, "the content of a cell stays its name")
        for key, tag, expanded in (("row:2", "tr", "false"), ("col:status", "th", "false"), ("cell:1.name", "td", None)):
            with self.subTest(target=key):
                tags = self.tags(html, key)
                self.assertEqual(len(tags), 1, (key, tags))
                self.assertTrue(tags[0].startswith("<" + tag + " "), tags[0])
                self.assertIn('tabindex="0"', tags[0])
                self.assertIn("cursor:pointer", tags[0])
                if expanded:
                    self.assertIn('aria-expanded="%s"' % expanded, tags[0], "a row and a column header support aria-expanded")
                else:
                    self.assertNotIn("aria-expanded", tags[0], "a plain cell does not support aria-expanded")
        self.assertEqual(html.count("data-tip-dot"), 3, "one dot for each tooltip")

    def test_a_table_dot_sits_right_after_the_text_of_its_row_header_or_cell(self):
        html = self.html("tip_table")
        for key, text in (("col:status", "status"), ("cell:1.name", "web"), ("row:2", "api")):
            with self.subTest(target=key):
                dot = re.search(re.escape(text) + r'<span[^>]*data-tip-dot[^>]*>', html)
                self.assertIsNotNone(dot, "the dot follows the text %r" % text)
                self.assertIn("display:inline-block", dot.group(0))
                self.assertNotIn("position:absolute", dot.group(0), "an inline dot stays next to its text in a wide cell")
                self.assertIn("vertical-align:middle", dot.group(0))

    def test_a_bar_dot_sits_inside_the_bar_at_its_top_so_it_never_touches_the_value_or_the_label(self):
        html = self.html("tip_bar")
        col = re.search(r'<div[^>]*data-tip="api"[^>]*>(.*?)</div></div>', html, re.S)
        self.assertIsNotNone(col, html)
        inner = col.group(1)
        # column: value label, then the bar (which holds the dot), then the label
        order = [m.group(0) for m in re.finditer(r'font-size:11px|data-tip-dot|background:var\(--accent', inner)]
        self.assertEqual(order, ["font-size:11px", "background:var(--accent", "data-tip-dot", "font-size:11px"], order)
        dot = re.search(r'<span[^>]*data-tip-dot[^>]*>', inner).group(0)
        self.assertIn("left:50%", dot)
        self.assertIn("top:1px", dot)
        self.assertNotIn("right:", dot)
        self.assertIn("position:relative", re.search(r'<div[^>]*background:var\(--accent[^>]*>', inner).group(0))
        plain = self.html("plain_bar")
        self.assertNotIn("position:relative", plain)

    def test_the_dot_is_in_the_tone_colour_and_ignores_the_pointer(self):
        html = self.html("tip_metric")
        dot = re.search(r"<(?:span|circle)[^>]*data-tip-dot[^>]*>", html).group(0)
        self.assertIn("#d29922", dot)
        self.assertRegex(dot, r"pointer-events:\s*none|pointer-events=\"none\"")
        self.assertIn('aria-hidden="true"', dot)

    def test_a_table_row_stays_a_real_tr_and_the_table_stays_valid_html(self):
        html = self.html("tip_table")
        self.assertRegex(html, r"<tbody>(<tr[ >].*?</tr>)+</tbody>")
        self.assertNotRegex(html, r"<tbody>\s*<(?!tr[ >])")
        self.assertRegex(html, r"<tr[^>]*data-tip=\"row:2\"")
        self.assertRegex(html, r"<th[^>]*data-tip=\"col:status\"")
        self.assertRegex(html, r"<td[^>]*data-tip=\"cell:1\.name\"")
        self.assertIn("overflow-x:auto", html, "the table keeps its sideways scrolling")
        self.assertEqual(len(re.findall(r"<tr[ >]", html)), 3)
        self.assertIn("<thead><tr><th", html)

    def test_the_panel_dock_is_inside_the_widget_block_and_the_component_is_one_root(self):
        for k in TIPPED:
            html = self.html("tip_" + k)
            with self.subTest(component=k):
                self.assertTrue(html.startswith(("<div", "<figure")), html[:40])

    def test_the_map_link_has_a_transparent_hit_path_of_about_12_px(self):
        html = self.html("tip_geo")
        g = re.search(r'<g[^>]*data-tip="web&gt;api".*?</g>', html, re.S).group(0)
        m = re.search(r'<path[^>]*stroke="transparent"[^>]*>', g)
        self.assertIsNotNone(m, g)
        width = float(re.search(r'stroke-width="([\d.]+)"', m.group(0)).group(1))
        k = float(re.search(r'viewBox="[-\d. ]+ ([\d.]+) [\d.]+"', html).group(1)) / 640
        self.assertAlmostEqual(width / k, 12, delta=0.5, msg="12 css px, whatever the zoom of the map")
        self.assertIn("stroke-dasharray", g, "the dashed line is still drawn")

    def test_the_map_pin_hit_box_allows_7_8_px_a_letter_of_the_bold_label(self):
        html = self.html("tip_geo")
        g = re.search(r'<g[^>]*data-tip="web"[^>]*>.*?</g>', html, re.S).group(0)
        rect = re.search(r'<rect[^>]*fill="transparent"[^>]*>', g).group(0)
        width = float(re.search(r' width="([\d.]+)"', rect).group(1))
        k = float(re.search(r'viewBox="[-\d. ]+ ([\d.]+) [\d.]+"', html).group(1)) / 640
        self.assertAlmostEqual(width / k, 18 + 3 * 7.8 + 2, delta=0.3, msg="pin (18 px), 3 letters at 7.8 px and 2 px of room")

    def test_the_map_pin_has_a_hit_rectangle_and_a_marker(self):
        html = self.html("tip_geo")
        g = re.search(r'<g[^>]*data-tip="web"[^>]*>.*?</g>', html, re.S).group(0)
        self.assertIn('fill="transparent"', g)
        self.assertIn("web</text>", g)


# ---- one interaction module for the whole page, handed to the packs through window.__HM.mods -------------------------------

class SharedModule(unittest.TestCase):
    def js(self, rel):
        return gzip.decompress((bundle.ASSETS / rel).read_bytes()).decode("utf-8")

    def test_the_build_hands_the_interaction_and_the_highlighter_to_the_packs(self):
        text = (BUILD / "build.mjs").read_text(encoding="utf-8")
        self.assertRegex(text, r'tooltips\\\.jsx\$/, "hermes-openui/tooltips"')
        self.assertRegex(text, r'code\\\.jsx\$/, "hermes-openui/code"')
        self.assertIn("hermes-openui/tooltip-schema", text)
        core_src = (SRC / "core.jsx").read_text(encoding="utf-8")
        self.assertIn('"hermes-openui/tooltips"', core_src)
        self.assertIn('"hermes-openui/code"', core_src)

    def test_the_core_carries_the_interaction_once_and_the_packs_take_it_from_the_core(self):
        m = bundle.manifest()
        core = self.js(m["core"]["file"])
        self.assertEqual(core.count("data-tip-panel"), 1, "the panel markup is in the core once")
        self.assertEqual(core.count('name:"Tooltip"'), 1, "Tooltip is defined once")
        for name in ("diagrams", "infra", "sequence", "map", "text"):
            text = self.js(m["packs"][name]["file"])
            with self.subTest(pack=name):
                self.assertNotIn("data-tip-panel", text, "the pack bundles its own copy of the interaction")
                self.assertNotIn('name:"Tooltip"', text)
                self.assertNotIn("Copy blocked", text, "the pack bundles its own copy of the code highlighter")
                if name != "text":
                    self.assertIn('__HM.mods["hermes-openui/tooltips"]', text)
        self.assertIn('__HM.mods["hermes-openui/code"]', self.js(m["packs"]["text"]["file"]))

    def test_the_diagram_packs_shrink_and_the_core_grows_a_little(self):
        m = bundle.manifest()
        for name in ("diagrams", "infra", "sequence"):
            with self.subTest(pack=name):
                self.assertLess(m["packs"][name]["gz"], BEFORE[name] - 3000, "the pack should lose the interaction module and the highlighter (about 5 KB gzip)")
        self.assertLess(m["packs"]["text"]["gz"], BEFORE["text"] - 1000)
        self.assertLess(m["packs"]["map"]["gz"], BEFORE["map"] + 1500)
        self.assertGreater(m["core"]["gz"], BEFORE["core"])
        self.assertLess(m["core"]["gz"], BEFORE["core"] + 12 * 1024)
        self.assertEqual(bundle.verify(), [])

    def test_the_tooltip_component_is_still_registered_once_in_the_core(self):
        m = bundle.manifest()
        self.assertIn("Tooltip", m["core"]["components"])
        for pack, info in m["packs"].items():
            self.assertNotIn("Tooltip", info["components"], pack)
        defs = [p.name for p in sorted(SRC.rglob("*.js*")) if re.search(r'defineComponent\(\s*\{\s*name:\s*"Tooltip"', p.read_text(encoding="utf-8"))]
        self.assertEqual(defs, ["tooltip-schema.js"])

    def test_the_html_interaction_is_one_generic_piece_not_five_copies(self):
        hits = [p.relative_to(SRC).as_posix() for p in sorted(SRC.rglob("*.js*")) if 'role="button"' in p.read_text(encoding="utf-8")]
        self.assertEqual(hits, ["components/tooltips.jsx"], "only the interaction module marks an element as a tooltip button")
        text = (SRC / "components" / "tooltips.jsx").read_text(encoding="utf-8")
        for name in ("export function HotBox", "export function TipDot", "export function TipBox"):
            self.assertIn(name, text)


# ---- native mode: the app's stylesheet makes every role=button unselectable ---------------------------------------------------

class NativeCss(unittest.TestCase):
    def test_every_tooltip_element_is_selectable_in_native_mode_and_the_copy_and_close_buttons_are_not_touched(self):
        for rel in ("build/src/plugin/plugin.jsx", "desktop/plugin.js"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(file=rel):
                m = re.search(r"\.\$\{\w+\} \[data-tip\]\{([^}]*)\}", text)  # the class name is a variable (minified in the built file)
                self.assertIsNotNone(m, "no rule makes [data-tip] selectable")
                self.assertIn("user-select:text", m.group(1))
                self.assertIn("-webkit-user-select:text", m.group(1))
                self.assertNotIn("button", m.group(1), "the Copy and close buttons keep the app's user-select:none")

    def test_the_layout_check_reads_the_user_select_of_tooltip_elements(self):
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import verify_native
        finally:
            sys.path.remove(str(ROOT / "tools"))
        base_row = {"widget": "tooltips-select", "width": 360, "container": 360, "w": 360, "h": 100, "rootOverflow": False, "slotOverflow": False, "wrap": "normal",
                    "cellWrap": "normal", "scrollers": [], "media": []}
        good = dict(base_row, tipSelect=[{"name": "table cell", "select": "text", "text": "web", "picked": "web"}])
        self.assertEqual(verify_native.problems([good], True), [])
        broken = dict(base_row, tipSelect=[{"name": "metric tile", "select": "text", "text": "Error rate2.4%+1.9 pt", "picked": "Error rate\n2.4%\n+1.9 pt"}])
        self.assertEqual(verify_native.problems([broken], True), [], "line breaks between block children are not a difference")
        none = dict(base_row, tipSelect=[{"name": "table cell", "select": "none", "text": "web", "picked": ""}])
        bad = verify_native.problems([none], True)
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("table cell", bad[0])
        self.assertIn("user-select", bad[0])
        picked = dict(base_row, tipSelect=[{"name": "bar", "select": "text", "text": "api", "picked": ""}])
        self.assertEqual(len(verify_native.problems([picked], True)), 1, "a Range over the element must return its text")
        self.assertEqual(verify_native.problems([none], False), [], "without the app's stylesheet there is nothing to check")
        self.assertIn("tooltips-select", [w["name"] for w in verify_native.load_widgets()])


# ---- the reference the agent reads --------------------------------------------------------------------------------------------

SIGS = {
    "Table": "Table(columns: string[], rows: (string | number)[][], tooltips?: Tooltip[])",
    "Metric": 'Metric(label: string, value: string, delta?: string, tone?: "good" | "warn" | "bad" | "neutral", tooltips?: Tooltip[])',
    "BarChart": "BarChart(labels: string[], values: number[], title?: string, unit?: string, tooltips?: Tooltip[])",
    "GeoMap": "GeoMap(points: GeoPoint[], links?: string[][], title?: string, tooltips?: Tooltip[])",
    "Image": "Image(src: string, alt?: string, caption?: string, tooltips?: Tooltip[])",
}


class Reference(unittest.TestCase):
    def test_the_signatures_end_with_tooltips(self):
        for name, sig in SIGS.items():
            with self.subTest(component=name):
                self.assertTrue(base.reference_line(name).startswith(sig), base.reference_line(name))

    def test_each_description_says_tooltips_is_the_last_argument_and_how_to_name_a_target(self):
        needles = {
            "Table": ("row:3", "col:status", "cell:3.status"),
            "Metric": ("its own label", "null"),
            "BarChart": ("bar's label", "null"),
            "GeoMap": ("A>B", "point's label", "null"),
            "Image": ("image", "null"),
        }
        for name, words in needles.items():
            line = base.reference_line(name)
            with self.subTest(component=name):
                self.assertIn("tooltips", line)
                self.assertIn("LAST argument", line)
                for w in words:
                    self.assertIn(w, line)

    def test_the_four_older_diagrams_get_the_same_last_argument_rule_as_the_five(self):
        for name in ("Dag", "Erd", "InfraMap", "SequenceDiagram"):
            line = base.reference_line(name)
            with self.subTest(component=name):
                self.assertIn("tooltips: Tooltip[] is the LAST argument", line)
                self.assertIn("write null for each skipped optional argument", line)
                self.assertIn(name + "(", line.split("tooltips:", 1)[1], "the example is for this component")

    def test_the_tooltip_description_names_all_nine(self):
        line = base.reference_line("Tooltip")
        for name in ("Dag", "Erd", "InfraMap", "SequenceDiagram", "Table", "Metric", "BarChart", "GeoMap", "Image"):
            self.assertIn(name, line)

    def test_the_tool_description_is_untouched(self):
        # A static check (no git needed): the description and the parameter text hash to the value pinned above.
        text = json.dumps([base.schemas.RENDER_WIDGET, base.schemas.EXPORT_WIDGETS], sort_keys=True)
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), SCHEMA_SHA256, "schemas.py changed: if on purpose, update SCHEMA_SHA256")


# ---- docs, guidance, changelog -----------------------------------------------------------------------------------------------

PAGES = {"Table": "table", "Metric": "metric", "BarChart": "bar-chart", "GeoMap": "geo-map", "Image": "image"}


class Docs(unittest.TestCase):
    def test_the_tooltip_page_has_a_where_tooltips_work_table_with_all_nine_and_the_height_note_once(self):
        text = (DOCS / "Tooltip.md").read_text(encoding="utf-8")
        self.assertIn("Where tooltips work", text)
        for name in ("Dag", "Erd", "InfraMap", "SequenceDiagram", "Table", "Metric", "BarChart", "GeoMap", "Image"):
            self.assertRegex(text, r"\| \[%s\]\(%s\.md\) \|" % (name, name))
        for form in ("row:3", "col:status", "cell:3.status", "A>B", "image"):
            self.assertIn(form, text)
        self.assertEqual(len(re.findall(r"(?m)^#{3,4} Height in preview mode", text)), 1)
        self.assertIn("1,200 px", text)
        self.assertNotIn("Tables, charts and the other components have no tooltips", text)
        self.assertIn("LineChart", text, "the library charts are named as not taking tooltips")

    def test_each_page_has_a_tooltips_section_with_an_example_a_screenshot_and_generic_names(self):
        for name, stem in PAGES.items():
            text = (DOCS / (name + ".md")).read_text(encoding="utf-8")
            with self.subTest(page=name):
                self.assertRegex(text, r"(?m)^## Tooltips\s*$")
                sec = text[text.index("## Tooltips"):]
                self.assertIn("```openui", sec)
                self.assertIn("Tooltip(", sec)
                self.assertIn("![", sec)
                example = EXAMPLES / (stem + "-tooltips.oui")
                self.assertTrue(example.is_file(), example)
                png = DOCS / "images" / (stem + "-tooltips.png")
                self.assertTrue(png.is_file(), png)
                self.assertLess(png.stat().st_size, 100 * 1024)
                self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
                body = example.read_text(encoding="utf-8")
                self.assertEqual(helpers.private_setup_hits(re.sub(r"https://example\.com[^\s\"]*", "", body)), [])
                for l in re.findall(r"https?://[^\s\"]+", body):
                    self.assertTrue(l.startswith("https://example.com/"), l)

    def test_the_indexes_and_the_feature_text_name_the_new_components(self):
        index = (DOCS / "README.md").read_text(encoding="utf-8")
        row = [ln for ln in index.splitlines() if ln.startswith("| [**Tooltip**]")][0]
        for name in ("Table", "Metric", "BarChart", "GeoMap", "Image"):
            self.assertIn(name, row)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        start = readme.index("### Tooltips")
        for name in ("Table", "Metric", "BarChart", "GeoMap", "Image"):
            self.assertIn(name, readme[start:start + 1500])
        self.assertNotIn("hover tooltips for the diagrams", readme)

    def test_nothing_of_this_work_uses_the_reserved_word_or_a_dash(self):
        # A scan of the current files (no git history needed). The files whose every line is new work are scanned whole; the older files are
        # scanned for the reserved word only, because they may hold older dashes. The generated assets and desktop file are not ours to edit.
        whole = [DOCS / "Tooltip.md", ROOT / "tests" / "test_tooltips_more.py", SRC / "components" / "tooltips-core.js", SRC / "components" / "tooltips-check.js",
                 SRC / "components" / "tooltips.jsx"] + [EXAMPLES / (s + "-tooltips.oui") for s in PAGES.values()]
        for path in whole:
            for n, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                self.assertNotIn(RESERVED_WORD, ln.lower(), "%s:%d" % (path.name, n))
                self.assertNotRegex(ln, "\u2014|\u2013", "%s:%d" % (path.name, n))
        every = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "CHANGELOG.md"] + sorted(DOCS.glob("*.md")) + sorted((ROOT / "skills").rglob("*.md")) + sorted(SRC.rglob("*.js*")) + sorted((ROOT / "tests").glob("*.py"))
        for path in every:
            self.assertNotIn(RESERVED_WORD, path.read_text(encoding="utf-8").lower(), path.name)

    def test_the_geomap_pages_say_close_pins_and_short_links_need_the_keyboard(self):
        for name in ("GeoMap.md", "Tooltip.md"):
            text = (DOCS / name).read_text(encoding="utf-8")
            with self.subTest(page=name):
                self.assertRegex(text, r"closer than about 20 px")
                self.assertRegex(text, r"shorter than about 25 px")
                self.assertRegex(text, r"(?i)tab reaches each one")

    def test_the_pages_state_the_limits_of_an_image_a_table_header_and_a_metric(self):
        image = (DOCS / "Image.md").read_text(encoding="utf-8")
        self.assertIn("fills the column", image)
        self.assertIn("drawn over the picture", image)
        table = (DOCS / "Table.md").read_text(encoding="utf-8")
        self.assertRegex(table, r"hide the cells of the first row")
        for name in ("Table.md", "Tooltip.md"):
            text = (DOCS / name).read_text(encoding="utf-8")
            with self.subTest(page=name):
                self.assertIn("keeps its own role", text, "a row, a header and a cell stay a row, a column header and a cell for a screen reader")
        metric = (DOCS / "Metric.md").read_text(encoding="utf-8") + (DOCS / "Tooltip.md").read_text(encoding="utf-8")
        self.assertIn("a line of its own", metric)
        self.assertIn("below the tile", metric)
        self.assertNotIn("neighbouring tiles stretch", metric)
        self.assertNotIn("the panel is as wide as its tile", metric)

    def test_the_docs_gate_passes(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_docs.py")], capture_output=True, text=True, timeout=240, env=ENV)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class Guidance(unittest.TestCase):
    TEXT = (ROOT / "skills" / "openui-render" / "SKILL.md").read_text(encoding="utf-8")

    def test_the_skill_stays_within_5000_characters_and_names_all_nine_components(self):
        self.assertLessEqual(len(self.TEXT), 5000)
        for name in ("Dag", "Erd", "InfraMap", "SequenceDiagram", "Table", "Metric", "BarChart", "GeoMap", "Image"):
            self.assertIn(name, self.TEXT)
        for needle in ("reference=true", "LAST argument", "`null`", "800 px", "about 8"):
            self.assertIn(needle, self.TEXT)

    def test_the_cap_is_not_raised(self):
        for rel in ("tests/test_plugin.py", "tests/test_custom_components_skill.py"):
            self.assertNotIn("5001", (ROOT / rel).read_text(encoding="utf-8"))

    def test_the_changelog_lists_the_five_under_added(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        sec = re.split(r"(?m)^(?=## \[)", text)[1]
        self.assertRegex(sec, r"^## \[Unreleased\]")
        added = sec[sec.index("### Added"):]
        for name in ("Table", "Metric", "BarChart", "GeoMap", "Image"):
            self.assertIn(name, added)
        self.assertNotRegex(sec, "\u2014|\u2013")
        self.assertNotIn(RESERVED_WORD, sec.lower())

    def test_the_agent_rules_describe_the_core_interaction_module(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("hermes-openui/tooltips", agents)
        self.assertIn("Table", agents[agents.index("Tooltip is a core component"):][:3500])


if __name__ == "__main__":
    unittest.main()
