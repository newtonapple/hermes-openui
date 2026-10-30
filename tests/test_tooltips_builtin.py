"""Tooltips on the four diagrams (Dag, Erd, InfraMap, SequenceDiagram): the `Tooltip` component, its checks and its view.

Layers: the manifest and the reference the model reads; the reserved name; the page builder; the PURE module run under Node with
no bundler (build/src/components/tooltips-core.js and tooltips-check.js); the real validator
(`node assets/validate.cjs`) with one message per mistake; the markup the four views draw (esbuild bundles the real components,
React renders them to a string); the docs page and its gate; the guidance for the agent. What a browser does with a hover, a
click or a key is NOT tested here: it was driven in Chrome with tools/shoot.py --steps (see the CHANGELOG entry and the report).
"""
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402

packs = helpers.sub("packs")
lint = helpers.sub("lint")
bundle = helpers.sub("bundle")
page = helpers.sub("page")
schemas = helpers.sub("schemas")
tools = helpers.sub("tools")

ROOT = helpers.ROOT
BUILD = ROOT / "build"
SRC = BUILD / "src"
DOCS = ROOT / "docs" / "ui-components"
EXAMPLES = DOCS / "examples"
ENV = dict(os.environ, DO_NOT_TRACK="1", OPENUI_TELEMETRY_DISABLED="1", PYTHONDONTWRITEBYTECODE="1")

TOOLTIP_SIG = 'Tooltip(target: string, hint?: string, detail?: string, code?: string, language?: string, tone?: "info" | "good" | "warn" | "bad", link?: string, linkLabel?: string)'
DIAGRAM_SIGS = {
    "Dag": 'Dag(nodes: DagNode[], edges: string[][], direction?: "LR" | "TB", title?: string, tooltips?: Tooltip[])',
    "Erd": "Erd(entities: Entity[], relations: Relation[], title?: string, tooltips?: Tooltip[])",
    "InfraMap": 'InfraMap(zones: InfraZone[], links: InfraLink[], title?: string, direction?: "LR" | "TB", tooltips?: Tooltip[])',
    "SequenceDiagram": "SequenceDiagram(participants: SeqParticipant[], steps: (SeqMessage | SeqNote | SeqGroup)[], title?: string, numbered?: boolean, tooltips?: Tooltip[])",
}
DOC_EXAMPLES = [
    "tooltip-hover.oui", "tooltip-dag-node.oui", "tooltip-infra-map.oui", "tooltip-sequence-diagram.oui",
    "dag-tooltips.oui", "erd-tooltips.oui", "infra-map-tooltips.oui", "sequence-diagram-tooltips.oui",
]


def node_ok():
    return bool(shutil.which("node"))


def node_missing_reason():
    if not shutil.which("node"):
        return "node is not on PATH"
    for mod in ("react", "react-dom", "zod", "esbuild", "@openuidev/react-lang", "@openuidev/lang-core"):
        if not (BUILD / "node_modules" / mod / "package.json").is_file():
            return "build/node_modules/%s is missing (run `npm ci` in build/)" % mod
    return ""


def reference_line(name):
    lines = [ln for ln in bundle.reference_text().splitlines() if ln.startswith(name + "(")]
    assert len(lines) == 1, "%s appears %d times in components.md" % (name, len(lines))
    return lines[0]


def q(s):
    return json.dumps(s)


def validate(text, directory):
    path = Path(directory) / ("case-%d.oui" % len(list(Path(directory).iterdir())))
    path.write_text(text, encoding="utf-8")
    r = subprocess.run(["node", str(bundle.VALIDATOR), str(path)], capture_output=True, text=True, timeout=60, env=ENV)
    return r.returncode, r.stdout + r.stderr


def problems_of(out):
    return [ln[2:] for ln in out.splitlines() if ln.startswith("- ")]


# ---- sources: the four diagrams with a list of tooltip lines ---------------------------------------------------------

def tt(target, hint="null", detail="null", code="null", language="null", tone="null", link="null", label="null"):
    return "Tooltip(%s)" % ", ".join([q(target)] + [x if x == "null" else (x if x.startswith('"') else q(x)) for x in (hint, detail, code, language, tone, link, label)])


def dag_src(*tooltips):
    return "\n".join([
        "root = Stack([d])",
        "d = Dag([n1, n2, n3], [[\"build\", \"unit\"], [\"unit\", \"ship\"]], null, null, [%s])" % ", ".join(tooltips),
        'n1 = DagNode("build", "Build")', 'n2 = DagNode("unit", "Unit tests")', 'n3 = DagNode("ship", "Ship")',
    ]) + "\n"


def erd_src(*tooltips):
    return "\n".join([
        "root = Stack([d])",
        "d = Erd([e1, e2], [r1], null, [%s])" % ", ".join(tooltips),
        'e1 = Entity("users", ["id uuid PK", "email text UNIQUE"])', 'e2 = Entity("orders", ["id uuid PK", "user_id uuid FK", "total int"])',
        'r1 = Relation("users", "orders", "1:N")',
    ]) + "\n"


def infra_src(*tooltips, extra_link=False):
    links = ["l1", "l2"] + (["l3"] if extra_link else [])
    return "\n".join([
        "root = Stack([m])",
        "m = InfraMap([z1, z2], [%s], null, null, [%s])" % (", ".join(links), ", ".join(tooltips)),
        'z1 = InfraZone("Edge", [n1, n2], "warn")', 'z2 = InfraZone("Core", [n3])',
        'n1 = InfraNode("client", "Client", "client")', 'n2 = InfraNode("web", "Web", "gateway")', 'n3 = InfraNode("api", "API", "service")',
        'l1 = InfraLink("client", "web", "HTTPS")', 'l2 = InfraLink("web", "api", "gRPC")',
    ] + (['l3 = InfraLink("web", "api", "retry", "dashed")'] if extra_link else [])) + "\n"


def seq_src(*tooltips, dup_id=False):
    return "\n".join([
        "root = Stack([d])",
        "d = SequenceDiagram([p1, p2], [m1, g1], null, null, [%s])" % ", ".join(tooltips),
        'p1 = SeqParticipant("client", "Client", "actor")', 'p2 = SeqParticipant("api", "API")',
        'm1 = SeqMessage("client", "api", "POST /login", null, "login")',
        'g1 = SeqGroup("alt", "ok?", [m2])',
        'm2 = SeqMessage("api", "client", "200", "return", %s)' % q("client" if dup_id else "reply"),
    ]) + "\n"


# ---- the manifest, the reference, the reserved name ----------------------------------------------------------------

class Manifest(unittest.TestCase):
    def test_tooltip_is_one_core_component_defined_once(self):
        m = bundle.manifest()
        self.assertIn("Tooltip", m["core"]["components"])
        self.assertIn("Tooltip", bundle.component_names())
        self.assertNotIn("Tooltip", m["components"], "a core component has no pack entry")
        for pack, info in m["packs"].items():
            self.assertNotIn("Tooltip", info["components"], "%s registers its own Tooltip; createLibrary would throw on the duplicate" % pack)

    def test_a_page_with_only_a_tooltip_pulls_no_pack_and_two_diagrams_pull_two(self):
        self.assertEqual(page.select_packs('root = Stack([a])\na = Tooltip("x", "hint")'), [])
        self.assertEqual(page.select_packs("root = Stack([a, b])\na = Dag([], [])\nb = InfraMap([], [])"), ["diagrams", "infra"])

    def test_the_sources_define_tooltip_in_exactly_one_module_and_the_packs_only_reference_it(self):
        defs = [p.name for p in sorted(SRC.rglob("*.js*")) if re.search(r'defineComponent\(\s*\{\s*name:\s*"Tooltip"', p.read_text(encoding="utf-8"))]
        self.assertEqual(defs, ["tooltip-schema.js"])
        for rel in ("packs/diagrams.jsx", "packs/infra.jsx", "packs/sequence.jsx"):
            text = (SRC / rel).read_text(encoding="utf-8")
            with self.subTest(pack=rel):
                self.assertIn("tooltip-schema.js", text)
                self.assertNotRegex(text, r"components:\s*\[[^\]]*Tooltip\b[^\]]*\]\s*\}")
        self.assertIn("Tooltip", (SRC / "core-components.jsx").read_text(encoding="utf-8"))

    def test_the_shared_interaction_lives_in_one_module_and_the_pure_ones_have_no_imports_but_each_other(self):
        self.assertTrue((SRC / "components" / "tooltips.jsx").is_file())
        for rel in ("tooltips-core.js", "tooltips-check.js"):
            text = (SRC / "components" / rel).read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("import "):
                    self.assertRegex(line, r'from "\./tooltips-core\.js"', "%s may import only the core module" % rel)
            self.assertNotIn("window.", text)
            self.assertNotIn("document.", text)
        for rel in ("diagrams.jsx", "infra.jsx", "sequence.jsx"):
            self.assertIn("tooltips.jsx", (SRC / "components" / rel).read_text(encoding="utf-8"), rel)

    def test_the_packs_share_the_cores_tooltip_definition_instead_of_bundling_a_copy(self):
        # The parser matches a component to a slot by the identity of its schema object. A pack with its own copy of Tooltip makes the
        # parser drop every Tooltip in `tooltips` ("expects object but got component"), which only shows in a browser, never in Node.
        core = gzip.decompress((bundle.ASSETS / bundle.manifest()["core"]["file"]).read_bytes()).decode("utf-8")
        self.assertTrue("hermes-openui/tooltip-schema" in core, "the core does not hand the Tooltip definition to the packs")
        for name in ("diagrams", "infra", "sequence"):
            text = gzip.decompress((bundle.ASSETS / bundle.manifest()["packs"][name]["file"]).read_bytes()).decode("utf-8")
            with self.subTest(pack=name):
                self.assertTrue('__HM.mods["hermes-openui/tooltip-schema"]' in text, "the pack does not take Tooltip from the core")
                self.assertTrue('name:"Tooltip"' not in text, "the pack bundles its own Tooltip definition")
        self.assertIn("hermes-openui/tooltip-schema", (BUILD / "build.mjs").read_text(encoding="utf-8"))

    def test_the_pack_sizes_stay_small(self):
        m = bundle.manifest()
        for name, limit in (("diagrams", 14 * 1024), ("infra", 18 * 1024), ("sequence", 18 * 1024)):
            with self.subTest(pack=name):
                self.assertLess(m["packs"][name]["gz"], limit)
        self.assertEqual(bundle.verify(), [])


