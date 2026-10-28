"""The built-in InfraMap components (InfraNode, InfraZone, InfraLink, InfraMap), shipped in the optional `infra` pack.

Four layers: the manifest and the reference the model reads; the sample sources in tests/fixtures/infra/ through lint, the page
builder and the real validator (`node assets/validate.cjs`, no --pack); the cross-reference checks, one message each; and, when
Node and build/node_modules are present, the renderer and its layout engine run for real (SVG markup, geometry). A last class
loads a page in headless Chrome through tools/shoot.py when a Chrome exists.
"""
import gzip
import importlib.util
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

ROOT = helpers.ROOT
FIXTURES = ROOT / "tests" / "fixtures" / "infra"
GOOD = ["map.oui", "minimal.oui", "tb.oui"]
BAD = "bad.oui"
NAMES = ["InfraNode", "InfraZone", "InfraLink", "InfraMap"]

# The signatures the model read while this was a user-linked pack (its header lines). The built-in reference must say the same.
SIGNATURES = {
    "InfraNode": 'InfraNode(id: string, label: string, kind?: "client" | "gateway" | "service" | "gpu" | "database" | "storage" | "queue" | "cloud", status?: "up" | "degraded" | "down" | "unknown", detail?: string)',
    "InfraZone": 'InfraZone(name: string, nodes: InfraNode[], tone?: "neutral" | "info" | "good" | "warn" | "bad")',
    "InfraLink": 'InfraLink(from: string, to: string, label?: string, style?: "solid" | "dashed")',
    "InfraMap": 'InfraMap(zones: InfraZone[], links: InfraLink[], title?: string, direction?: "LR" | "TB")',
}
# Facts the descriptions must keep (they are the only place the model learns what the arguments mean).
DESCRIPTION_FACTS = {
    "InfraNode": ["unique", "InfraLink", "glyph", "health dot", "detail"],
    "InfraZone": ["labelled", "tints", "at least one node"],
    "InfraLink": ["curved arrow", "pill", "dashed"],
    "InfraMap": ["zones are columns", "top to bottom", "legend", "4 zones and 12 nodes"],
}


def fixture(name):
    return FIXTURES / name


def source(name):
    return lint.strip_fences(fixture(name).read_text(encoding="utf-8"))


def reference_line(name):
    lines = [ln for ln in bundle.reference_text().splitlines() if ln.startswith(name + "(")]
    assert len(lines) == 1, "%s appears %d times in components.md" % (name, len(lines))
    return lines[0]


def split_args(text):
    """`a: string, b?: "x" | "y"` -> [("a", False, "string"), ("b", True, '"x" | "y"')] (commas inside quotes or brackets do not split)."""
    out, depth, quote, cur = [], 0, False, ""
    for ch in text + ",":
        if ch == '"':
            quote = not quote
        if not quote and ch in "([":
            depth += 1
        if not quote and ch in ")]":
            depth -= 1
        if ch == "," and not quote and depth == 0:
            if cur.strip():
                out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    res = []
    for a in out:
        name, _, typ = a.partition(":")
        res.append((name.strip().rstrip("?"), name.strip().endswith("?"), typ.strip()))
    return res


def signature_args(name):
    sig = reference_line(name).split(" \u2014 ")[0]
    return split_args(sig[sig.index("(") + 1:sig.rindex(")")])


def node_available():
    return bool(shutil.which("node")) and bundle.VALIDATOR.is_file()


def run_validator(text, directory):
    """(exit code, output) of the shipped validator on `text`, with NO --pack: the components are built in."""
    path = Path(directory) / ("case-%d.oui" % len(list(Path(directory).iterdir())))
    path.write_text(text, encoding="utf-8")
    r = subprocess.run(["node", str(bundle.VALIDATOR), str(path)], capture_output=True, text=True, timeout=60, env=dict(os.environ, DO_NOT_TRACK="1"))
    return r.returncode, r.stdout + r.stderr


def build_map(zones, links, title=None, direction=None):
    """OpenUI Lang for a map: zones = [(name, [(id, label), ...], tone?)], links = [(from, to), ...]."""
    lines, zone_vars, link_vars = [], [], []
    for zi, zone in enumerate(zones):
        name, nodes = zone[0], zone[1]
        node_vars = []
        for ni, (nid, label) in enumerate(nodes):
            var = "n%d_%d" % (zi, ni)
            node_vars.append(var)
            lines.append('%s = InfraNode("%s", "%s")' % (var, nid, label))
        zone_vars.append("z%d" % zi)
        lines.append('z%d = InfraZone("%s", [%s]%s)' % (zi, name, ", ".join(node_vars), ', "%s"' % zone[2] if len(zone) > 2 else ""))
    for li, (a, b) in enumerate(links):
        link_vars.append("l%d" % li)
        lines.append('l%d = InfraLink("%s", "%s")' % (li, a, b))
    args = "[%s], [%s]" % (", ".join(zone_vars), ", ".join(link_vars))
    if title or direction:
        args += ', "%s"' % (title or "Map")
    if direction:
        args += ', "%s"' % direction
    return "root = Stack([m])\nm = InfraMap(%s)\n%s\n" % (args, "\n".join(lines))