class Reference(unittest.TestCase):
    def test_the_signatures_are_exactly_the_ones_in_the_brief(self):
        self.assertEqual(reference_line("Tooltip").split(" \u2014 ")[0], TOOLTIP_SIG)
        for name, sig in DIAGRAM_SIGS.items():
            with self.subTest(component=name):
                self.assertEqual(reference_line(name).split(" \u2014 ")[0], sig)

    def test_tooltip_comes_after_every_older_component_so_the_existing_order_is_unchanged(self):
        order = re.findall(r"^([A-Z]\w*)\(", bundle.reference_text(), re.M)
        self.assertEqual(order[-1], "Tooltip")
        self.assertEqual(order[-6:-1], ["SeqParticipant", "SeqMessage", "SeqNote", "SeqGroup", "SequenceDiagram"])

    def test_the_descriptions_tell_the_agent_when_to_add_one_and_what_a_target_is(self):
        desc = reference_line("Tooltip").split(" \u2014 ", 1)[1]
        for word in ("only", "about 8", "hint", "short", "code", "native", "node id", "zone:", ">", "entity.column", "message", "id", "tone", "worth"):
            with self.subTest(word=word):
                self.assertIn(word, desc)
        for name in DIAGRAM_SIGS:
            with self.subTest(component=name):
                self.assertIn("Tooltip", reference_line(name).split(" \u2014 ", 1)[1])

    def test_the_tool_description_is_untouched(self):
        desc = schemas.RENDER_WIDGET["description"]
        self.assertNotIn("tooltip", desc.lower())
        self.assertLessEqual(len(desc), 800)