class Manifest(unittest.TestCase):
    def test_the_four_components_belong_to_the_infra_pack_in_reference_order(self):
        m = bundle.manifest()
        self.assertEqual(m["packs"]["infra"]["components"], NAMES)
        for name in NAMES:
            self.assertEqual(m["components"][name], "infra", name)
            self.assertIn(name, bundle.component_names())

    def test_infra_is_a_pack_of_its_own_so_pages_without_it_do_not_get_heavier(self):
        m = bundle.manifest()
        self.assertEqual(sorted(m["packs"]), ["charts", "diagrams", "infra", "map", "text"])
        for name in NAMES:
            self.assertNotIn(name, m["core"]["components"])
            for other in ("charts", "diagrams", "map", "text"):
                self.assertNotIn(name, m["packs"][other]["components"], "%s leaked into the %s pack" % (name, other))

    def test_the_pack_file_is_shipped_small_and_matches_its_recorded_hash(self):
        info = bundle.manifest()["packs"]["infra"]
        self.assertTrue((bundle.ASSETS / info["file"]).is_file())
        self.assertLess(info["gz"], 16 * 1024)
        self.assertLess(info["gz"], bundle.manifest()["packs"]["charts"]["gz"])
        self.assertEqual([p for p in bundle.verify() if "infra" in p], [])

    def test_the_shipped_pack_has_no_network_code_and_registers_itself(self):
        info = bundle.manifest()["packs"]["infra"]
        text = gzip.decompress((bundle.ASSETS / info["file"]).read_bytes()).decode("utf-8")
        self.assertIsNone(re.search(r"fetch\(|XMLHttpRequest|sendBeacon|WebSocket\(|EventSource\(|posthog|cloudfront", text))
        self.assertIn("window.__HM.register(", text)
        self.assertIn('"infra"', text)

    def test_the_theme_comes_from_css_variables_with_fallbacks(self):
        info = bundle.manifest()["packs"]["infra"]
        text = gzip.decompress((bundle.ASSETS / info["file"]).read_bytes()).decode("utf-8")
        for var in ("--foreground", "--muted-foreground", "--accent", "--border", "--card"):
            self.assertIn("var(" + var + ",", text)

    def test_the_sources_define_exactly_the_four_components_and_register_the_pack(self):
        text = (ROOT / "build" / "src" / "packs" / "infra.jsx").read_text(encoding="utf-8")
        defined = re.findall(r'defineComponent\(\s*\{\s*name:\s*"(\w+)"', text)
        self.assertEqual(defined, NAMES)
        reg = re.search(r'export const pack = \{\s*name:\s*"([^"]+)"\s*,\s*components:\s*\[([^\]]*)\]', text)
        self.assertIsNotNone(reg, "no `export const pack = { name, components: [...] }`")
        self.assertEqual(reg.group(1), "infra")
        self.assertEqual([x.strip() for x in reg.group(2).split(",") if x.strip()], NAMES)
        self.assertIn('"./infra.jsx"', (ROOT / "build" / "src" / "packs" / "index.js").read_text(encoding="utf-8"))

    def test_the_sources_do_not_reach_for_the_user_pack_globals(self):
        for rel in ("components/infra.jsx", "packs/infra.jsx"):
            with self.subTest(source=rel):
                text = (ROOT / "build" / "src" / rel).read_text(encoding="utf-8")
                self.assertNotIn("window.__HM", text, "a built-in imports react and zod normally")


class Reference(unittest.TestCase):
    def test_every_signature_matches_what_the_user_pack_header_said(self):
        for name, sig in SIGNATURES.items():
            with self.subTest(component=name):
                self.assertEqual(reference_line(name).split(" \u2014 ")[0], sig)

    def test_every_line_has_a_description_that_keeps_the_facts_the_model_needs(self):
        for name, facts in DESCRIPTION_FACTS.items():
            with self.subTest(component=name):
                desc = reference_line(name).split(" \u2014 ", 1)[1]
                for fact in facts:
                    self.assertIn(fact, desc)

    def test_the_four_come_after_every_older_component_so_the_existing_order_is_unchanged(self):
        order = re.findall(r"^([A-Z]\w*)\(", bundle.reference_text(), re.M)
        self.assertEqual(order[-4:], NAMES)
        self.assertEqual(order[:-4], [n for n in order if not n.startswith("Infra")])
        self.assertEqual(order.index("RadarChart"), len(order) - 5)

    def test_argument_order_and_optionality_follow_the_documented_signature(self):
        want = {n: split_args(s[s.index("(") + 1:s.rindex(")")]) for n, s in SIGNATURES.items()}
        for name in NAMES:
            with self.subTest(component=name):
                self.assertEqual([(a, o) for a, o, _t in signature_args(name)], [(a, o) for a, o, _t in want[name]])

    def test_all_eight_kinds_and_four_statuses_are_documented(self):
        def values(comp, arg):
            return re.findall(r'"([^"]+)"', dict((a, t) for a, _o, t in signature_args(comp))[arg])

        self.assertEqual(sorted(values("InfraNode", "kind")), sorted("client gateway service gpu database storage queue cloud".split()))
        self.assertEqual(sorted(values("InfraNode", "status")), sorted("up degraded down unknown".split()))
        self.assertEqual(sorted(values("InfraZone", "tone")), sorted("neutral info good warn bad".split()))
        self.assertEqual(sorted(values("InfraLink", "style")), ["dashed", "solid"])
        self.assertEqual(sorted(values("InfraMap", "direction")), ["LR", "TB"])

    def test_a_user_pack_may_not_take_one_of_these_names(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "mine.js"
            f.write_text('/* hermes-openui-pack\n{"api": 1, "name": "mine", "components": {"InfraMap": "InfraMap(a: string) \\u2014 mine."}}\n*/\n(function () {})();\n', encoding="utf-8")
            found, problems = packs.load([str(f)], bundle.component_names())
        self.assertEqual(found, [])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("shadows a built-in component", problems[0])


class Fixtures(unittest.TestCase):
    def setUp(self):
        self.known = bundle.component_names()

    def test_the_fixture_files_exist(self):
        for name in GOOD + [BAD]:
            self.assertTrue(fixture(name).is_file(), name)

    def test_every_good_fixture_lints_clean(self):
        for name in GOOD:
            with self.subTest(fixture=name):
                self.assertEqual(lint.check(source(name), self.known), [])

    def test_the_bad_fixture_is_lint_clean_because_its_mistake_is_semantic(self):
        self.assertEqual(lint.check(source(BAD), self.known), [])

    def test_fixtures_call_the_pack_so_it_is_embedded_and_the_page_fits(self):
        for name in GOOD + [BAD]:
            with self.subTest(fixture=name):
                self.assertEqual(page.select_packs(source(name)), ["infra"])
                html, embedded = page.build_page(source(name))
                self.assertEqual(embedded, ["infra"])
                self.assertIn('data-oui="infra"', html)
                self.assertNotIn('data-oui="diagrams"', html)
                self.assertNotIn("custom:", html)
                self.assertLess(len(html.encode("utf-8")), page.SAFE_BUDGET)

    def test_fixtures_use_only_generic_names(self):
        for name in GOOD + [BAD]:
            text = fixture(name).read_text(encoding="utf-8")
            with self.subTest(fixture=name):
                self.assertIsNone(re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", text), "an IP address")
                self.assertIsNone(re.search(r"https?://|\.local\b|\.lan\b|\.internal\b|@|password|token|secret|sk-", text, re.I))
                # public fixtures describe an ordinary web platform, not the owner's own stack
                self.assertIsNone(re.search(r"litellm|vllm|dgx|spark-?\d|qwen|llama|ollama|homelab|tailnet|onlygens", text, re.I), "a real name")

    def test_the_main_fixture_shows_the_four_zones_and_the_requested_nodes(self):
        text = source("map.oui")
        self.assertEqual(text.count("InfraZone("), 4)
        for needle in ("Browser", "Mobile app", "Load balancer", "web-1", "web-2", "worker", "Postgres", "Cache", "Object storage"):
            self.assertIn(needle, text)
        links = re.findall(r"\bInfraLink\(", text)
        self.assertGreaterEqual(len(links), 8)
        for label in ('"HTTPS"', '"route"', '"SQL"', '"backup"'):
            self.assertIn(label, text)

    def test_the_minimal_fixture_is_two_zones_and_three_nodes(self):
        text = source("minimal.oui")
        self.assertEqual((text.count("InfraZone("), text.count("InfraNode(")), (2, 3))

    def test_the_tb_fixture_asks_for_top_to_bottom(self):
        self.assertIn('"TB"', source("tb.oui"))


class PageBuilding(unittest.TestCase):
    DAG = 'root = Stack([d])\nd = Dag([DagNode("a", "A")], [])'

    def test_a_page_without_infra_components_does_not_embed_the_pack(self):
        for src in (self.DAG, 'root = Stack([t])\nt = Text("hi", "body")', 'root = Stack([e])\ne = Erd([Entity("a", ["id uuid PK"])], [])'):
            with self.subTest(source=src.splitlines()[-1]):
                html, embedded = page.build_page(src)
                self.assertNotIn("infra", embedded)
                self.assertNotIn('data-oui="infra"', html)

    def test_infra_names_inside_text_do_not_pull_the_pack_in(self):
        src = 'root = Stack([t])\nt = Text("Use InfraMap( and InfraNode( for servers", "body")'
        self.assertEqual(page.select_packs(src), [])

    def test_each_component_alone_pulls_the_pack_in(self):
        for name in NAMES:
            with self.subTest(component=name):
                self.assertEqual(page.select_packs("root = Stack([x])\nx = %s()" % name), ["infra"])

    def test_a_widget_may_mix_infra_with_another_pack(self):
        src = source("minimal.oui").replace("root = Stack([map])", "root = Stack([map, d])") + 'd = Dag([DagNode("a", "A")], [])\n'
        self.assertEqual(page.select_packs(src), ["diagrams", "infra"])
        html, embedded = page.build_page(src)
        self.assertEqual(embedded, ["diagrams", "infra"])
        self.assertLess(len(html.encode("utf-8")), page.SAFE_BUDGET)

    def test_the_everything_flag_includes_infra(self):
        self.assertIn("infra", page.select_packs("root = Stack([])", everything=True))


@unittest.skipUnless(node_available(), "needs Node and assets/validate.cjs")
class Validator(unittest.TestCase):
    """The shipped validator, run with no --pack: the cross-reference checks are built in."""

    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.out = {}
        cases = {
            "dup": build_map([("A", [("x", "X"), ("y", "Y")]), ("B", [("x", "X again")])], [("x", "y")]),
            "dup_twice": build_map([("A", [("x", "X"), ("x", "X2"), ("x", "X3")])], []),
            "empty_zone": 'root = Stack([m])\nm = InfraMap([z0, z1], [])\nz0 = InfraZone("Lonely", [])\nz1 = InfraZone("Fine", [n])\nn = InfraNode("a", "A")\n',
            "missing": build_map([("A", [("x", "X")]), ("B", [("y", "Y")])], [("x", "nope")]),
            "missing_from": build_map([("A", [("x", "X")])], [("ghost", "x")]),
            "label_not_id": build_map([("A", [("pg", "Postgres")]), ("B", [("q", "Q")])], [("Postgres", "q")]),
            "label_other_case": build_map([("A", [("pg", "Postgres")]), ("B", [("q", "Q")])], [("q", "postgres")]),
            "self": build_map([("A", [("x", "X"), ("y", "Y")])], [("x", "x")]),
            "no_zones": "root = Stack([m])\nm = InfraMap([], [])\n",
            "fine": build_map([("A", [("x", "X")]), ("B", [("y", "Y")])], [("x", "y")]),
            "proto_ids": build_map([("A", [("constructor", "C"), ("y", "Y")]), ("B", [("__proto__", "P")])], [("constructor", "y"), ("y", "__proto__")]),
            "proto_label": build_map([("A", [("a", "constructor")])], [("toString", "a")]),
            "node_alone": 'root = Stack([n])\nn = InfraNode("x", "X")\n',
            "link_alone": 'root = Stack([l])\nl = InfraLink("x", "y")\n',
        }
        for name, text in cases.items():
            cls.out[name] = run_validator(text, cls.td.name)
        cls.out["bad"] = run_validator(source(BAD), cls.td.name)
        for name in GOOD:
            cls.out[name] = run_validator(source(name), cls.td.name)

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def problems(self, key):
        code, out = self.out[key]
        self.assertEqual(code, 1, out)
        self.assertIn("OpenUI validation FAILED", out)
        return [ln[2:] for ln in out.splitlines() if ln.startswith("- ")]

    def test_the_good_fixtures_pass_with_no_pack_linked(self):
        for name in GOOD:
            with self.subTest(fixture=name):
                code, out = self.out[name]
                self.assertEqual(code, 0, out)
                self.assertIn("OpenUI validation OK", out)

    def test_the_bad_fixture_is_rejected_with_the_hint_that_names_the_right_id(self):
        problems = self.problems("bad")
        self.assertEqual(len(problems), 1, problems)
        self.assertEqual(
            problems[0],
            "InfraMap link uses unknown node id `postgres` in `to` (InfraLink takes InfraNode id strings, not variable names or labels; known ids: web, api, pg). `postgres` is a label; the id is `pg`.",
        )

    def test_the_bad_fixture_names_the_unknown_id_and_lists_the_known_ones(self):
        problem = self.problems("bad")[0]
        m = re.search(r"link .*unknown node id `([^`]+)`", problem)
        self.assertIsNotNone(m, problem)
        self.assertIn(m.group(1), source(BAD))
        self.assertIn("known", problem)
        for known in re.findall(r'InfraNode\("([^"]+)"', source(BAD)):
            self.assertIn(known, problem)

    def test_duplicate_ids_across_zones_are_reported_once(self):
        self.assertEqual(
            self.problems("dup"),
            ["InfraMap has duplicate node ids: x (every InfraNode id must be unique across all zones)."],
        )

    def test_an_id_used_three_times_is_listed_once(self):
        self.assertEqual(
            self.problems("dup_twice"),
            ["InfraMap has duplicate node ids: x (every InfraNode id must be unique across all zones)."],
        )

    def test_a_zone_without_nodes_is_reported(self):
        self.assertEqual(
            self.problems("empty_zone"),
            ["InfraZone `Lonely` has no nodes (give it at least one InfraNode, or remove the zone)."],
        )

    def test_a_link_to_a_missing_id_lists_the_known_ids_and_has_no_label_hint(self):
        self.assertEqual(
            self.problems("missing"),
            ["InfraMap link uses unknown node id `nope` in `to` (InfraLink takes InfraNode id strings, not variable names or labels; known ids: x, y)."],
        )

    def test_a_link_from_a_missing_id_says_from(self):
        self.assertEqual(
            self.problems("missing_from"),
            ["InfraMap link uses unknown node id `ghost` in `from` (InfraLink takes InfraNode id strings, not variable names or labels; known ids: x)."],
        )

    def test_a_link_that_names_a_label_instead_of_the_id_says_so(self):
        problems = self.problems("label_not_id")
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(problems[0].endswith("`Postgres` is a label; the id is `pg`."), problems[0])

    def test_the_label_hint_ignores_case_and_works_for_the_from_end_too(self):
        problems = self.problems("label_other_case")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("in `to`", problems[0])
        self.assertTrue(problems[0].endswith("`postgres` is a label; the id is `pg`."), problems[0])

    def test_a_link_from_a_node_to_itself_is_reported(self):
        self.assertEqual(self.problems("self"), ["InfraMap link from `x` to itself cannot be drawn."])

    def test_a_map_with_no_zones_is_reported(self):
        self.assertEqual(self.problems("no_zones"), ["InfraMap needs at least one InfraZone in `zones`."])

    def test_a_valid_map_and_the_leaf_components_pass(self):
        for key in ("fine", "node_alone", "link_alone"):
            with self.subTest(case=key):
                code, out = self.out[key]
                self.assertEqual(code, 0, out)

    def test_node_ids_and_labels_that_look_like_object_properties_are_handled(self):
        for key in ("proto_ids", "proto_label"):
            with self.subTest(case=key):
                code, out = self.out[key]
                if key == "proto_ids":
                    self.assertEqual(code, 0, out)
                else:
                    # `toString` is no id of this map: reported, and the label `constructor` must not crash the hint lookup
                    self.assertEqual(code, 1, out)
                    self.assertEqual(len(self.problems(key)), 1)

    def test_every_value_the_reference_lists_is_accepted_and_a_made_up_one_is_not(self):
        kinds, statuses = "client gateway service gpu database storage queue cloud".split(), "up degraded down unknown".split()
        nodes = ['n%d = InfraNode("id%d", "L%d", "%s", "%s", "d")' % (i, i, i, kinds[i], statuses[i % 4]) for i in range(8)]
        zones = ['z%d = InfraZone("Z%d", [n%d], "%s")' % (i, i, i, t) for i, t in enumerate(["neutral", "info", "good", "warn", "bad"])]
        zones += ['z5 = InfraZone("Z5", [n5, n6, n7])', 'z6 = InfraZone("Z6", [n8])']
        nodes.append('n8 = InfraNode("id8", "L8")')
        links = ['l0 = InfraLink("id0", "id1", "x", "solid")', 'l1 = InfraLink("id1", "id2", "y", "dashed")']
        ok = 'root = Stack([m1, m2])\nm1 = InfraMap([z0, z1, z2, z3, z4, z5], [l0, l1], "t", "LR")\nm2 = InfraMap([z6], [], "t", "TB")\n' + "\n".join(nodes + zones + links) + "\n"
        code, out = run_validator(ok, self.td.name)
        self.assertEqual(code, 0, out)
        for label, bad in (
            ("kind", ok.replace('"gpu"', '"gpuu"')),
            ("status", ok.replace('"degraded"', '"degradedd"')),
            ("tone", ok.replace('"warn")', '"orange")')),
            ("style", ok.replace('"dashed"', '"dotted"')),
            ("direction", ok.replace('"TB"', '"RL"')),
        ):
            with self.subTest(argument=label):
                code, out = run_validator(bad, self.td.name)
                self.assertEqual(code, 1, out)
                self.assertIn("OpenUI validation FAILED", out)

    def test_a_missing_required_argument_is_a_schema_error_not_a_crash(self):
        code, out = run_validator('root = Stack([n])\nn = InfraNode("only-id")\n', self.td.name)
        self.assertEqual(code, 1, out)
        self.assertIn("InfraNode", out)


# ---- the renderer and its layout engine, run for real under Node ----------------------------------------------------------

BUILD = ROOT / "build"
NEEDED = ("react", "react-dom", "zod", "esbuild", "@openuidev/react-lang", "@openuidev/lang-core")

HARNESS = r"""
const fs = require("fs"), path = require("path");
const cfg = JSON.parse(process.env.INFRA_CFG);
const req = require("module").createRequire(path.join(cfg.build, "package.json"));
const esbuild = req("esbuild");
const entry = [
  'import React from "react";',
  'import { renderToStaticMarkup } from "react-dom/server";',
  'import * as lang from "@openuidev/react-lang";',
  'import { createParser } from "@openuidev/lang-core";',
  'import * as zod from "zod/v4";',
  'import { pack } from "./packs/infra.jsx";',
  'import { layoutInfra } from "./components/infra.jsx";',
  'export { React, renderToStaticMarkup, lang, createParser, zod, pack, layoutInfra };',
].join("\n");
const built = esbuild.buildSync({
  stdin: { contents: entry, resolveDir: path.join(cfg.build, "src"), loader: "js", sourcefile: "infra-harness.js" },
  bundle: true, platform: "node", format: "cjs", jsx: "automatic", write: false, logLevel: "error",
  define: { "process.env.NODE_ENV": '"production"' },
});
const mod = { exports: {} };
new Function("module", "exports", "require", built.outputFiles[0].text)(mod, mod.exports, require);
const { React, renderToStaticMarkup, lang, createParser, zod, pack, layoutInfra } = mod.exports;

const Stack = lang.defineComponent({ name: "Stack", description: "stack", props: zod.object({ children: zod.array(zod.any()) }), component: () => null });
const library = lang.createLibrary({ root: "Stack", components: [Stack].concat(pack.components) });
const parser = createParser(library.toJSONSchema(), library.root);
const out = { pack: { name: pack.name, components: pack.components.map((c) => c.name) }, examples: {}, schema: {}, scenarios: {} };

for (const c of pack.components) {
  const shape = c.props.shape || {};
  out.schema[c.name] = Object.keys(shape).map((k) => ({ key: k, optional: shape[k].safeParse(undefined).success,
    accepts: (cfg.values[c.name + "." + k] || []).map((v) => shape[k].safeParse(v).success), rejectsBogus: !shape[k].safeParse("__bogus__").success }));
}

const walk = (n, fn) => { if (n && typeof n === "object") { if (n.typeName) fn(n); for (const v of Object.values(n.props || {})) (Array.isArray(v) ? v : [v]).forEach((c) => walk(c, fn)); } };
for (const [name, src] of Object.entries(cfg.sources)) {
  const { root, meta } = parser.parse(src);
  const ex = { parsed: !!root, unresolved: meta.unresolved, orphaned: meta.orphaned, errors: (meta.errors || []).map((e) => e.message || String(e)), html: "", layouts: [] };
  walk(root, (n) => {
    if (n.typeName !== "InfraMap") return;
    const comp = pack.components.find((c) => c.name === "InfraMap");
    ex.html = renderToStaticMarkup(React.createElement(comp.component, { props: n.props }));
    const p = n.props;
    const zones = (p.zones || []).map((zn) => ({ name: zn.props.name, tone: zn.props.tone, nodes: (zn.props.nodes || []).map((x) => x.props) }));
    ex.layouts.push(layoutInfra(zones, (p.links || []).map((l) => l.props), p.direction || "LR"));
  });
  out.examples[name] = ex;
}
for (const [name, sc] of Object.entries(cfg.scenarios)) {
  for (const dir of ["LR", "TB"]) {
    try { out.scenarios[name + ":" + dir] = layoutInfra(sc.zones, sc.links, dir); }
    catch (e) { out.scenarios[name + ":" + dir] = { error: String((e && e.stack) || e) }; }
  }
}
process.stdout.write(JSON.stringify(out));
"""


def node_missing_reason():
    if not shutil.which("node"):
        return "node is not on PATH"
    for mod in NEEDED:
        if not (BUILD / "node_modules" / mod / "package.json").is_file():
            return "build/node_modules/%s is missing (run `npm ci` in build/)" % mod
    return ""


def run_harness(sources, values, scenarios):
    cfg = {"build": str(BUILD), "sources": sources, "values": values, "scenarios": scenarios}
    env = dict(os.environ, INFRA_CFG=json.dumps(cfg), DO_NOT_TRACK="1", OPENUI_TELEMETRY_DISABLED="1")
    r = subprocess.run(["node", "-"], input=HARNESS, capture_output=True, text=True, env=env, cwd=str(BUILD), timeout=120)
    if r.returncode != 0:
        raise AssertionError("node harness failed:\n" + (r.stderr or r.stdout)[-2000:])
    return json.loads(r.stdout)


def scenarios():
    """Layouts the fixtures do not cover: every kind of route at once, and the degenerate inputs."""

    def n(i, **kw):
        d = {"id": i, "label": "Node " + i}
        d.update(kw)
        return d

    def lk(a, b, label=None, style=None):
        return {"from": a, "to": b, "label": label, "style": style}

    zones = [
        {"name": "Edge", "nodes": [n("a1", status="up", kind="client"), n("a2", detail="two lines", kind="cloud"), n("a3", kind="queue")]},
        {"name": "Core", "nodes": [n("b1", status="degraded", kind="gateway"), n("b2", kind="service", detail="x" * 40)]},
        {"name": "Compute with a long name", "tone": "good", "nodes": [n("c1", kind="gpu", status="down"), n("c2", kind="gpu"), n("c3", kind="gpu", status="unknown")]},
        {"name": "Data", "tone": "bad", "nodes": [n("d1", kind="database"), n("d2", kind="storage", status="up")]},
    ]
    links = [
        lk("a1", "b1", "adjacent"), lk("a2", "b2", "adjacent"), lk("b1", "a3", "back"), lk("b2", "c1"), lk("c2", "b1", "back two", "dashed"),
        lk("a1", "c3", "far forward"), lk("a3", "d2", "far to the end"), lk("d1", "a2", "far back"), lk("c1", "d2", "a longer label here"),
        lk("a1", "a2", "stack"), lk("a3", "a2"), lk("a1", "a3", "bracket"), lk("c1", "c3", "bracket"), lk("d2", "d1", "up"),
        lk("b1", "b2"), lk("b2", "b1", "both ways"), lk("a1", "a1", "self"), lk("a1", "ghost", "unknown"),
    ]
    return {
        "everything": {"zones": zones, "links": links},
        "no_zones": {"zones": [], "links": []},
        "empty_zone": {"zones": [{"name": "Empty", "nodes": []}, {"name": "One", "nodes": [n("x")]}], "links": [lk("x", "x")]},
        "no_links": {"zones": zones, "links": []},
        "single": {"zones": [{"name": "Only", "nodes": [n("solo")]}], "links": []},
        "duplicate_ids": {"zones": [{"name": "A", "nodes": [n("same"), n("same")]}], "links": [lk("same", "same")]},
        "proto_ids": {"zones": [{"name": "A", "nodes": [n("constructor"), n("__proto__")]}], "links": [lk("constructor", "__proto__", "p")]},
        "many_far": {"zones": [{"name": "Z%d" % i, "nodes": [n("z%dn%d" % (i, j)) for j in range(2)]} for i in range(6)],
                     "links": [lk("z0n%d" % (i % 2), "z%dn%d" % (2 + i % 4, (i + 1) % 2), "hop %d" % i) for i in range(8)] + [lk("z5n1", "z0n0", "return")]},
    }


def overlap(a, b, m=0.5):
    return a["x"] < b["x"] + b["w"] - m and b["x"] < a["x"] + a["w"] - m and a["y"] < b["y"] + b["h"] - m and b["y"] < a["y"] + a["h"] - m


@unittest.skipIf(node_missing_reason(), node_missing_reason() or "")
class RunsUnderNode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        values = {}
        for name in NAMES:
            for arg, _opt, typ in signature_args(name):
                q = re.findall(r'"([^"]+)"', typ)
                if q:
                    values["%s.%s" % (name, arg)] = q
        cls.values = values
        cls.r = run_harness({n: source(n) for n in GOOD + [BAD]}, values, scenarios())

    # registration and schema -------------------------------------------------------------------------------------
    def test_it_registers_under_the_manifest_name(self):
        self.assertEqual(self.r["pack"]["name"], "infra")
        self.assertEqual(self.r["pack"]["components"], NAMES)

    def test_argument_order_and_optionality_of_the_zod_schemas_match_the_reference(self):
        for cname in NAMES:
            with self.subTest(component=cname):
                want = signature_args(cname)
                have = self.r["schema"][cname]
                self.assertEqual([k["key"] for k in have], [a[0] for a in want])
                self.assertEqual([k["optional"] for k in have], [a[1] for a in want])

    def test_every_value_the_reference_lists_is_accepted_and_anything_else_is_rejected(self):
        listed = 0
        for cname, keys in self.r["schema"].items():
            for k in keys:
                vals = self.values.get("%s.%s" % (cname, k["key"]))
                if vals:
                    listed += 1
                    self.assertTrue(all(k["accepts"]), "%s.%s rejects a value the reference lists" % (cname, k["key"]))
                    self.assertTrue(k["rejectsBogus"], "%s.%s accepts a made-up value" % (cname, k["key"]))
        self.assertGreaterEqual(listed, 5)  # kind, status, tone, style, direction

    # the real parser agrees with the fixtures ---------------------------------------------------------------------
    def test_the_real_parser_accepts_every_fixture(self):
        for name in GOOD + [BAD]:
            with self.subTest(fixture=name):
                ex = self.r["examples"][name]
                self.assertTrue(ex["parsed"])
                self.assertEqual((ex["unresolved"], ex["orphaned"], ex["errors"]), ([], [], []))

    # rendering -----------------------------------------------------------------------------------------------------
    def test_the_svg_is_well_formed_and_has_no_broken_numbers(self):
        for name in GOOD + [BAD]:
            html = self.r["examples"][name]["html"]
            with self.subTest(fixture=name):
                self.assertIn("<svg", html)
                self.assertIn("viewBox=", html)
                for bad in ("NaN", "undefined", "Infinity", "[object"):
                    self.assertNotIn(bad, html)

    def test_every_label_and_detail_in_the_source_is_drawn(self):
        for name in GOOD:
            src = source(name)
            html = self.r["examples"][name]["html"]
            with self.subTest(fixture=name):
                for m in re.finditer(r'InfraNode\("[^"]+", "([^"]+)"', src):
                    self.assertIn(m.group(1), html)
                for m in re.finditer(r'InfraZone\("([^"]+)"', src):
                    self.assertIn(m.group(1), html)
                for m in re.finditer(r'InfraLink\("[^"]+", "[^"]+", "([^"]+)"', src):
                    self.assertIn(m.group(1), html)

    def test_one_arrow_is_drawn_per_link(self):
        for name in GOOD:
            n_links = len(re.findall(r"\bInfraLink\(", source(name)))
            with self.subTest(fixture=name):
                self.assertEqual(self.r["examples"][name]["html"].count("marker-end="), n_links)

    def test_the_legend_names_each_status_in_use_and_only_those(self):
        html = self.r["examples"]["map.oui"]["html"]
        for status in ("up", "degraded", "unknown"):
            self.assertRegex(html, r">%s</span>" % status)
        self.assertNotRegex(html, r">down</span>")  # no node in the sample is down
        self.assertNotIn(">unknown</span>", self.r["examples"]["minimal.oui"]["html"])  # none of its nodes is unknown

    def test_the_bad_fixture_still_draws_what_it_can_and_warns(self):
        html = self.r["examples"][BAD]["html"]
        self.assertIn("<svg", html)
        self.assertIn("\u26a0", html)
        self.assertIn("unknown node id", html)

    def test_colours_come_from_css_variables_not_hard_coded_values(self):
        html = self.r["examples"]["map.oui"]["html"]
        self.assertIsNone(re.search(r'(?:fill|stroke)="#(?!3fb950|d29922|f85149)[0-9a-fA-F]{3,6}"', html))
        self.assertIn("var(--foreground", html)

    # geometry ------------------------------------------------------------------------------------------------------
    def layout(self, name):
        return self.r["examples"][name]["layouts"][0]

    def test_no_link_is_drawn_across_a_node_box(self):
        for name in GOOD:
            lay = self.layout(name)
            with self.subTest(fixture=name):
                for link in lay["links"]:
                    for (x, y) in link["points"]:
                        for node in lay["nodes"]:
                            inside = node["x"] + 0.5 < x < node["x"] + node["w"] - 0.5 and node["y"] + 0.5 < y < node["y"] + node["h"] - 0.5
                            self.assertFalse(inside, "link %s->%s passes through node %s" % (link["from"], link["to"], node["id"]))

    def test_every_arrow_starts_and_ends_on_the_edge_of_its_own_nodes(self):
        for name in GOOD:
            lay = self.layout(name)
            nodes = {n["id"]: n for n in lay["nodes"]}
            with self.subTest(fixture=name):
                for link in lay["links"]:
                    for pt, nid in ((link["points"][0], link["from"]), (link["points"][-1], link["to"])):
                        n = nodes[nid]
                        on_x = abs(pt[0] - n["x"]) < 0.6 or abs(pt[0] - (n["x"] + n["w"])) < 0.6
                        on_y = abs(pt[1] - n["y"]) < 0.6 or abs(pt[1] - (n["y"] + n["h"])) < 0.6
                        within_x = n["x"] - 0.6 <= pt[0] <= n["x"] + n["w"] + 0.6
                        within_y = n["y"] - 0.6 <= pt[1] <= n["y"] + n["h"] + 0.6
                        self.assertTrue(within_x and within_y and (on_x or on_y), "%s end of %s->%s is off node %s: %r" % (name, link["from"], link["to"], nid, pt))

    def test_link_label_pills_do_not_cover_nodes_or_each_other(self):
        for name in GOOD:
            lay = self.layout(name)
            pills = list(lay["pills"])
            with self.subTest(fixture=name):
                for i, p in enumerate(pills):
                    for n in lay["nodes"]:
                        self.assertFalse(overlap(p, n), "pill %r covers node %s" % (p["text"], n["id"]))
                    for q in pills[i + 1:]:
                        self.assertFalse(overlap(p, q), "pills %r and %r overlap" % (p["text"], q["text"]))

    def test_everything_drawn_sits_inside_the_view_box(self):
        for name in GOOD:
            lay = self.layout(name)
            vb = lay["viewBox"]
            with self.subTest(fixture=name):
                for it in lay["nodes"] + lay["zones"] + lay["pills"]:
                    self.assertGreaterEqual(it["x"], vb[0] - 0.01)
                    self.assertGreaterEqual(it["y"], vb[1] - 0.01)
                    self.assertLessEqual(it["x"] + it["w"], vb[0] + vb[2] + 0.01)
                    self.assertLessEqual(it["y"] + it["h"], vb[1] + vb[3] + 0.01)

    def test_the_main_fixture_is_not_so_wide_that_text_becomes_unreadable_in_the_640_column(self):
        vb = self.layout("map.oui")["viewBox"]
        self.assertLess(vb[2], 640 / 0.78, "scaled below 78%% the labels get too small (width %d)" % vb[2])

    def test_lr_puts_zones_in_columns_and_tb_in_rows_in_the_order_given(self):
        lr = self.layout("map.oui")["zones"]
        self.assertEqual([z["name"] for z in lr], ["Clients", "Edge", "Application", "Data"])
        self.assertTrue(all(a["x"] + a["w"] <= b["x"] for a, b in zip(lr, lr[1:])))
        tb = self.layout("tb.oui")["zones"]
        self.assertTrue(len(tb) >= 3 and all(a["y"] + a["h"] <= b["y"] for a, b in zip(tb, tb[1:])))
        self.assertTrue(all(z["x"] == tb[0]["x"] and z["w"] == tb[0]["w"] for z in tb))

    def test_nodes_sit_inside_their_zone(self):
        for name in GOOD:
            lay = self.layout(name)
            with self.subTest(fixture=name):
                zones = {z["name"]: z for z in lay["zones"]}
                for n in lay["nodes"]:
                    z = zones[n["zone"]]
                    self.assertTrue(z["x"] < n["x"] and n["x"] + n["w"] < z["x"] + z["w"] and z["y"] < n["y"] and n["y"] + n["h"] < z["y"] + z["h"], n["id"])

    # layouts the fixtures do not cover --------------------------------------------------------------------------------
    def scenario(self, name, direction):
        lay = self.r["scenarios"]["%s:%s" % (name, direction)]
        self.assertNotIn("error", lay, lay.get("error"))
        return lay

    def test_no_scenario_crashes_in_either_direction(self):
        for key in self.r["scenarios"]:
            with self.subTest(scenario=key):
                lay = self.r["scenarios"][key]
                self.assertNotIn("error", lay, lay.get("error"))
                self.assertEqual(len(lay["viewBox"]), 4)
                for v in lay["viewBox"]:
                    self.assertTrue(isinstance(v, (int, float)) and v == v and abs(v) < 1e6, lay["viewBox"])
                self.assertGreater(lay["viewBox"][2], 0)
                self.assertGreater(lay["viewBox"][3], 0)

    def test_every_route_kind_keeps_off_the_nodes_in_both_directions(self):
        for direction in ("LR", "TB"):
            for name in ("everything", "many_far", "no_links"):
                lay = self.scenario(name, direction)
                with self.subTest(scenario=name, direction=direction):
                    for link in lay["links"]:
                        for (x, y) in link["points"]:
                            for node in lay["nodes"]:
                                inside = node["x"] + 0.5 < x < node["x"] + node["w"] - 0.5 and node["y"] + 0.5 < y < node["y"] + node["h"] - 0.5
                                self.assertFalse(inside, "%s->%s (%s) crosses node %s" % (link["from"], link["to"], link["type"], node["id"]))
                    for p in lay["pills"]:
                        for node in lay["nodes"]:
                            self.assertFalse(overlap(p, node), "pill %r covers node %s" % (p["text"], node["id"]))

    def test_every_valid_link_is_drawn_and_bad_ones_are_warned_about_instead(self):
        for direction in ("LR", "TB"):
            lay = self.scenario("everything", direction)
            self.assertEqual(len(lay["links"]), 16)  # 18 minus the self-link and the one to an id that does not exist
            self.assertTrue(any("ghost" in w for w in lay["warns"]), lay["warns"])
            self.assertTrue(any("itself" in w for w in lay["warns"]), lay["warns"])
            kinds = sorted(set(l["type"] for l in lay["links"]))
            self.assertEqual(kinds, ["adj", "bracket", "far", "stack"])

    def test_far_links_go_around_the_zones_in_between(self):
        lay = self.scenario("everything", "LR")
        zones = {z["name"]: z for z in lay["zones"]}
        top = min(z["y"] for z in lay["zones"])
        bottom = max(z["y"] + z["h"] for z in lay["zones"])
        for link in lay["links"]:
            if link["type"] != "far":
                continue
            ys = [p[1] for p in link["points"]]
            self.assertTrue(min(ys) < top or max(ys) > bottom, "far link %s->%s never leaves the zone band" % (link["from"], link["to"]))
            inner = [p for p in link["points"] if zones["Core"]["x"] < p[0] < zones["Core"]["x"] + zones["Core"]["w"] and zones["Core"]["y"] < p[1] < zones["Core"]["y"] + zones["Core"]["h"]]
            if link["from"] in ("a1", "a3", "d1") and link["to"] in ("c3", "d2", "a2"):
                self.assertEqual(inner, [], "%s->%s runs through the Core zone" % (link["from"], link["to"]))

    def test_degenerate_input_is_handled(self):
        for direction in ("LR", "TB"):
            self.assertEqual(self.scenario("no_zones", direction)["nodes"], [])
            self.assertEqual(len(self.scenario("empty_zone", direction)["zones"]), 2)
            self.assertEqual(len(self.scenario("single", direction)["nodes"]), 1)
            dup = self.scenario("duplicate_ids", direction)
            self.assertTrue(any("duplicate" in w for w in dup["warns"]), dup["warns"])
            proto = self.scenario("proto_ids", direction)
            self.assertEqual(len(proto["links"]), 1)
            self.assertEqual(proto["warns"], [])

    def test_boxes_are_wide_enough_for_their_text(self):
        lay = self.scenario("everything", "LR")
        for n in lay["nodes"]:
            self.assertGreaterEqual(n["w"], 100)
        widest_label = max(lay["nodes"], key=lambda n: len(n["detail"] or ""))
        self.assertGreaterEqual(widest_label["w"], 34 + 6 * len(widest_label["detail"]))  # detail is clipped to 26 chars
        for name in ("map.oui", "tb.oui"):
            for n in self.layout(name)["nodes"]:
                self.assertGreaterEqual(n["w"], 34 + 6.2 * max(len(n["label"]), len(n["detail"] or "")) - 2, n["id"])


# ---- a real page in headless Chrome ---------------------------------------------------------------------------------

def chrome_missing_reason():
    spec = importlib.util.spec_from_file_location("shoot_infra", ROOT / "tools" / "shoot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        mod.find_chrome(None)
    except SystemExit as e:
        return str(e), mod
    return "", mod


_CHROME_REASON, _SHOOT = chrome_missing_reason()


@unittest.skipIf(_CHROME_REASON, _CHROME_REASON or "")
class RendersInChrome(unittest.TestCase):
    """tools/shoot.py builds the real widget page (no --pack: the components are built in), loads it in headless Chrome and waits for it to draw."""

    def shoot(self, name, theme):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / ("%s-%s.png" % (Path(name).stem, theme))
            summary = _SHOOT.shoot(fixture(name), out, theme=theme)
            self.assertTrue(out.is_file())
            w, h = _SHOOT.png_size(out)
            return summary, out.stat().st_size, (w, h)

    def test_the_minimal_fixture_renders_in_both_themes_with_only_the_infra_pack(self):
        for theme in ("dark", "light"):
            with self.subTest(theme=theme):
                summary, size, (w, h) = self.shoot("minimal.oui", theme)
                self.assertIn("packs: infra)", summary)
                self.assertGreater(w, 600)
                self.assertGreater(h, 200)
                self.assertGreater(size, 10 * 1024, "the screenshot is nearly empty: nothing was drawn")

    def test_the_top_to_bottom_fixture_renders(self):
        summary, size, (w, h) = self.shoot("tb.oui", "dark")
        self.assertIn("packs: infra)", summary)
        self.assertGreater(size, 20 * 1024)


if __name__ == "__main__":
    unittest.main()