class ReservedName(unittest.TestCase):
    def test_a_user_pack_may_not_reuse_the_name(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "mine.js"
            f.write_text('/* hermes-openui-pack\n{"api": 1, "name": "mine", "components": {"Tooltip": "Tooltip(a: string) \\u2014 mine."}}\n*/\n(function () {})();\n', encoding="utf-8")
            found, problems = packs.load([str(f)], bundle.component_names())
        self.assertEqual(found, [])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("shadows a built-in component", problems[0])

    def test_the_pack_api_did_not_change(self):
        text = (ROOT / "packs.py").read_text(encoding="utf-8")
        self.assertRegex(text, r"api\W+1")


# ---- the pure modules under Node ----------------------------------------------------------------------------------------

HARNESS = r"""
const cfg = JSON.parse(process.env.TIP_CFG);
const core = await import(cfg.core);
const check = await import(cfg.check);
const out = {};
out.tips = cfg.tips.map((a) => core.tooltipText(a));
out.bodies = cfg.tips.map((a) => core.panelText(a));
out.norm = core.normalizeTooltips(cfg.norm);
out.place = cfg.place.map((c) => core.placeTooltip(c.wrap, c.anchor, c.tip, c.gap));
out.links = cfg.links.map((u) => core.checkLink(u));
out.checks = cfg.checks.map((c) => check.checkTooltips(c.kind, c.props));
out.linkRows = cfg.linkRows.map((u) => core.checkLink(u));
// A text model for the tooltip: nat is the width of the text on one line (padding included). Wrapping at maxWidth w adds lines.
const model = (nat) => (mw) => {
  if (nat <= mw) return { width: nat, height: 29.5 };
  const lines = Math.ceil((nat - 18) / (mw - 18));
  return { width: mw, height: 12 + 17.5 * lines };
};
out.fit = cfg.fit.map((c) => { const r = core.placeTooltip(c.wrap, c.anchor, model(c.nat), c.gap); return Object.assign({}, r, { size: model(c.nat)(r.maxWidth) }); });
out.tipLines = typeof core.tipLines === "function" ? [47, 100, 10, 29.5, 12].map((h) => core.tipLines(h)) : null;
out.consts = { tones: core.TONES, limits: core.LIMITS, fallback: core.TIP_FALLBACK };
out.targets = cfg.targets.map((c) => core.targetSummary(c.kind, c.props));
process.stdout.write(JSON.stringify(out));
"""


def el(type_name, **props):
    return {"typeName": type_name, "props": props}


def T(target, **props):
    return el("Tooltip", target=target, **props)


LONG_FIRST = "x" * 150
PURE_TIPS = [
    {"hint": "Slow query", "detail": "ignored"},
    {"hint": None, "detail": "First line\nsecond line"},
    {"hint": "   ", "detail": "\n\nAfter blanks\nmore"},
    {"hint": None, "detail": LONG_FIRST},
    {"hint": None, "detail": None, "code": "SELECT 1"},
    {},
    {"hint": "Only a hint", "detail": None},
]
PLACE = [
    {"wrap": {"left": 0, "top": 0, "width": 400, "height": 300}, "anchor": {"left": 180, "top": 150, "width": 40, "height": 20}, "tip": {"width": 100, "height": 30}},
    {"wrap": {"left": 0, "top": 0, "width": 400, "height": 300}, "anchor": {"left": 0, "top": 150, "width": 20, "height": 20}, "tip": {"width": 100, "height": 30}},
    {"wrap": {"left": 0, "top": 0, "width": 400, "height": 300}, "anchor": {"left": 390, "top": 150, "width": 10, "height": 20}, "tip": {"width": 100, "height": 30}},
    {"wrap": {"left": 0, "top": 0, "width": 400, "height": 300}, "anchor": {"left": 180, "top": 4, "width": 40, "height": 20}, "tip": {"width": 100, "height": 30}},
    {"wrap": {"left": 50, "top": 80, "width": 200, "height": 60}, "anchor": {"left": 120, "top": 100, "width": 20, "height": 20}, "tip": {"width": 100, "height": 50}},
    {"wrap": {"left": 0, "top": 0, "width": 80, "height": 300}, "anchor": {"left": 30, "top": 150, "width": 20, "height": 20}, "tip": {"width": 150, "height": 30}},
    {"wrap": {"left": 0, "top": 0, "width": 200, "height": 60}, "anchor": {"left": 150, "top": 20, "width": 20, "height": 20}, "tip": {"width": 100, "height": 50}},
]
LINKS = ["https://example.com/a", "javascript:alert(1)", "", "HTTP://example.com", "//example.com/x", "https://user:pw@example.com/", "https://exa mple.com", "https://example.com/\u0007", "example.com", "https://", "mailto:a@example.com"]
SEQ_PROPS = {
    "participants": [el("SeqParticipant", id="client", label="Client"), el("SeqParticipant", id="api", label="API")],
    "steps": [el("SeqMessage", **{"from": "client", "to": "api", "label": "go", "id": "m1"}), el("SeqGroup", kind="alt", label="x", steps=[el("SeqMessage", **{"from": "api", "to": "client", "label": "ok", "id": "m2"}), el("SeqNote", over="api", text="n")], elseSteps=[el("SeqMessage", **{"from": "api", "to": "client", "label": "no"})])],
}
INFRA_PROPS = {
    "zones": [el("InfraZone", name="Edge", nodes=[el("InfraNode", id="web", label="Web"), el("InfraNode", id="api", label="API")])],
    "links": [el("InfraLink", **{"from": "web", "to": "api"}), el("InfraLink", **{"from": "web", "to": "api", "label": "again"}), el("InfraLink", **{"from": "web", "to": "ghost"})],
}
ERD_PROPS = {"entities": [el("Entity", name="orders", fields=["id uuid PK", "user_id uuid FK", "  total   int "])], "relations": []}
DAG_PROPS = {"nodes": [el("DagNode", id="a", label="A"), el("DagNode", id="b", label="B")], "edges": [["a", "b"]]}


# Addresses the click must open exactly as they are shown: (link, accepted?, what the reason must say).
HTTPS300 = "https://example.com/" + "a" * 280
LINK_ROWS = [
    # the spoofing family: a format character anywhere, a non-ASCII host or port, a bad port
    ("https://\u0430pple.com/", False, ("U+0430", "ASCII", "punycode")),
    ("https://caf\u00e9.example.com/", False, ("U+00E9", "punycode")),
    ("https://x.com\uff0fevil.com/", False, ("U+FF0F", "punycode")),
    ("https://x.com:80\u0663/", False, ("U+0663", "punycode")),
    ("https://example.com/\u202egpj.exe", False, ("U+202E",)),
    ("https://exa\u200bmple.com/", False, ("U+200B",)),
    ("https://x.com/a\u2066b", False, ("U+2066",)),
    ("https://x.com/\ufeff", False, ("U+FEFF",)),
    ("https://x.com/\u00ad", False, ("U+00AD",)),
    ("https://x.com/\u061c", False, ("U+061C",)),
    ("https://x.com/\u180e", False, ("U+180E",)),
    ("https://x.com/\u200f", False, ("U+200F",)),
    ("https://x.com/a\u2060b", False, ("U+2060",)),
    ("https://x.com/\U000e0041", False, ("U+E0041",)),
    ("https://x.com:99999999/", False, ("port",)),
    ("https://x.com:abc/", False, ("port",)),
    ("https://x.com:0/", False, ("port",)),
    ("https://x.com:65536/", False, ("port",)),
    ("https://x.com:/", False, ("port",)),
    ("https://[::1]:99999/", False, ("port",)),
    ("https://[::1]:abc/", False, ("port",)),
    # control characters, one rule each (the C1 range and DEL are not format characters)
    ("https://x.com/\u0085", False, ("whitespace or a control character",)),
    ("https://x.com/\u007f", False, ("whitespace or a control character",)),
    # the backslash rule on its own: the userinfo rule does not see this one
    ("https://good.example.com\\.evil.com", False, ("backslash",)),
    # the length limit is inclusive: 300 characters pass, 301 do not
    (HTTPS300, True, ()),
    (HTTPS300 + "a", False, ("301 characters", "limit is 300")),
    # still accepted
    ("https://x.com:8080/a", True, ()),
    ("https://x.com:65535/", True, ()),
    ("https://x.com:1/", True, ()),
    ("https://[::1]:8443/", True, ()),
    ("https://[::1]/", True, ()),
    ("https://xn--pple-43d.com/", True, ()),
    ("https://example.com/caf\u00e9", True, ()),
    ("https://example.com/?q=caf\u00e9#\u00fc", True, ()),
    ("https://example.com/a?q=1#h", True, ()),
]

# placeTooltip with a text model (see HARNESS): wrap, anchor, nat = width of the text on one line.
FIT = [
    {"name": "hint of 140 characters in a diagram 47 px tall, 700 px wide", "wrap": {"left": 0, "top": 0, "width": 700, "height": 47}, "anchor": {"left": 100, "top": 5, "width": 87, "height": 36}, "nat": 900},
    {"name": "hint of 140 characters in a diagram 47 px tall, 360 px wide", "wrap": {"left": 0, "top": 0, "width": 360, "height": 47}, "anchor": {"left": 22, "top": 5, "width": 87, "height": 36}, "nat": 900},
    {"name": "a short LR diagram at 360 px, text wider than the room beside the node", "wrap": {"left": 0, "top": 0, "width": 328, "height": 72}, "anchor": {"left": 6, "top": 18, "width": 87, "height": 36}, "nat": 300},
    {"name": "a short one-row diagram, the node in the middle", "wrap": {"left": 0, "top": 0, "width": 700, "height": 60}, "anchor": {"left": 300, "top": 12, "width": 90, "height": 36}, "nat": 230},
    {"name": "narrow wrapper, no side has 140 px, a little room above", "wrap": {"left": 0, "top": 0, "width": 160, "height": 120}, "anchor": {"left": 50, "top": 60, "width": 60, "height": 20}, "nat": 400},
    {"name": "no room anywhere", "wrap": {"left": 10, "top": 10, "width": 100, "height": 40}, "anchor": {"left": 50, "top": 10, "width": 20, "height": 20}, "nat": 400},
    {"name": "a wrapper narrower than 140 px", "wrap": {"left": 0, "top": 0, "width": 120, "height": 200}, "anchor": {"left": 40, "top": 90, "width": 40, "height": 20}, "nat": 230},
    {"name": "a node in the middle of a narrow one-row diagram: 115 px on each side", "wrap": {"left": 0, "top": 0, "width": 328, "height": 47}, "anchor": {"left": 121, "top": 5, "width": 87, "height": 36}, "nat": 1100},
    {"name": "plenty of room above", "wrap": {"left": 0, "top": 0, "width": 700, "height": 400}, "anchor": {"left": 300, "top": 200, "width": 90, "height": 36}, "nat": 230},
    {"name": "node at the far right edge, tall text", "wrap": {"left": 0, "top": 0, "width": 360, "height": 90}, "anchor": {"left": 280, "top": 25, "width": 80, "height": 36}, "nat": 800},
    {"name": "node at the far left edge, tall text", "wrap": {"left": 0, "top": 0, "width": 360, "height": 90}, "anchor": {"left": 0, "top": 25, "width": 80, "height": 36}, "nat": 800},
]
# An InfraMap whose node ids contain `>`: the targets `a>b -> c` and `a -> b>c` are the same string.
GT_PROPS = {
    "zones": [el("InfraZone", name="Z", nodes=[el("InfraNode", id="a", label="A"), el("InfraNode", id="b>c", label="BC"), el("InfraNode", id="a>b", label="AB"), el("InfraNode", id="c", label="C")])],
    "links": [el("InfraLink", **{"from": "a>b", "to": "c"}), el("InfraLink", **{"from": "a", "to": "b>c"})],
}
SEQ_CLASH = dict(SEQ_PROPS, steps=[el("SeqMessage", **{"from": "client", "to": "api", "label": "go", "id": "client"})])
CODE40 = "\n".join(["x"] * 40)


@unittest.skipUnless(node_ok(), "needs Node")
class PureModules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = {
            "core": (SRC / "components" / "tooltips-core.js").as_uri(), "check": (SRC / "components" / "tooltips-check.js").as_uri(),
            "tips": PURE_TIPS, "place": PLACE, "links": LINKS,
            "norm": [T("a", hint="  h  ", tone="loud"), el("Text", text="x"), {"typeName": "Tooltip", "props": {"hint": "no target"}}, T("b", detail="d", link=""), None, 5],
            "targets": [{"kind": "SequenceDiagram", "props": SEQ_PROPS}, {"kind": "InfraMap", "props": INFRA_PROPS}, {"kind": "Erd", "props": ERD_PROPS}, {"kind": "Dag", "props": DAG_PROPS}],
            "checks": [
                {"kind": "Dag", "props": dict(DAG_PROPS, tooltips=[T("a", hint="x"), T("zzz", hint="x")])},
                {"kind": "Dag", "props": dict(DAG_PROPS, tooltips=[T("a", code=CODE40)])},
                {"kind": "Dag", "props": dict(DAG_PROPS, tooltips=[T("a", code=CODE40 + "\nx")])},
                {"kind": "Dag", "props": dict(DAG_PROPS, tooltips=[T("a", code=CODE40 + "\n\n")])},
                {"kind": "SequenceDiagram", "props": dict(SEQ_CLASH, tooltips=[T("client", hint="x")])},
                {"kind": "InfraMap", "props": dict(INFRA_PROPS, tooltips=[T("web>api", hint="x")])},
                {"kind": "InfraMap", "props": dict(GT_PROPS, tooltips=[T("a>b>c", hint="x")])},
            ],
            "linkRows": [row[0] for row in LINK_ROWS], "fit": FIT,
        }
        r = subprocess.run(["node", "--input-type=module", "-e", HARNESS], capture_output=True, text=True, timeout=60, env=dict(ENV, TIP_CFG=json.dumps(cfg)))
        if r.returncode != 0:
            raise AssertionError("node harness failed:\n" + (r.stderr or r.stdout)[-2000:])
        cls.r = json.loads(r.stdout)

    def test_constants(self):
        c = self.r["consts"]
        self.assertEqual(c["tones"], ["info", "good", "warn", "bad"])
        self.assertEqual(c["limits"], {"count": 60, "hint": 140, "detail": 800, "code": 2000, "codeLines": 40, "language": 20, "linkLabel": 60, "link": 300})
        self.assertEqual(c["fallback"], "Click for details")

    def test_tooltip_text_prefers_the_hint_then_the_first_line_of_the_detail_then_a_prompt(self):
        t = self.r["tips"]
        self.assertEqual(t[0], "Slow query")
        self.assertEqual(t[1], "First line")
        self.assertEqual(t[2], "After blanks")
        self.assertEqual(len(t[3]), 100)
        self.assertTrue(t[3].endswith("\u2026"))
        self.assertEqual(t[4], "Click for details")
        self.assertEqual(t[5], "Click for details")
        self.assertEqual(t[6], "Only a hint")

    def test_the_panel_says_the_detail_and_falls_back_to_the_hint_so_a_click_always_shows_something(self):
        # There is no hover on a touch screen: a tooltip that has only a hint must still show it when it is clicked.
        b = self.r["bodies"]
        self.assertEqual(b[0], "ignored")
        self.assertEqual(b[1], "First line\nsecond line")
        self.assertEqual(b[6], "Only a hint")
        self.assertIsNone(b[4], "code only: the panel has its code block and no text line")
        self.assertIsNone(b[5])

    def test_normalize_drops_what_is_not_a_tooltip_and_defaults_the_tone(self):
        n = self.r["norm"]
        self.assertEqual([a["target"] for a in n], ["a", "b"])
        self.assertEqual(n[0]["tone"], "info")
        self.assertEqual(n[0]["hint"], "h")
        self.assertIsNone(n[0]["detail"])
        self.assertIsNone(n[1]["link"], "an empty link is no link")

    def test_the_tooltip_is_centred_clamped_and_flipped(self):
        p = self.r["place"]
        self.assertEqual({k: p[0][k] for k in ("left", "top", "side")}, {"left": 150.0, "top": 114.0, "side": "above"})
        self.assertEqual(p[1]["left"], 0)
        self.assertEqual(p[2]["left"], 300)
        self.assertEqual(p[3]["side"], "below")
        self.assertEqual(p[3]["top"], 30.0)
        self.assertEqual({k: p[4][k] for k in ("left", "top", "side")}, {"left": 96.0, "top": 5.0, "side": "right"}, "neither above nor below fits in a short wrapper: go beside the element, never on top of it")
        self.assertEqual({k: p[6][k] for k in ("left", "top", "side")}, {"left": 44.0, "top": 5.0, "side": "left"}, "no room on the right either")
        for case, got in zip(PLACE, p):
            wrap, tip = case["wrap"], case["tip"]
            self.assertGreaterEqual(got["left"], 0)
            self.assertGreaterEqual(got["top"], 0)
            if tip["width"] <= wrap["width"]:
                self.assertLessEqual(got["left"] + tip["width"], wrap["width"])
            if tip["height"] <= wrap["height"]:
                self.assertLessEqual(got["top"] + tip["height"], wrap["height"])
        self.assertEqual(p[5]["left"], 0, "a tooltip wider than the wrapper starts at its left edge")

    def test_the_tooltip_never_covers_the_element_and_never_leaves_the_wrapper(self):
        # S2. Every case: inside the wrapper both ways, no more than 280 wide, and clear of the hovered element whenever any side has room.
        for case, got in zip(FIT, self.r["fit"]):
            with self.subTest(case=case["name"]):
                wrap, anchor, size = case["wrap"], case["anchor"], got["size"]
                height = got["maxHeight"] if got["lines"] else size["height"]
                self.assertGreaterEqual(got["left"], 0)
                self.assertLessEqual(got["left"] + size["width"], wrap["width"] + 0.05, "sticks out on the right")
                self.assertGreaterEqual(got["top"], 0)
                self.assertLessEqual(got["top"] + height, wrap["height"] + 0.05, "sticks out at the bottom (that would grow the page)")
                self.assertLessEqual(got["maxWidth"], 280)
                self.assertGreaterEqual(got["maxWidth"], min(100, wrap["width"]))
                if got["side"] != "over":
                    ax, ay = anchor["left"] - wrap["left"], anchor["top"] - wrap["top"]
                    apart = got["left"] >= ax + anchor["width"] or got["left"] + size["width"] <= ax or got["top"] >= ay + anchor["height"] or got["top"] + height <= ay
                    self.assertTrue(apart, "covers the element: %r" % (got,))

    def test_a_tall_tip_in_a_short_wrapper_goes_beside_the_element_wraps_and_is_cut_with_a_line_clamp(self):
        wide, narrow = self.r["fit"][0], self.r["fit"][1]
        self.assertEqual((wide["side"], wide["maxWidth"], wide["top"], wide["lines"]), ("right", 280, 0, 2), "47 px of height hold two lines")
        self.assertEqual((narrow["side"], narrow["top"], narrow["lines"]), ("right", 0, 2))
        self.assertEqual(narrow["maxWidth"], 360 - (22 + 87 + 6), "the text wraps to the room beside the node instead of covering it")
        self.assertEqual(self.r["tipLines"], [2, 5, 1, 1, 1], "tipLines never gives less than one line")

    def test_the_text_wraps_to_the_room_beside_the_node_down_to_140_px(self):
        got = self.r["fit"][2]
        self.assertEqual(got["side"], "right")
        self.assertEqual(got["maxWidth"], 328 - (6 + 87 + 6))
        self.assertIsNone(got["lines"], "it fits the 72 px of the wrapper once wrapped")

    def test_a_tooltip_that_fits_beside_the_node_keeps_its_natural_width(self):
        got = self.r["fit"][3]
        self.assertEqual((got["side"], got["lines"]), ("right", None))
        self.assertEqual(got["left"], 300 + 90 + 6)

    def test_a_narrow_wrapper_squeezes_into_the_room_above_before_it_covers_the_element(self):
        got = self.r["fit"][4]
        self.assertEqual((got["side"], got["maxWidth"], got["lines"]), ("above", 160, 2))
        self.assertEqual(got["top"], 60 - 6 - (12 + 17.5 * 2))

    def test_when_no_side_has_140_px_it_wraps_to_the_room_it_has_down_to_100_px_before_it_covers_the_element(self):
        got = self.r["fit"][7]
        self.assertEqual((got["side"], got["maxWidth"], got["lines"]), ("left", 115, 2))
        self.assertEqual(got["left"], 0, "its right edge is 6 px from the element")

    def test_with_no_room_anywhere_it_is_clamped_over_the_element_inside_the_wrapper(self):
        got = self.r["fit"][5]
        self.assertEqual((got["side"], got["maxWidth"], got["top"], got["lines"]), ("over", 100, 0, 1))
        narrow = self.r["fit"][6]
        self.assertEqual((narrow["maxWidth"], narrow["left"]), (120, 0), "a wrapper under 140 px wide wins over the 140 px minimum")

    def test_the_link_table(self):
        got = {u: r for u, r in zip(LINKS, self.r["links"])}
        self.assertTrue(got["https://example.com/a"]["ok"])
        for bad in LINKS[1:]:
            with self.subTest(link=bad):
                self.assertFalse(got[bad]["ok"])
                self.assertTrue(got[bad]["reason"])
        self.assertIn("javascript: scheme", got["javascript:alert(1)"]["reason"])
        self.assertIn("lowercase", got["HTTP://example.com"]["reason"])

    def test_a_link_shows_what_the_click_opens(self):
        # B1. The app opens new URL(link).toString(), so a lookalike host, a bidi override or a bad port must not pass.
        for (url, good, parts), got in zip(LINK_ROWS, self.r["linkRows"]):
            with self.subTest(link=url):
                self.assertEqual(got["ok"], good, got)
                for part in parts:
                    self.assertIn(part, got.get("reason", ""))
                if good:
                    self.assertEqual(got["url"], url)

    def test_targets(self):
        seq, infra, erd, dag = self.r["targets"]
        self.assertEqual(seq["keys"], ["client", "api", "m1", "m2"], "nested message ids count; a message without an id is not a target")
        self.assertEqual(infra["keys"], ["zone:Edge", "web", "api", "web>api"])
        self.assertEqual(infra["count"]["web>api"], ["link", "link"])
        self.assertEqual(erd["keys"], ["orders", "orders.id", "orders.user_id", "orders.total"])
        self.assertEqual(dag["keys"], ["a", "b"])

    def test_the_checker_is_pure_and_reports_an_unknown_target(self):
        self.assertEqual(self.r["checks"][0], ["Dag tooltip target `zzz` matches no element (valid targets: a, b)."])

    def test_the_code_limit_is_forty_lines_inclusive(self):
        self.assertEqual(self.r["checks"][1], [])
        self.assertEqual(self.r["checks"][2], ["Tooltip for `a`: code has 41 lines; the limit is 40."])
        self.assertEqual(self.r["checks"][3], [], "trailing blank lines do not count")

    def test_ambiguous_targets_are_reported_by_the_pure_checker(self):
        self.assertEqual(self.r["checks"][4], ["SequenceDiagram tooltip target `client` is ambiguous: it is both a participant id and a message id (give the message another id)."])
        self.assertEqual(self.r["checks"][5], ["InfraMap tooltip target `web>api` is ambiguous: 2 links join `web` to `api` (remove the extra links, or put the tooltip on the nodes instead)."])

    def test_a_node_id_with_a_greater_than_sign_does_not_confuse_the_link_message(self):
        # S6. `a>b -> c` and `a -> b>c` both read a>b>c; the message names the two real links instead of splitting the string.
        self.assertEqual(self.r["checks"][6], ["InfraMap tooltip target `a>b>c` is ambiguous: it matches 2 links (`a>b` to `c`, `a` to `b>c`); a node id with `>` in it makes the target unclear, so rename it."])


# ---- the real validator, one message per mistake ------------------------------------------------------------------------

@unittest.skipUnless(node_ok() and bundle.VALIDATOR.is_file(), "needs Node and assets/validate.cjs")
class Validator(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)

    def run_case(self, text):
        return validate(text, self.td.name)

    def ok(self, text):
        code, out = self.run_case(text)
        self.assertEqual(code, 0, out)

    def problems(self, text):
        code, out = self.run_case(text)
        self.assertEqual(code, 1, out)
        return problems_of(out)

    def test_valid_targets_for_each_diagram_pass(self):
        full = tt("build", "Build step", "Runs the image build.", "docker build .", "bash", "warn", "https://example.com/docs/build", "Build docs")
        self.ok(dag_src(full, tt("ship", "Ships it")))
        self.ok(erd_src(tt("users", "Accounts"), tt("orders.user_id", "FK to users", tone="info"), tt("orders.total", detail="In cents.")))
        self.ok(infra_src(tt("zone:Edge", "Public edge", tone="warn"), tt("client", "Browser"), tt("client>web", "TLS ends here")))
        self.ok(seq_src(tt("client", "The caller"), tt("login", "Rate limited", code="POST /login", language="http")))

    def test_an_unknown_target_lists_up_to_five_valid_ones(self):
        self.assertEqual(self.problems(dag_src(tt("biuld", "x"))), ["Dag tooltip target `biuld` matches no element (valid targets: build, unit, ship)."])
        self.assertEqual(self.problems(erd_src(tt("orders.nope", "x"))), ["Erd tooltip target `orders.nope` matches no element (valid targets: users, users.id, users.email, orders, orders.id and 2 more)."])
        self.assertEqual(self.problems(infra_src(tt("zone:Nope", "x"))), ["InfraMap tooltip target `zone:Nope` matches no element (valid targets: zone:Edge, client, web, zone:Core, api and 2 more)."])
        self.assertEqual(self.problems(seq_src(tt("m9", "x"))), ["SequenceDiagram tooltip target `m9` matches no element (valid targets: client, api, login, reply)."])

    def test_a_message_without_an_id_cannot_have_a_tooltip(self):
        out = self.problems(seq_src(tt("POST /login", "x")))
        self.assertEqual(len(out), 1)
        self.assertIn("matches no element", out[0])

    def test_a_duplicate_target(self):
        self.assertEqual(self.problems(dag_src(tt("build", "a"), tt("build", "b"))), ["Dag has more than one tooltip for target `build` (keep one Tooltip per element)."])

    def test_two_links_between_the_same_nodes_are_ambiguous(self):
        self.assertEqual(
            self.problems(infra_src(tt("web>api", "x"), extra_link=True)),
            ["InfraMap tooltip target `web>api` is ambiguous: 2 links join `web` to `api` (remove the extra links, or put the tooltip on the nodes instead)."])

    def test_a_message_id_that_is_also_a_participant_id_is_ambiguous(self):
        self.assertEqual(
            self.problems(seq_src(tt("client", "x"), dup_id=True)),
            ["SequenceDiagram tooltip target `client` is ambiguous: it is both a participant id and a message id (give the message another id)."])

    def test_an_item_that_is_not_a_tooltip(self):
        src = dag_src(tt("build", "x")).replace("[Tooltip", '[t, Tooltip', 1) + 't = Text("hi")\n'
        out = self.problems(src)
        self.assertEqual(out, ["Dag `tooltips` can hold only Tooltip, but item 1 is Text (give each remark as Tooltip(target, hint?, detail?, code?, language?, tone?, link?, linkLabel?))."])

    def test_a_tooltip_that_would_do_nothing(self):
        self.assertEqual(self.problems(dag_src(tt("build"))), ["Tooltip for `build` has none of hint, detail, code or link, so it would do nothing (add one of them, or remove the Tooltip)."])
        self.assertEqual(self.problems(dag_src(tt("build", hint="  "))), ["Tooltip for `build` has none of hint, detail, code or link, so it would do nothing (add one of them, or remove the Tooltip)."])

    def test_the_limits(self):
        cases = [
            (tt("build", "h" * 141), "Tooltip for `build`: hint is 141 characters; the limit is 140."),
            (tt("build", detail="d" * 801), "Tooltip for `build`: detail is 801 characters; the limit is 800."),
            (tt("build", code="c" * 2001), "Tooltip for `build`: code is 2001 characters; the limit is 2000."),
            (tt("build", code="\n".join(["x"] * 41)), "Tooltip for `build`: code has 41 lines; the limit is 40."),
            (tt("build", "h", language="l" * 21), "Tooltip for `build`: language is 21 characters; the limit is 20."),
            (tt("build", "h", link="https://example.com/", label="L" * 61), "Tooltip for `build`: linkLabel is 61 characters; the limit is 60."),
            (tt("build", "h", link="https://example.com/" + "a" * 300), None),
        ]
        for line, expected in cases:
            with self.subTest(expected=expected):
                out = self.problems(dag_src(line))
                if expected:
                    self.assertEqual(out, [expected])
                else:
                    self.assertEqual(len(out), 1)
                    self.assertIn("characters; the limit is 300", out[0])

    def test_the_limits_are_inclusive(self):
        self.ok(dag_src(tt("build", "h" * 140, "d" * 800, "\n".join(["c"] * 40), "l" * 20, "info", "https://example.com/" + "a" * 280, "L" * 60)))

    def test_at_most_sixty_tooltips_per_diagram(self):
        nodes = ["n%d" % i for i in range(61)]
        src = "root = Stack([d])\nd = Dag([%s], [], null, null, [%s])\n" % (", ".join("v" + n for n in nodes), ", ".join("a" + n for n in nodes))
        src += "".join('v%s = DagNode("%s", "N")\na%s = Tooltip("%s", "h")\n' % (n, n, n, n) for n in nodes)
        self.assertEqual(self.problems(src), ["Dag has 61 tooltips; use at most 60 (add a tooltip only where there is something worth saying)."])

    def test_a_made_up_tone_is_a_schema_error(self):
        code, out = self.run_case(dag_src(tt("build", "x", tone="loud")))
        self.assertEqual(code, 1, out)
        self.assertIn("OpenUI validation FAILED", out)

    LINK_CASES = [
        ("http://example.com/a", True, ""),
        ("https://example.com/a?x=1#top", True, ""),
        ("https://example.com:8443/a", True, ""),
        ("javascript:alert(1)", False, "uses the javascript: scheme; only http:// and https:// links are accepted"),
        ("data:text/html,<b>x</b>", False, "uses the data: scheme"),
        ("file:///etc/passwd", False, "uses the file: scheme"),
        ("vbscript:msgbox(1)", False, "uses the vbscript: scheme"),
        ("mailto:a@example.com", False, "uses the mailto: scheme"),
        ("//example.com/x", False, "has no scheme (it starts with //); start it with https://"),
        ("HTTP://example.com/", False, "does not start with lowercase http:// or https://"),
        ("example.com/docs", False, "does not start with http:// or https://"),
        ("https://user:secret@example.com/", False, "contains a user:password@ part; remove the credentials"),
        ("https://exa mple.com/", False, "contains whitespace or a control character"),
        ("https://example.com/\ta", False, "contains whitespace or a control character"),
        ("https://", False, "has no host"),
        ("", False, "is empty (leave the link out, or pass null)"),
        ("https://\u0430pple.com/login", False, "U+0430"),
        ("https://example.com/\u202egpj.exe", False, "U+202E"),
        ("https://x.com:99999999/", False, "port"),
    ]

    def test_the_link_scheme_table(self):
        for url, good, reason in self.LINK_CASES:
            with self.subTest(link=url):
                code, out = self.run_case(dag_src(tt("build", "x", link=url)))
                if good:
                    self.assertEqual(code, 0, out)
                else:
                    self.assertEqual(code, 1, out)
                    got = problems_of(out)
                    self.assertEqual(len(got), 1, got)
                    self.assertTrue(got[0].startswith("Tooltip for `build`: link `"), got[0])
                    self.assertIn(reason, got[0])

    def test_the_other_diagrams_check_the_same_way(self):
        for src in (erd_src(tt("users", "x", link="javascript:alert(1)")), infra_src(tt("web", "x", link="ftp://example.com/")), seq_src(tt("api", "x", link="//example.com"))):
            with self.subTest(src=src.splitlines()[1][:30]):
                out = self.problems(src)
                self.assertEqual(len(out), 1)
                self.assertIn("link `", out[0])

    def test_without_tooltips_nothing_changes(self):
        self.ok(dag_src())
        self.ok(dag_src().replace(", null, null, [])", ")"))

    def test_the_message_for_a_lookalike_host_says_what_to_do(self):
        out = self.problems(dag_src(tt("build", "x", link="https://\u0430pple.com/login")))
        self.assertEqual(len(out), 1, out)
        self.assertIn("write the host in ASCII, as punycode if needed", out[0])

    STRAY = "Tooltip `%s` is used outside a component that takes tooltips: a Tooltip only goes in the last argument (`tooltips`) of Dag, Erd, InfraMap, SequenceDiagram, Table, Metric, BarChart, GeoMap or Image, for example `Dag(nodes, edges, null, null, [%s])`."

    def test_a_tooltip_that_is_not_in_a_diagram_is_an_error(self):
        # S4. The component draws nothing, so a misplaced one used to give an empty widget and ok: true.
        self.assertEqual(self.problems('root = Stack([t1])\nt1 = Tooltip("login", "x")\n'), [self.STRAY % ("t1", "t1")])

    def test_a_tooltip_used_as_a_child_anywhere_else_is_an_error(self):
        card = 'root = Stack([c])\nc = Card([t1])\nt1 = Tooltip("login", "x")\n'
        self.assertEqual(self.problems(card), [self.STRAY % ("t1", "t1")])
        both = "\n".join(["root = Stack([d, a1])", "d = Dag([n1], [], null, null, [a1])", 'n1 = DagNode("build", "Build")', 'a1 = Tooltip("build", "x")']) + "\n"
        self.assertEqual(self.problems(both), [self.STRAY % ("a1", "a1")], "one Tooltip in the diagram's tooltips AND in a Stack is still outside a diagram")

    def test_a_tooltip_that_nothing_refers_to_is_reported_like_any_unreachable_variable(self):
        out = self.problems(dag_src(tt("build", "x")) + 'extra = Tooltip("ship", "y")\n')
        self.assertEqual(len(out), 1, out)
        self.assertIn("`extra` is defined but not reachable from root", out[0])

    def test_a_node_id_with_a_greater_than_sign_names_the_two_real_links(self):
        src = "\n".join([
            "root = Stack([m])", 'm = InfraMap([z], [l1, l2], null, null, [t])',
            'z = InfraZone("Z", [n1, n2, n3, n4])',
            'n1 = InfraNode("a", "A")', 'n2 = InfraNode("b>c", "BC")', 'n3 = InfraNode("a>b", "AB")', 'n4 = InfraNode("c", "C")',
            'l1 = InfraLink("a>b", "c")', 'l2 = InfraLink("a", "b>c")', 't = Tooltip("a>b>c", "x")',
        ]) + "\n"
        self.assertEqual(self.problems(src), ["InfraMap tooltip target `a>b>c` is ambiguous: it matches 2 links (`a>b` to `c`, `a` to `b>c`); a node id with `>` in it makes the target unclear, so rename it."])


class ToolPath(unittest.TestCase):
    """The same checks through render_widget, the path the agent uses."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.old = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.td.name
        self.addCleanup(self.cleanup)

    def cleanup(self):
        if self.old is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self.old
        self.td.cleanup()

    @unittest.skipUnless(node_ok() and bundle.VALIDATOR.is_file(), "needs Node and assets/validate.cjs")
    def test_render_widget_refuses_a_free_standing_tooltip_and_writes_nothing(self):
        r = json.loads(tools.render_widget({"source": 'root = Stack([t1])\nt1 = Tooltip("login", "x")\n'}, mode="preview"))
        self.assertFalse(r["ok"], r)
        self.assertTrue(any("Tooltip `t1` is used outside a component that takes tooltips" in e for e in r["errors"]), r)
        widgets = Path(self.td.name) / "widgets"
        self.assertEqual(sorted(widgets.glob("*")) if widgets.exists() else [], [])


# ---- the markup the four views draw -------------------------------------------------------------------------------------

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
  'import { Tooltip } from "./components/tooltip-schema.js";',
  'import { pack as diagrams } from "./packs/diagrams.jsx";',
  'import { pack as infra } from "./packs/infra.jsx";',
  'import { pack as sequence } from "./packs/sequence.jsx";',
  'export { React, renderToStaticMarkup, lang, createParser, Tooltip, diagrams, infra, sequence };',
].join("\n");
const built = esbuild.buildSync({
  stdin: { contents: entry, resolveDir: path.join(cfg.build, "src"), loader: "js", sourcefile: "tip-harness.js" },
  bundle: true, platform: "node", format: "cjs", jsx: "automatic", write: false, logLevel: "error",
  define: { "process.env.NODE_ENV": '"production"' },
});
const mod = { exports: {} };
new Function("module", "exports", "require", built.outputFiles[0].text)(mod, mod.exports, require);
const { React, renderToStaticMarkup, lang, createParser, Tooltip, diagrams, infra, sequence } = mod.exports;
const zod = req("zod/v4");
const Stack = lang.defineComponent({ name: "Stack", description: "stack", props: zod.object({ children: zod.array(zod.any()) }), component: () => null });
const all = [].concat(diagrams.components, infra.components, sequence.components);
const library = lang.createLibrary({ root: "Stack", components: [Stack, Tooltip].concat(all) });
const parser = createParser(library.toJSONSchema(), library.root);
const out = {};
const walk = (n, fn) => { if (n && typeof n === "object") { if (n.typeName) fn(n); for (const v of Object.values(n.props || {})) (Array.isArray(v) ? v : [v]).forEach((c) => walk(c, fn)); } };
for (const [name, src] of Object.entries(cfg.sources)) {
  const { root, meta } = parser.parse(src);
  const ex = { parsed: !!root, errors: (meta.errors || []).map((e) => e.message || String(e)), unresolved: meta.unresolved, html: "" };
  walk(root, (n) => {
    const comp = all.find((c) => c.name === n.typeName);
    if (comp && ["Dag", "Erd", "InfraMap", "SequenceDiagram"].includes(n.typeName)) ex.html = renderToStaticMarkup(React.createElement(comp.component, { props: n.props }));
  });
  out[name] = ex;
}
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipIf(node_missing_reason(), node_missing_reason() or "")
class Markup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources = {
            "dag": dag_src(tt("build", "Build step", "Runs the build.", "docker build .", "bash", "warn", "https://example.com/b", "Docs")),
            "dag_plain": dag_src(),
            "erd": erd_src(tt("users", "Accounts"), tt("orders.user_id", "FK to users", tone="good")),
            "infra": infra_src(tt("zone:Edge", "Public edge", tone="warn"), tt("web", "Gateway"), tt("web>api", "gRPC", tone="bad")),
            "infra_plain": infra_src(),
            "seq": seq_src(tt("client", "The caller"), tt("login", "Rate limited", tone="bad")),
            "seq_plain": seq_src(),
        }
        r = subprocess.run(["node", "-"], input=RENDER_HARNESS, capture_output=True, text=True, cwd=str(BUILD), timeout=120, env=dict(ENV, TIP_CFG=json.dumps({"build": str(BUILD), "sources": sources})))
        if r.returncode != 0:
            raise AssertionError("node render harness failed:\n" + (r.stderr or r.stdout)[-2000:])
        cls.r = json.loads(r.stdout)

    def html(self, name):
        ex = self.r[name]
        self.assertTrue(ex["parsed"], ex)
        self.assertEqual((ex["unresolved"], ex["errors"]), ([], []), ex)
        self.assertIn("<svg", ex["html"])
        return ex["html"]

    def hot(self, html, key):
        return re.findall(r'<g[^>]*data-tip="%s"[^>]*>' % re.escape(key.replace("&", "&amp;").replace(">", "&gt;")), html)

    def test_a_tooltip_element_is_a_focusable_button_with_a_label_and_a_marker(self):
        for name, keys in (("dag", ["build"]), ("erd", ["users", "orders.user_id"]), ("infra", ["zone:Edge", "web", "web>api"]), ("seq", ["client", "login"])):
            html = self.html(name)
            for key in keys:
                with self.subTest(diagram=name, target=key):
                    tags = self.hot(html, key)
                    self.assertTrue(tags, "no element for %s" % key)
                    tag = tags[0]
                    self.assertIn('tabindex="0"', tag)
                    self.assertIn('role="button"', tag)
                    self.assertIn("aria-label=", tag)
                    self.assertIn('aria-expanded="false"', tag)
                    self.assertIn("cursor:pointer", tag)

    def test_the_marker_is_a_small_dot_in_the_tone_colour(self):
        html = self.html("infra")
        dots = [c for c in re.findall(r"<circle[^>]*>", html) if 'r="3"' in c and 'pointer-events="none"' in c]
        for colour in ("#f85149", "#d29922"):
            with self.subTest(colour=colour):
                self.assertTrue([c for c in dots if 'fill="%s"' % colour in c], dots)

    def test_other_elements_are_left_alone(self):
        html = self.html("dag")
        self.assertEqual(html.count("data-tip="), 1)
        self.assertNotIn("tabindex", html.replace(self.hot(html, "build")[0], ""))

    def test_a_diagram_without_tooltips_is_drawn_as_before(self):
        for name in ("dag_plain", "infra_plain", "seq_plain"):
            with self.subTest(diagram=name):
                html = self.html(name)
                for word in ("data-tip", "tabindex", "role=\"button\"", "position:relative"):
                    self.assertNotIn(word, html)

    def test_a_tooltip_element_has_no_native_title_that_would_double_the_tooltip(self):
        html = self.html("seq")
        found = re.search(r'<g[^>]*data-tip="login"[^>]*>.*?</g>', html, re.S)
        self.assertIsNotNone(found)
        grp = found.group(0) if found else ""
        self.assertNotIn("<title>", grp)
        self.assertIn("<title>", html, "the messages and headers without a tooltip keep theirs")

    def test_a_tooltip_svg_is_a_group_not_an_image_so_the_buttons_stay_reachable(self):
        for name in ("infra", "seq"):
            with self.subTest(diagram=name):
                html = self.html(name)
                self.assertNotIn('role="img"', html)
                self.assertIn('role="group"', html)
        self.assertIn('role="img"', self.html("seq_plain"))

    def test_a_row_of_text_gets_a_transparent_hit_rectangle_so_it_can_be_hovered_between_its_glyphs(self):
        html = self.html("erd")
        col = re.search(r'<g[^>]*data-tip="orders.user_id"[^>]*>.*?</g>', html, re.S)
        self.assertIsNotNone(col)
        self.assertIn('fill="transparent"', col.group(0) if col else "")
        self.assertIn('pointer-events="all"', col.group(0) if col else "")

    def test_the_diagram_sits_in_a_relative_wrapper(self):
        for name in ("dag", "erd", "infra", "seq"):
            with self.subTest(diagram=name):
                self.assertIn("position:relative", self.html(name))


# ---- the sources of the shared view -------------------------------------------------------------------------------------

class ViewSource(unittest.TestCase):
    TEXT = (SRC / "components" / "tooltips.jsx").read_text(encoding="utf-8") if (SRC / "components" / "tooltips.jsx").is_file() else ""

    def test_the_view_has_the_pieces_the_brief_asks_for(self):
        for needle in ("getBoundingClientRect", "placeTooltip", 'role="tooltip"', "pointerEvents", "pos.maxWidth", "aria-describedby", "Escape", "CodeView", "openExternal", "checkLink", "enableNativeLinks"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.TEXT)

    def test_the_panel_takes_focus_so_escape_works_after_a_click_inside_it(self):
        self.assertIn("tabIndex={-1}", self.TEXT)

    def test_focus_comes_back_after_a_copy_and_after_the_panel_closes_so_escape_keeps_working(self):
        code = (SRC / "components" / "code.jsx").read_text(encoding="utf-8")
        self.assertIn("preventScroll", code, "copyText must give focus back after its hidden textarea took it")
        self.assertRegex(self.TEXT, r"opener|\.focus\(\{ preventScroll: true \}\)")
        self.assertIn("closePanel", self.TEXT)

    def test_escape_that_closes_the_panel_is_marked_handled_so_the_app_does_not_also_stop_the_turn(self):
        # S1. The app's Escape handler (it cancels the running turn) is a window listener that skips a defaultPrevented event.
        block = re.search(r'if \(e\.key === "Escape"\) \{(.*?)\n    \}', self.TEXT, re.S)
        self.assertIsNotNone(block)
        text = block.group(1) if block else ""
        closing = re.search(r"if \(cur\) \{(.*?)\n      \}", text, re.S)
        self.assertIsNotNone(closing, "the close branch must be a block")
        inner = closing.group(1) if closing else ""
        self.assertIn("e.preventDefault()", inner)
        self.assertLess(inner.index("preventDefault"), inner.index("closePanel()"))
        self.assertNotIn("preventDefault", text.replace(inner, ""), "an Escape with nothing to close must still reach the app")
        self.assertNotIn("stopPropagation", self.TEXT, "the app's own handler is a window listener: keep bubbling")

    def test_the_tooltip_is_sized_by_the_placement_so_it_wraps_and_is_cut_with_a_line_clamp(self):
        for needle in ("pos.maxWidth", "WebkitLineClamp", "measure"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.TEXT)

    def test_a_different_set_of_tooltips_closes_the_panel_and_clears_the_hover(self):
        # Found in Chrome: inside Tabs, React keeps the diagram's component when the tab changes, so a panel that was open on the first tab
        # showed up (with the first tab's name) on the second one. Whatever belonged to the old tooltips must go.
        m = re.search(r"if \((\w+) !== list\) \{(.*?)\}", self.TEXT, re.S)
        self.assertIsNotNone(m, "Tipped must notice a new list of tooltips")
        body = m.group(2) if m else ""
        for call in ("setOpen(null)", "setHover(null)", "setFocus(null)", "setPos(null)"):
            with self.subTest(call=call):
                self.assertIn(call, body)

    def test_it_draws_no_anchor_and_navigates_nowhere(self):
        self.assertNotRegex(self.TEXT, r"<a[\s>]")
        for bad in ("href", "window.open", "location.", "target=\"_blank\"", "dangerouslySetInnerHTML", "innerHTML", "eval(", "new Function"):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, self.TEXT)

    def test_open_external_is_called_only_in_native_mode_through_the_bridge_check(self):
        self.assertRegex(self.TEXT, r"typeof [\w.]*openExternal === \"function\"")
        self.assertEqual(self.TEXT.count(".openExternal("), 1)

    def test_the_desktop_plugin_turns_the_native_links_on_and_the_preview_never_does(self):
        self.assertIn("enableNativeLinks", (SRC / "plugin" / "plugin.jsx").read_text(encoding="utf-8"))
        self.assertNotIn("enableNativeLinks", (SRC / "core.jsx").read_text(encoding="utf-8"))
        self.assertNotIn("enableNativeLinks", (SRC / "components" / "diagrams.jsx").read_text(encoding="utf-8"))

    def test_the_on_action_rule_that_ignores_open_url_is_unchanged(self):
        text = (SRC / "plugin" / "plugin.jsx").read_text(encoding="utf-8")
        self.assertIn('event.type !== "continue_conversation"', text)
        self.assertIn("open_url: not allowed", text)

    def test_the_shipped_files_have_no_network_code(self):
        rx = re.compile(r"fetch\(|XMLHttpRequest|sendBeacon|WebSocket\(|EventSource\(|posthog|cloudfront")
        for name, info in bundle.manifest()["packs"].items():
            text = gzip.decompress((bundle.ASSETS / info["file"]).read_bytes()).decode("utf-8")
            with self.subTest(pack=name):
                self.assertIsNone(rx.search(text))
        self.assertIsNone(rx.search((ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8")))

    def test_the_native_build_carries_the_view(self):
        text = (ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8")
        self.assertIn("openExternal", text)
        self.assertIn("Click for details", text)

    def test_the_stage_two_features_are_not_here(self):
        for word in ("composer", "submit(", "continue_conversation", "hermes.send", "localStorage"):
            with self.subTest(word=word):
                self.assertNotIn(word, self.TEXT)


# ---- the Chrome driver step list (tools/shoot.py --steps) ---------------------------------------------------------------

def load_shoot():
    import importlib.util
    spec = importlib.util.spec_from_file_location("shoot_for_steps", ROOT / "tools" / "shoot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ShootSteps(unittest.TestCase):
    def test_a_step_list_is_checked_before_chrome_starts(self):
        shoot = load_shoot()
        good = '[{"move": "[data-tip=\\"a\\"]"}, {"click": "#x"}, {"key": "Tab"}, {"key": "Shift+Tab"}, {"js": "1"}, {"eval": "2", "name": "two"}, {"shot": "a.png"}]'
        self.assertEqual(len(shoot.parse_steps(good)), 7)
        for bad in ('{"move": "#a"}', '[{"hover": "#a"}]', '[{"move": "#a", "click": "#b"}]', '[{"key": "F13"}]', '[{"eval": "1"}]', '[{"shot": "../a.png"}]', "not json", '[{"move": 5}]'):
            with self.subTest(bad=bad):
                with self.assertRaises(SystemExit):
                    shoot.parse_steps(bad)

    def test_steps_are_accepted_by_both_modes_and_need_nothing_else(self):
        shoot = load_shoot()
        a = shoot.parse_args(["x.oui", "o.png", "--steps", '[{"key": "Tab"}]'])
        self.assertEqual(a.steps, '[{"key": "Tab"}]')
        b = shoot.parse_args(["--html", "p.html", "o.png", "--steps", '[{"key": "Tab"}]'])
        self.assertEqual(b.steps, '[{"key": "Tab"}]')


# ---- docs, guidance, changelog ------------------------------------------------------------------------------------------

class Docs(unittest.TestCase):
    PAGE = DOCS / "Tooltip.md"

    def test_the_page_and_three_examples_exist_with_screenshots(self):
        self.assertTrue(self.PAGE.is_file())
        for name in DOC_EXAMPLES:
            with self.subTest(example=name):
                self.assertTrue((EXAMPLES / name).is_file())
                self.assertTrue((DOCS / "images" / (name[:-4] + ".png")).is_file())

    def test_the_examples_use_generic_names_and_example_dot_com_links_only(self):
        for name in DOC_EXAMPLES:
            text = (EXAMPLES / name).read_text(encoding="utf-8")
            with self.subTest(example=name):
                for url in re.findall(r"https?://[^\"\s]+", text):
                    self.assertRegex(url, r"^https://example\.com/")
                rest = re.sub(r"https://example\.com/[^\"\s]*", "", text)
                self.assertEqual(helpers.private_setup_hits(rest), [])
                self.assertNotRegex(text, "\u2014|\u2013")

    def test_the_page_covers_what_the_brief_lists(self):
        text = self.PAGE.read_text(encoding="utf-8")
        for needle in ("`target`", "node id", "entity.column", "zone:", "`web>api`", "message", "without an `id`", "hover", "Escape", "native", "desktop", "Copy", "60 tooltips", "140", "800", "2,000", "40 lines", "http://", "https://", "When not to add a tooltip", "ambiguous", "tone"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        self.assertNotRegex(text, "\u2014|\u2013")

    def test_each_diagram_page_has_a_tooltips_section_with_its_own_example(self):
        for page_name, example in (("Dag", "dag-tooltips"), ("Erd", "erd-tooltips"), ("InfraMap", "infra-map-tooltips"), ("SequenceDiagram", "sequence-diagram-tooltips")):
            text = (DOCS / (page_name + ".md")).read_text(encoding="utf-8")
            with self.subTest(page=page_name):
                self.assertRegex(text, r"(?m)^## Tooltips\s*$")
                self.assertIn("images/%s.png" % example, text)
                self.assertIn("[Tooltip](Tooltip.md)", text)

    def test_the_erd_example_uses_a_sql_snippet_and_the_dag_one_a_python_snippet(self):
        self.assertRegex((EXAMPLES / "erd-tooltips.oui").read_text(encoding="utf-8"), r'"sql"')
        self.assertRegex((EXAMPLES / "dag-tooltips.oui").read_text(encoding="utf-8"), r'"(python|bash)"')

    def test_the_page_tells_the_agent_how_tall_a_diagram_with_tooltips_may_be_in_preview_mode(self):
        text = self.PAGE.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^#{3,4} Height in preview mode\s*$")
        for needle in ("about 70 px", "about 400 px", "under about 800 px", "about 20 steps", "about 8 rows", "1,200", "no height cap"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_the_page_documents_the_last_argument_two_panels_and_the_cut_hint(self):
        text = self.PAGE.read_text(encoding="utf-8")
        for needle in ("LAST argument", "Dag(nodes, edges, null, null, [t1, t2])", "two panels", "ellipsis", "images/tooltip-hover.png"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        self.assertLess(text.index("tooltip-hover.png"), text.index("## Signature"), "the hover image is at the top")
        self.assertNotIn("The tooltip stays inside the diagram and flips", text, "the old sentence was not true")
        self.assertLess((DOCS / "images" / "tooltip-hover.png").stat().st_size, 100 * 1024)

    def test_no_code_line_in_an_example_is_wider_than_the_code_box(self):
        for name in DOC_EXAMPLES:
            for line in (EXAMPLES / name).read_text(encoding="utf-8").splitlines():
                m = re.match(r"^\w+ = Tooltip\((.*)\)$", line)
                if not m:
                    continue
                code = json.loads("[" + m.group(1) + "]")[3:4]
                for row in (code[0] or "").split("\n") if code and code[0] else []:
                    with self.subTest(example=name, row=row[:30]):
                        self.assertLessEqual(len(row), 64, "the code box is about 70 characters wide, the rest is cut in a screenshot")

    def test_the_zod_description_tells_the_agent_about_the_last_argument_and_the_height(self):
        desc = reference_line("Tooltip").split(" \u2014 ", 1)[1]
        for needle in ("LAST argument", "null", "800 px", "70", "400"):
            with self.subTest(needle=needle):
                self.assertIn(needle, desc)

    def test_the_stale_figures_and_names_are_fixed(self):
        dev = (ROOT / "docs" / "development.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("3,700", dev)
        table = re.search(r"\| Component reference \| the first use in a chat \| about ([\d,]+) \|", readme).group(1)
        self.assertIn("about %s tokens" % table, dev)
        self.assertIn("the %s-token first use" % table, dev)
        self.assertIn("from about 3,700 to %s tokens" % table, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertIn("<b>Hover details</b> &middot; <a href=\"docs/ui-components/Tooltip.md\">Tooltip</a>", readme)
        self.assertNotIn("<b>Tooltip</b> &middot;", readme)

    def test_the_agent_rules_say_an_additive_internal_key_is_not_a_breaking_change(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("An additive, internal `window.__HM.mods` key", agents)
        self.assertIn("does not bump `api`", agents)
        self.assertIn("removing or renaming a documented key is", agents)

    def test_the_docs_gate_passes_and_counts_the_new_total(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_docs.py")], capture_output=True, text=True, timeout=250, env=ENV)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("all 38 components documented", r.stdout)

    def test_the_gallery_index_and_the_readme_count_the_new_component(self):
        index = (DOCS / "README.md").read_text(encoding="utf-8")
        self.assertIn("[**Tooltip**](Tooltip.md)", index)
        self.assertIn("There are 24 components, plus 14 small helpers", index)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("**24 components** (38 with helpers)", readme)
        self.assertRegex(readme, r"(?m)^#{2,4} Tooltips\s*$")
        self.assertIn("tooltip", readme[:4000].lower(), "the feature list names tooltips")
        start = readme.index("Tooltips")
        self.assertNotRegex(readme[start:start + 2500], "\u2014|\u2013")


class Guidance(unittest.TestCase):
    TEXT = (ROOT / "skills" / "openui-render" / "SKILL.md").read_text(encoding="utf-8")

    def test_the_skill_tells_the_agent_when_to_add_a_tooltip(self):
        low = self.TEXT.lower()
        self.assertIn("tooltip", low)
        for word in ("about 8", "native"):
            self.assertIn(word, low)
        self.assertTrue(self.TEXT.startswith("---\nname: openui-render\n"))
        self.assertRegex(self.TEXT, r"(?m)^version: 0\.3\.0$")

    def test_the_skill_says_tooltips_is_the_last_argument_and_how_tall_the_diagram_may_be(self):
        self.assertLessEqual(len(self.TEXT), 5000)
        for needle in ("LAST argument", "`null`", "800 px"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.TEXT)

    def test_the_skill_cap_is_raised_once_to_5000_in_every_test_that_pins_it(self):
        self.assertLessEqual(len(self.TEXT), 5000)
        self.assertGreater(len(self.TEXT), 4376, "the lines were not added")
        for rel in ("tests/test_plugin.py", "tests/test_custom_components_skill.py", "tests/test_sequence_builtin.py"):
            with self.subTest(file=rel):
                self.assertIn("5000", (ROOT / rel).read_text(encoding="utf-8"))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        m = re.search(r"`hermes-openui:openui-render`, about ([\d,]+) tokens", readme)
        self.assertIsNotNone(m)
        self.assertLessEqual(abs(int(m.group(1).replace(",", "")) - len(self.TEXT) / 4), 25)
        self.assertIn("5,000", (ROOT / "AGENTS.md").read_text(encoding="utf-8"))

    def test_the_readme_figure_for_the_reference_is_still_true(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        table = re.search(r"\| Component reference \| the first use in a chat \| about ([\d,]+) \|", readme)
        self.assertIsNotNone(table)
        real = (ROOT / "assets" / "components.md").stat().st_size / 4
        self.assertLessEqual(abs(int(table.group(1).replace(",", "")) - real), 50, "components.md is about %d tokens" % real)


class Changelog(unittest.TestCase):
    def test_unreleased_lists_tooltips_under_added_and_names_the_reserved_word(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        sec = re.split(r"(?m)^(?=## \[)", text)[1]
        self.assertRegex(sec, r"^## \[Unreleased\]")
        self.assertIn("### Added", sec)
        self.assertIn("Tooltip", sec)
        self.assertRegex(sec, r"reserved")
        self.assertNotRegex(sec, "\u2014|\u2013")


if __name__ == "__main__":
    unittest.main()
