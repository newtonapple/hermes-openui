"""The built-in SequenceDiagram components (SeqParticipant, SeqMessage, SeqNote, SeqGroup, SequenceDiagram), shipped in the `sequence` pack.

Layers: the manifest and the reference the model reads; reserved names; the page builder; the real validator
(`node assets/validate.cjs`, no --pack) with one message per mistake; the PURE layout function run under Node with no
browser (build/src/components/sequence-layout.js); the renderer's markup; the docs page and its gate; the discovery words.
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

ROOT = helpers.ROOT
BUILD = ROOT / "build"
EXAMPLES = ROOT / "docs" / "ui-components" / "examples"
NAMES = ["SeqParticipant", "SeqMessage", "SeqNote", "SeqGroup", "SequenceDiagram"]
GOOD = ["sequence-diagram-login.oui", "sequence-diagram-cache-lookup.oui", "sequence-diagram-async-job.oui"]

SIGNATURES = {
    "SeqParticipant": 'SeqParticipant(id: string, label: string, kind?: "actor" | "service" | "database" | "queue" | "external")',
    "SeqMessage": 'SeqMessage(from: string, to: string, label: string, style?: "sync" | "async" | "return", id?: string)',
    "SeqNote": "SeqNote(over: string, text: string, to?: string)",
    "SeqGroup": 'SeqGroup(kind: "alt" | "opt" | "loop" | "par", label: string, steps: (SeqMessage | SeqNote | SeqGroup)[], elseSteps?: (SeqMessage | SeqNote | SeqGroup)[], elseLabel?: string)',
    "SequenceDiagram": "SequenceDiagram(participants: SeqParticipant[], steps: (SeqMessage | SeqNote | SeqGroup)[], title?: string, numbered?: boolean)",
}


def source(name):
    return lint.strip_fences((EXAMPLES / name).read_text(encoding="utf-8"))


def reference_line(name):
    lines = [ln for ln in bundle.reference_text().splitlines() if ln.startswith(name + "(")]
    assert len(lines) == 1, "%s appears %d times in components.md" % (name, len(lines))
    return lines[0]


def node_available():
    return bool(shutil.which("node")) and bundle.VALIDATOR.is_file()


def run_validator(text, directory):
    path = Path(directory) / ("case-%d.oui" % len(list(Path(directory).iterdir())))
    path.write_text(text, encoding="utf-8")
    r = subprocess.run(["node", str(bundle.VALIDATOR), str(path)], capture_output=True, text=True, timeout=60, env=dict(os.environ, DO_NOT_TRACK="1"))
    return r.returncode, r.stdout + r.stderr


class Manifest(unittest.TestCase):
    def test_the_five_components_belong_to_the_sequence_pack_in_reference_order(self):
        m = bundle.manifest()
        self.assertEqual(m["packs"]["sequence"]["components"], NAMES)
        for name in NAMES:
            self.assertEqual(m["components"][name], "sequence", name)
            self.assertIn(name, bundle.component_names())
            self.assertNotIn(name, m["core"]["components"])
            for other in ("charts", "diagrams", "infra", "map", "text"):
                self.assertNotIn(name, m["packs"][other]["components"], "%s leaked into the %s pack" % (name, other))

    def test_the_pack_is_shipped_small_and_matches_its_recorded_hash(self):
        info = bundle.manifest()["packs"]["sequence"]
        self.assertTrue((bundle.ASSETS / info["file"]).is_file())
        self.assertLess(info["gz"], 16 * 1024)
        self.assertEqual([p for p in bundle.verify() if "sequence" in p], [])

    def test_the_shipped_pack_has_no_network_code_and_registers_itself(self):
        info = bundle.manifest()["packs"]["sequence"]
        text = gzip.decompress((bundle.ASSETS / info["file"]).read_bytes()).decode("utf-8")
        self.assertIsNone(re.search(r"fetch\(|XMLHttpRequest|sendBeacon|WebSocket\(|EventSource\(|posthog|cloudfront", text))
        self.assertIn("window.__HM.register(", text)
        self.assertIn('"sequence"', text)
        for var in ("--foreground", "--muted-foreground", "--accent", "--border", "--card"):
            self.assertIn("var(" + var + ",", text)

    def test_the_sources_define_exactly_the_five_components_and_register_the_pack(self):
        text = (BUILD / "src" / "packs" / "sequence.jsx").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'defineComponent\(\s*\{\s*name:\s*"(\w+)"', text), NAMES)
        reg = re.search(r'export const pack = \{\s*name:\s*"([^"]+)"\s*,\s*components:\s*\[([^\]]*)\]', text)
        self.assertIsNotNone(reg, "no `export const pack = { name, components: [...] }`")
        self.assertEqual(reg.group(1), "sequence")
        self.assertEqual([x.strip() for x in reg.group(2).split(",") if x.strip()], NAMES)
        self.assertIn('"./sequence.jsx"', (BUILD / "src" / "packs" / "index.js").read_text(encoding="utf-8"))
        for rel in ("components/sequence.jsx", "components/sequence-layout.js", "components/sequence-check.js", "packs/sequence.jsx"):
            with self.subTest(source=rel):
                self.assertNotIn("window.__HM", (BUILD / "src" / rel).read_text(encoding="utf-8"))

    def test_the_layout_module_is_pure_so_node_can_load_it_without_a_bundler(self):
        for rel in ("components/sequence-layout.js", "components/sequence-check.js"):
            text = (BUILD / "src" / rel).read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("import "):
                    self.assertRegex(line, r'from "\./sequence-layout\.js"', "%s may import only the layout module" % rel)

    def test_the_desktop_plugin_carries_the_components(self):
        text = (ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8")
        for name in NAMES:
            self.assertIn(name, text)

    def test_the_older_packs_are_untouched(self):
        self.assertEqual(sorted(bundle.manifest()["packs"]), ["charts", "diagrams", "infra", "map", "sequence", "text"])


class Reference(unittest.TestCase):
    def test_every_signature_is_exactly_the_one_in_the_brief(self):
        for name, sig in SIGNATURES.items():
            with self.subTest(component=name):
                self.assertEqual(reference_line(name).split(" \u2014 ")[0], sig)

    def test_the_five_come_after_every_older_component_so_the_existing_order_is_unchanged(self):
        order = re.findall(r"^([A-Z]\w*)\(", bundle.reference_text(), re.M)
        self.assertEqual(order[-5:], NAMES)
        self.assertEqual(order[-9:-5], ["InfraNode", "InfraZone", "InfraLink", "InfraMap"])

    def test_descriptions_keep_the_facts_the_model_needs(self):
        facts = {
            "SeqParticipant": ["unique", "icon", "service"],
            "SeqMessage": ["participant id", "above the arrow", "self-call", "return", "dashed"],
            "SeqNote": ["spans", "wrapped"],
            "SeqGroup": ["frame", "elseSteps", "nest"],
            "SequenceDiagram": ["left to right", "top to bottom", "numbered", "activation", "10 participants"],
        }
        for name, words in facts.items():
            desc = reference_line(name).split(" \u2014 ", 1)[1]
            for w in words:
                with self.subTest(component=name, word=w):
                    self.assertIn(w, desc)

    def test_the_reference_gives_the_step_budget_and_the_cut_limits(self):
        desc = reference_line("SequenceDiagram").split(" \u2014 ", 1)[1]
        self.assertIn("about 20 steps", desc)
        self.assertIn("split longer flows", desc)
        self.assertIn("Header labels are cut at 22 characters, message labels at 48, group labels at 40: keep them short", desc)
        self.assertIn("100 steps", desc, "the validator limit stays in the text")

    def test_one_seqgroup_per_decision_with_the_other_side_in_elsesteps(self):
        desc = reference_line("SeqGroup").split(" \u2014 ", 1)[1]
        self.assertIn("One SeqGroup per decision; put the other side in elseSteps, not in a second group", desc)
        self.assertNotIn("per branch", desc)
        skill = (ROOT / "skills" / "openui-render" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("per branch", skill)
        self.assertIn("`SeqGroup` per decision", skill)
        docs = (ROOT / "docs" / "ui-components" / "SequenceDiagram.md").read_text(encoding="utf-8")
        self.assertNotIn("for each branch", docs)
        self.assertIn("`SeqGroup` per decision", docs)


class ReservedNames(unittest.TestCase):
    def pack_with(self, td, name):
        f = Path(td) / "mine.js"
        f.write_text('/* hermes-openui-pack\n{"api": 1, "name": "mine", "components": {"%s": "%s(a: string) \\u2014 mine."}}\n*/\n(function () {})();\n' % (name, name), encoding="utf-8")
        return packs.load([str(f)], bundle.component_names())

    def test_a_user_pack_may_not_reuse_any_built_in_sequence_name(self):
        for name in NAMES:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as td:
                found, problems = self.pack_with(td, name)
                self.assertEqual(found, [])
                self.assertEqual(len(problems), 1, problems)
                self.assertIn("shadows a built-in component", problems[0])

    def test_names_that_are_not_built_in_stay_free(self):
        with tempfile.TemporaryDirectory() as td:
            found, problems = self.pack_with(td, "SeqTimeline")  # not built in: only the five exact names are reserved by the manifest
            self.assertEqual(problems, [], problems)
            self.assertEqual([p.name for p in found], ["mine"])


class PageBuilding(unittest.TestCase):
    def test_each_component_alone_pulls_the_pack_in(self):
        for name in NAMES:
            with self.subTest(component=name):
                self.assertEqual(page.select_packs("root = Stack([x])\nx = %s()" % name), ["sequence"])

    def test_names_inside_text_do_not_pull_the_pack_in(self):
        self.assertEqual(page.select_packs('root = Stack([t])\nt = Text("Use SequenceDiagram( and SeqNote( here", "body")'), [])

    def test_the_examples_embed_only_the_sequence_pack_and_fit_the_page_budget(self):
        for name in GOOD:
            with self.subTest(example=name):
                html, embedded = page.build_page(source(name))
                self.assertEqual(embedded, ["sequence"])
                self.assertIn('data-oui="sequence"', html)
                self.assertLess(len(html.encode("utf-8")), page.SAFE_BUDGET)

    def test_the_everything_flag_includes_sequence(self):
        self.assertIn("sequence", page.select_packs("root = Stack([])", everything=True))


def diagram(parts, steps, tail=""):
    """OpenUI Lang for one diagram. parts = [(id, label)], steps = lines of `name = Seq...(...)`; the diagram lists the ones no other step uses."""
    names = [ln.split(" = ", 1)[0] for ln in steps]

    def used(n):
        return any(re.search(r"[\[, ]%s[\],]" % re.escape(n), ln.split(" = ", 1)[1]) for ln in steps if not ln.startswith(n + " = "))

    top = [n for n in names if not used(n)]
    lines = ["root = Stack([d])", "d = SequenceDiagram([%s], [%s]%s)" % (", ".join("p%d" % i for i in range(len(parts))), ", ".join(top), tail)]
    for i, (pid, label) in enumerate(parts):
        lines.append('p%d = SeqParticipant("%s", "%s")' % (i, pid, label))
    return "\n".join(lines + list(steps)) + "\n"


@unittest.skipUnless(node_available(), "needs Node and assets/validate.cjs")
class Validator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        two = [("client", "Client"), ("api", "Api")]
        ok = ['m1 = SeqMessage("client", "api", "hello")']
        deep = [
            'g1 = SeqGroup("alt", "one", [g2])', 'g2 = SeqGroup("opt", "two", [g3])', 'g3 = SeqGroup("loop", "three", [g4])',
            'g4 = SeqGroup("par", "deepest", [n1])', 'n1 = SeqNote("api", "too deep")',
        ]
        many_steps = ['m%d = SeqMessage("client", "api", "call %d")' % (i, i) for i in range(101)]
        cases = {
            "fine": diagram(two, ok),
            "dup_part": diagram([("api", "A"), ("api", "B")], ['m1 = SeqMessage("api", "api", "loop")']),
            "unknown_from": diagram(two, ['m1 = SeqMessage("ghost", "api", "hello")']),
            "unknown_to": diagram(two, ['m1 = SeqMessage("client", "ghost", "hello")']),
            "label_not_id": diagram(two, ['m1 = SeqMessage("client", "Api", "hello")']),
            "note_over": diagram(two, ['n1 = SeqNote("ghost", "remember this")']),
            "note_to": diagram(two, ['n1 = SeqNote("client", "remember this", "ghost")']),
            "note_ok": diagram(two, ['n1 = SeqNote("client", "spans both", "api")']),
            "too_many_parts": diagram([("p%d" % i, "P%d" % i) for i in range(11)], ['m1 = SeqMessage("p0", "p1", "hello")']),
            "ten_parts": diagram([("p%d" % i, "P%d" % i) for i in range(10)], ['m1 = SeqMessage("p0", "p1", "hello")']),
            "too_many_steps": diagram(two, many_steps),
            "steps_at_limit": diagram(two, many_steps[:100]),
            "nested_steps_count": diagram(two, ['m1 = SeqMessage("client", "api", "a")', 'g1 = SeqGroup("loop", "again", [%s])' % ", ".join("n%d" % i for i in range(100))]
                                          + ['n%d = SeqNote("api", "note %d")' % (i, i) for i in range(100)]),
            "too_deep": diagram(two, deep),
            "depth_three": diagram(two, ['g1 = SeqGroup("alt", "one", [g2])', 'g2 = SeqGroup("opt", "two", [g3])', 'g3 = SeqGroup("loop", "three", [n1])', 'n1 = SeqNote("api", "fine")']),
            "not_seq": "root = Stack([d])\nd = SequenceDiagram([p0, p1], [m1, t1])\np0 = SeqParticipant(\"a\", \"A\")\np1 = SeqParticipant(\"b\", \"B\")\nm1 = SeqMessage(\"a\", \"b\", \"hi\")\nt1 = Text(\"oops\", \"body\")\n",
            "not_seq_in_group": "root = Stack([d])\nd = SequenceDiagram([p0, p1], [g1])\np0 = SeqParticipant(\"a\", \"A\")\np1 = SeqParticipant(\"b\", \"B\")\ng1 = SeqGroup(\"alt\", \"x\", [m1], [t1], \"else\")\nm1 = SeqMessage(\"a\", \"b\", \"hi\")\nt1 = Text(\"oops\", \"body\")\n",
            "empty_parts": "root = Stack([d])\nd = SequenceDiagram([], [])\n",
            "text_in_participants": "root = Stack([d])\nd = SequenceDiagram([p0, t1], [m1])\np0 = SeqParticipant(\"a\", \"A\")\nt1 = Text(\"oops\", \"body\")\nm1 = SeqMessage(\"a\", \"a\", \"hi\")\n",
            "message_in_participants": "root = Stack([d])\nd = SequenceDiagram([p0, m0], [m1])\np0 = SeqParticipant(\"a\", \"A\")\nm0 = SeqMessage(\"a\", \"a\", \"x\")\nm1 = SeqMessage(\"a\", \"a\", \"hi\")\n",
            "one_part_self": diagram([("api", "Api")], ['m1 = SeqMessage("api", "api", "retry")']),
            "one_part_other": diagram([("api", "Api")], ['m1 = SeqMessage("api", "web", "call")']),
            "dup_msg_id": diagram(two, ['m1 = SeqMessage("client", "api", "a", "sync", "step-1")', 'm2 = SeqMessage("api", "client", "b", "return", "step-1")']),
            "all_options": diagram(two, ['m1 = SeqMessage("client", "api", "a", "async", "x1")', 'm2 = SeqMessage("api", "client", "b", "return", "x2")', 'm3 = SeqMessage("client", "api", "c", "sync")'], ', "T", false'),
            "bad_style": diagram(two, ['m1 = SeqMessage("client", "api", "a", "dotted")']),
            "bad_group_kind": diagram(two, ['g1 = SeqGroup("maybe", "x", [m1])', 'm1 = SeqMessage("client", "api", "a")']),
            "leaf_alone": 'root = Stack([m])\nm = SeqMessage("a", "b", "x")\n',
        }
        cls.out = {k: run_validator(v, cls.td.name) for k, v in cases.items()}
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

    def passes(self, key):
        code, out = self.out[key]
        self.assertEqual(code, 0, out)

    def test_the_three_doc_examples_pass_with_no_pack_linked(self):
        for name in GOOD:
            with self.subTest(example=name):
                self.passes(name)

    def test_valid_diagrams_and_leaf_components_pass(self):
        for key in ("fine", "note_ok", "ten_parts", "steps_at_limit", "depth_three", "one_part_self", "all_options", "leaf_alone"):
            with self.subTest(case=key):
                self.passes(key)

    def test_duplicate_participant_id(self):
        self.assertEqual(self.problems("dup_part"), ["SequenceDiagram has duplicate participant ids: api (every SeqParticipant id must be unique)."])

    def test_unknown_participant_in_a_message_names_the_id_and_lists_the_known_ones(self):
        self.assertEqual(self.problems("unknown_from"), ["SeqMessage \"hello\" uses unknown participant id `ghost` in `from` (SeqMessage takes SeqParticipant id strings, not variable names or labels; known ids: client, api)."])
        self.assertEqual(self.problems("unknown_to"), ["SeqMessage \"hello\" uses unknown participant id `ghost` in `to` (SeqMessage takes SeqParticipant id strings, not variable names or labels; known ids: client, api)."])

    def test_a_label_used_as_an_id_says_which_id_was_meant(self):
        problems = self.problems("label_not_id")
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(problems[0].endswith("`Api` is a label; the id is `api`."), problems[0])

    def test_unknown_participant_in_a_note(self):
        self.assertEqual(self.problems("note_over"), ["SeqNote \"remember this\" uses unknown participant id `ghost` in `over` (SeqNote takes SeqParticipant id strings, not variable names or labels; known ids: client, api)."])

    def test_unknown_to_in_a_note(self):
        self.assertEqual(self.problems("note_to"), ["SeqNote \"remember this\" uses unknown participant id `ghost` in `to` (SeqNote takes SeqParticipant id strings, not variable names or labels; known ids: client, api)."])

    def test_more_than_ten_participants(self):
        self.assertEqual(self.problems("too_many_parts"), ["SequenceDiagram has 11 participants; use at most 10 (split the flow into two diagrams, or merge participants that always appear together)."])

    def test_more_than_a_hundred_steps(self):
        self.assertEqual(self.problems("too_many_steps"), ["SequenceDiagram has 101 steps in total (messages, notes and groups, nested ones included); use at most 100 (split the flow into two diagrams)."])

    def test_nested_steps_count_towards_the_hundred(self):
        # 1 message + 1 group + 100 notes inside it = 102
        self.assertEqual(self.problems("nested_steps_count"), ["SequenceDiagram has 102 steps in total (messages, notes and groups, nested ones included); use at most 100 (split the flow into two diagrams)."])

    def test_groups_nested_deeper_than_three(self):
        self.assertEqual(self.problems("too_deep"), ["SeqGroup `par` \"deepest\" is nested 4 deep; use at most 3 levels (flatten the groups, or split the flow into two diagrams)."])

    def test_a_step_that_is_not_a_seq_item(self):
        self.assertEqual(self.problems("not_seq"), ["SequenceDiagram `steps` can hold only SeqMessage, SeqNote and SeqGroup, but step 2 is Text (use SeqMessage for a call, SeqNote for a remark, SeqGroup for alt / opt / loop / par)."])
        self.assertEqual(self.problems("not_seq_in_group"), ["SeqGroup `alt` \"x\" `elseSteps` can hold only SeqMessage, SeqNote and SeqGroup, but step 1 is Text (use SeqMessage for a call, SeqNote for a remark, SeqGroup for alt / opt / loop / par)."])

    def test_an_item_in_participants_that_is_not_a_seqparticipant(self):
        fix = "(give each column as SeqParticipant(id, label, kind?) and put calls in `steps`)."
        self.assertEqual(self.problems("text_in_participants"), ["SequenceDiagram `participants` can hold only SeqParticipant, but item 2 is Text " + fix])
        self.assertEqual(self.problems("message_in_participants"), ["SequenceDiagram `participants` can hold only SeqParticipant, but item 2 is SeqMessage " + fix])

    def test_empty_participants(self):
        self.assertEqual(self.problems("empty_parts"), ["SequenceDiagram needs participants: give `participants` at least two SeqParticipant items (one is enough only when every message is a self-call)."])

    def test_one_participant_is_fine_for_self_calls_only(self):
        self.passes("one_part_self")
        problems = self.problems("one_part_other")
        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(any("unknown participant id `web` in `to`" in p for p in problems), problems)
        self.assertIn("SequenceDiagram has one participant (`api`), so every message must be a self-call; add the other participant as a SeqParticipant.", problems)

    def test_duplicate_message_id(self):
        self.assertEqual(self.problems("dup_msg_id"), ["SequenceDiagram has duplicate message ids: step-1 (every SeqMessage id must be unique)."])

    def test_a_made_up_style_or_group_kind_is_a_schema_error(self):
        for key in ("bad_style", "bad_group_kind"):
            with self.subTest(case=key):
                code, out = self.out[key]
                self.assertEqual(code, 1, out)
                self.assertIn("OpenUI validation FAILED", out)


# ---- the pure layout, run under Node with no bundler and no browser -----------------------------------------------------

LAYOUT_HARNESS = r"""
const cfg = JSON.parse(process.env.SEQ_CFG);
const mod = await import(cfg.url);
const out = {};
for (const [name, sc] of Object.entries(cfg.scenarios)) {
  try { out[name] = mod.layoutSequence(sc); } catch (e) { out[name] = { error: String((e && e.stack) || e) }; }
}
const act = {};
for (const [name, msgs] of Object.entries(cfg.matches)) act[name] = mod.matchActivations(msgs);
process.stdout.write(JSON.stringify({ out, act }));
"""


def P(*ids):
    return [{"id": i, "label": i.capitalize(), "kind": "service"} for i in ids]


CJK20 = "\u4f60\u597d\u4e16\u754c" * 5  # 20 Chinese characters, each about two Latin characters wide


def units(s):
    """The layout's width unit: a code point at or above U+2E80 counts 2, every other one counts 1."""
    return sum(2 if ord(c) >= 0x2E80 else 1 for c in s)


def M(a, b, label="call", style="sync", id=None):
    return {"t": "msg", "from": a, "to": b, "label": label, "style": style, "id": id}


def N(over, text, to=None):
    return {"t": "note", "over": over, "text": text, "to": to}


def G(kind, label, steps, else_steps=None, else_label=None):
    return {"t": "group", "kind": kind, "label": label, "steps": steps, "elseSteps": else_steps, "elseLabel": else_label}


def scenarios():
    long = "a very long message label that needs a wide gap"
    return {
        "basic": {"participants": P("client", "web", "api"), "steps": [M("client", "web", "GET /login"), M("web", "api", "check"), M("api", "web", "ok", "return"), M("web", "client", "200", "return")], "numbered": True},
        "unnumbered": {"participants": P("a", "b"), "steps": [M("a", "b", "x"), M("b", "a", "y", "return")], "numbered": False},
        "long_neighbors": {"participants": P("a", "b"), "steps": [M("a", "b", long)]},
        "short_neighbors": {"participants": P("a", "b"), "steps": [M("a", "b", "x")]},
        "spread": {"participants": P("a", "b", "c"), "steps": [M("a", "b", "x"), M("b", "c", "y"), M("a", "c", long)]},
        "reverse": {"participants": P("a", "b"), "steps": [M("b", "a", "back")]},
        "styles": {"participants": P("a", "b"), "steps": [M("a", "b", "s", "sync"), M("a", "b", "t", "async"), M("b", "a", "u", "return")]},
        "self": {"participants": P("a", "b", "c"), "steps": [M("b", "b", "validate the token", "sync"), M("b", "c", "next")]},
        "self_last": {"participants": P("a", "b"), "steps": [M("b", "b", "refresh the local cache entry")]},
        "bars": {"participants": P("a", "b", "c"), "steps": [M("a", "b", "call"), M("b", "c", "inner"), M("c", "b", "inner done", "return"), M("b", "a", "done", "return"), M("a", "c", "orphan")]},
        "nested_bars": {"participants": P("a", "b"), "steps": [M("a", "b", "one"), M("a", "b", "two"), M("b", "a", "two done", "return"), M("b", "a", "one done", "return")]},
        "note_one": {"participants": P("a", "b"), "steps": [N("a", "short"), N("b", "a longer remark that has to wrap over several lines of the note box because it is long")]},
        "note_span": {"participants": P("a", "b", "c"), "steps": [N("a", "spans two lifelines", "c")]},
        "group": {"participants": P("a", "b"), "steps": [M("a", "b", "first"), G("alt", "cache hit?", [M("b", "a", "hit", "return")], [M("b", "a", "miss", "return")], "cache miss"), M("a", "b", "last")]},
        "group_no_else": {"participants": P("a", "b"), "steps": [G("loop", "every second", [M("a", "b", "poll")])]},
        "nested_groups": {"participants": P("a", "b", "c"), "steps": [G("par", "outer", [G("opt", "inner", [M("a", "b", "x"), N("c", "n")])])]},
        "numbering_nested": {"participants": P("a", "b"), "steps": [M("a", "b", "one"), G("alt", "g", [M("a", "b", "two")], [M("b", "a", "three")]), M("a", "b", "four")]},
        "unknown": {"participants": P("a", "b"), "steps": [M("a", "ghost", "lost"), M("a", "b", "kept"), N("ghost", "gone")]},
        "empty": {"participants": [], "steps": []},
        "only_self": {"participants": P("a"), "steps": [M("a", "a", "tick")]},
        "no_steps": {"participants": P("a", "b"), "steps": []},
        "proto": {"participants": P("constructor", "__proto__"), "steps": [M("constructor", "__proto__", "x")]},
        "cjk": {"participants": P("a", "b"), "steps": [M("a", "b", CJK20)], "numbered": False},
        "latin20": {"participants": P("a", "b"), "steps": [M("a", "b", "abcdefghij" * 2)], "numbered": False},
        "cjk_cut": {"participants": P("a", "b"), "steps": [M("a", "b", CJK20 * 2), G("alt", CJK20 * 2, [M("b", "a", "ok", "return")])], "numbered": False},
        "cjk_header": {"participants": [{"id": "a", "label": CJK20, "kind": "service"}, {"id": "b", "label": "B", "kind": "service"}], "steps": [M("a", "b", "x")]},
        "cjk_note": {"participants": P("a", "b"), "steps": [N("a", CJK20 * 3)]},
        "ten": {"participants": P(*["p%d" % i for i in range(10)]), "steps": [M("p%d" % i, "p%d" % (i + 1), "step %d" % i) for i in range(9)]},
    }


MATCHES = {
    "pair": [M("a", "b", "x"), M("b", "a", "y", "return")],
    "none": [M("a", "b", "x"), M("a", "b", "y", "async"), M("b", "a", "z", "return")][:2],
    "innermost": [M("a", "b", "1"), M("a", "b", "2"), M("b", "a", "r2", "return"), M("b", "a", "r1", "return")],
    "other_pair_does_not_close": [M("a", "b", "x"), M("b", "c", "y", "return"), M("c", "a", "z", "return")],
    "unmatched_return": [M("b", "a", "r", "return")],
    "interleaved": [M("a", "b", "1"), M("b", "c", "2"), M("c", "b", "r2", "return"), M("b", "a", "r1", "return")],
}


def node_ok():
    return bool(shutil.which("node"))


def box_inside(inner, outer, m=0.01):
    return inner["x"] >= outer["x"] - m and inner["y"] >= outer["y"] - m and inner["x"] + inner["w"] <= outer["x"] + outer["w"] + m and inner["y"] + inner["h"] <= outer["y"] + outer["h"] + m


@unittest.skipUnless(node_ok(), "needs Node")
class PureLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = {"url": (BUILD / "src" / "components" / "sequence-layout.js").as_uri(), "scenarios": scenarios(), "matches": MATCHES}
        r = subprocess.run(["node", "--input-type=module", "-e", LAYOUT_HARNESS], capture_output=True, text=True, timeout=60,
                           env=dict(os.environ, SEQ_CFG=json.dumps(cfg), DO_NOT_TRACK="1"))
        if r.returncode != 0:
            raise AssertionError("node layout harness failed:\n" + (r.stderr or r.stdout)[-2000:])
        res = json.loads(r.stdout)
        cls.out, cls.act = res["out"], res["act"]

    def lay(self, name):
        lay = self.out[name]
        self.assertNotIn("error", lay, lay.get("error"))
        return lay

    def col(self, lay, pid):
        return next(c for c in lay["columns"] if c["id"] == pid)

    def test_nothing_crashes_and_every_number_is_finite(self):
        for name in self.out:
            with self.subTest(scenario=name):
                lay = self.lay(name)
                self.assertEqual(len(lay["viewBox"]), 4)
                for v in lay["viewBox"]:
                    self.assertTrue(isinstance(v, (int, float)) and v == v and abs(v) < 1e6, lay["viewBox"])
                self.assertGreater(lay["viewBox"][2], 0)
                self.assertGreater(lay["viewBox"][3], 0)
                self.assertNotIn("NaN", json.dumps(lay))

    def test_participants_are_columns_left_to_right_in_the_order_given(self):
        lay = self.lay("basic")
        self.assertEqual([c["id"] for c in lay["columns"]], ["client", "web", "api"])
        xs = [c["cx"] for c in lay["columns"]]
        self.assertEqual(xs, sorted(xs))
        for a, b in zip(lay["columns"], lay["columns"][1:]):
            self.assertLess(a["x"] + a["w"], b["x"], "header boxes touch or overlap")
        for c in lay["columns"]:
            self.assertAlmostEqual(c["x"] + c["w"] / 2, c["cx"], places=1)

    def test_a_dashed_lifeline_runs_from_each_header_to_below_the_last_row(self):
        lay = self.lay("basic")
        self.assertEqual([l["id"] for l in lay["lifelines"]], ["client", "web", "api"])
        bottom = max(m["y"] for m in lay["messages"])
        for l, c in zip(lay["lifelines"], lay["columns"]):
            self.assertAlmostEqual(l["x"], c["cx"], places=1)
            self.assertGreaterEqual(l["y1"], c["y"] + c["h"] - 0.5)
            self.assertGreater(l["y2"], bottom)

    def test_steps_run_top_to_bottom_in_order(self):
        ys = [m["y"] for m in self.lay("basic")["messages"]]
        self.assertEqual(ys, sorted(ys))
        self.assertEqual(len(set(ys)), len(ys))
        self.assertGreater(ys[0], self.lay("basic")["columns"][0]["y"] + self.lay("basic")["columns"][0]["h"])

    def test_both_directions_work(self):
        fwd = self.lay("basic")["messages"][0]
        self.assertLess(fwd["x1"], fwd["x2"])
        self.assertEqual(fwd["dir"], 1)
        back = self.lay("reverse")["messages"][0]
        self.assertGreater(back["x1"], back["x2"])
        self.assertEqual(back["dir"], -1)

    def test_a_label_sits_between_the_two_lifelines_and_the_gap_widens_to_fit_it(self):
        lay = self.lay("long_neighbors")
        a, b = self.col(lay, "a"), self.col(lay, "b")
        box = lay["messages"][0]["labelBox"]
        self.assertGreaterEqual(box["x"], a["cx"])
        self.assertLessEqual(box["x"] + box["w"], b["cx"])
        self.assertGreater(b["cx"] - a["cx"], self.col(self.lay("short_neighbors"), "b")["cx"] - self.col(self.lay("short_neighbors"), "a")["cx"] + 100)
        self.assertAlmostEqual(box["x"] + box["w"] / 2, (a["cx"] + b["cx"]) / 2, delta=1.5)

    def test_a_label_above_its_arrow(self):
        m = self.lay("basic")["messages"][0]
        self.assertLessEqual(m["labelBox"]["y"] + m["labelBox"]["h"], m["y"] + 0.5)

    def test_a_message_over_several_columns_spreads_the_width_instead_of_stretching_one_gap(self):
        lay = self.lay("spread")
        a, b, c = (self.col(lay, i) for i in "abc")
        box = lay["messages"][2]["labelBox"]
        self.assertGreaterEqual(box["x"], a["cx"] - 0.5)
        self.assertLessEqual(box["x"] + box["w"], c["cx"] + 0.5)
        base = self.col(self.lay("short_neighbors"), "b")["cx"] - self.col(self.lay("short_neighbors"), "a")["cx"]
        g1, g2 = b["cx"] - a["cx"], c["cx"] - b["cx"]
        self.assertGreater(g1 + g2, base * 2 + 20, "the wide label added nothing")
        self.assertLess(max(g1, g2), g1 + g2 - base + 1, "the whole need landed on one gap")

    def test_styles_map_to_line_and_arrowhead(self):
        sync, asyn, ret = self.lay("styles")["messages"]
        self.assertEqual((sync["dashed"], sync["head"]), (False, "filled"))
        self.assertEqual((asyn["dashed"], asyn["head"]), (False, "open"))
        self.assertEqual((ret["dashed"], ret["head"]), (True, "open"))

    def test_messages_are_numbered_in_order_of_appearance_nested_groups_included(self):
        nums = [m["number"] for m in self.lay("numbering_nested")["messages"]]
        self.assertEqual(nums, [1, 2, 3, 4])
        self.assertEqual([m["number"] for m in self.lay("unnumbered")["messages"]], [None, None])
        self.assertEqual([m["number"] for m in self.lay("basic")["messages"]], [1, 2, 3, 4])

    def test_a_self_call_is_a_loop_on_the_right_with_room_for_its_label(self):
        lay = self.lay("self")
        m = lay["messages"][0]
        b, c = self.col(lay, "b"), self.col(lay, "c")
        self.assertTrue(m["self"])
        self.assertGreaterEqual(min(m["x1"], m["x2"]), b["cx"] - 0.5)
        self.assertGreater(m["loop"]["w"], 10)
        self.assertGreaterEqual(m["labelBox"]["x"], b["cx"] + m["loop"]["w"] - 0.5)
        self.assertLessEqual(m["labelBox"]["x"] + m["labelBox"]["w"], c["cx"] + 0.5, "the label runs into the next lifeline")
        self.assertGreater(m["rowH"], self.lay("basic")["messages"][0]["rowH"], "a loop needs a taller row")

    def test_a_self_call_on_the_last_column_widens_the_diagram_instead_of_being_cut_off(self):
        lay = self.lay("self_last")
        m = lay["messages"][0]
        vb = lay["viewBox"]
        self.assertLessEqual(m["labelBox"]["x"] + m["labelBox"]["w"], vb[0] + vb[2] + 0.01)

    def test_activation_bars_pair_a_sync_with_the_next_return_back_to_its_sender(self):
        self.assertEqual(self.act["pair"], [[0, 1]])
        self.assertEqual(self.act["none"], [], "a sync with no return gets no bar")
        self.assertEqual(self.act["innermost"], [[1, 2], [0, 3]], "a return closes the innermost matching sync")
        self.assertEqual(self.act["other_pair_does_not_close"], [], "a return to a different participant closes nothing")
        self.assertEqual(self.act["unmatched_return"], [])
        self.assertEqual(self.act["interleaved"], [[1, 2], [0, 3]])

    def test_bars_are_drawn_on_the_receiver_between_the_call_and_its_return(self):
        lay = self.lay("bars")
        msgs = lay["messages"]
        bars = lay["activations"]
        self.assertEqual(sorted((b["participant"], b["open"], b["close"]) for b in bars), [("b", 0, 3), ("c", 1, 2)])
        for b in bars:
            self.assertAlmostEqual(b["y1"], msgs[b["open"]]["y"], delta=6)
            self.assertAlmostEqual(b["y2"], msgs[b["close"]]["y"], delta=6)
            c = self.col(lay, b["participant"])
            self.assertAlmostEqual(b["x"] + b["w"] / 2, c["cx"], delta=0.6)
            self.assertLess(b["w"], 14, "a thin bar")
        self.assertEqual([b for b in bars if b["participant"] == "c" and b["open"] == 4], [], "the orphan sync has no bar")

    def test_nested_activations_on_one_participant_are_offset(self):
        bars = sorted(self.lay("nested_bars")["activations"], key=lambda b: b["depth"])
        self.assertEqual([b["depth"] for b in bars], [0, 1])
        self.assertGreater(bars[1]["x"], bars[0]["x"] + 1)
        self.assertLess(bars[1]["x"] - bars[0]["x"], bars[0]["w"], "offset slightly, not side by side")

    def test_arrows_stop_at_the_edge_of_an_activation_bar(self):
        lay = self.lay("bars")
        first = lay["messages"][0]
        bar = next(b for b in lay["activations"] if b["open"] == 0)
        self.assertAlmostEqual(first["x2"], bar["x"], delta=0.6)

    def test_a_note_over_one_participant_is_centred_on_it_and_its_text_wraps(self):
        lay = self.lay("note_one")
        short, long = lay["notes"]
        a, b = self.col(lay, "a"), self.col(lay, "b")
        self.assertAlmostEqual(short["x"] + short["w"] / 2, a["cx"], delta=0.6)
        self.assertAlmostEqual(long["x"] + long["w"] / 2, b["cx"], delta=0.6)
        self.assertEqual(len(short["lines"]), 1)
        self.assertGreater(len(long["lines"]), 2)
        self.assertGreater(long["h"], short["h"])
        self.assertEqual(" ".join(long["lines"]), "a longer remark that has to wrap over several lines of the note box because it is long")
        for ln in long["lines"]:
            self.assertLessEqual(len(ln) * 6.2, long["w"], "a line is wider than its box")

    def test_a_note_over_two_participants_spans_both_lifelines(self):
        lay = self.lay("note_span")
        n = lay["notes"][0]
        a, c = self.col(lay, "a"), self.col(lay, "c")
        self.assertLessEqual(n["x"], a["cx"])
        self.assertGreaterEqual(n["x"] + n["w"], c["cx"])

    def test_a_group_is_a_frame_with_a_label_tab_and_an_else_divider(self):
        lay = self.lay("group")
        g = lay["groups"][0]
        self.assertEqual((g["kind"], g["label"], g["depth"]), ("alt", "cache hit?", 0))
        self.assertTrue(box_inside(g["tab"], g) or g["tab"]["x"] == g["x"], "the tab sits at the top left of the frame")
        self.assertAlmostEqual(g["tab"]["x"], g["x"], delta=0.6)
        self.assertAlmostEqual(g["tab"]["y"], g["y"], delta=0.6)
        self.assertEqual(g["divider"]["label"], "cache miss")
        msgs = lay["messages"]
        self.assertLess(msgs[1]["y"], g["divider"]["y"], "the first branch sits above the divider")
        self.assertGreater(msgs[2]["y"], g["divider"]["y"], "the else branch sits below it")
        self.assertGreater(g["y"] + g["h"], msgs[2]["y"])
        self.assertLess(g["y"] + g["h"], msgs[3]["y"] - 10, "steps after the group stay outside the frame")
        self.assertLess(msgs[0]["y"], g["y"])
        for i in (1, 2):
            self.assertGreater(msgs[i]["y"], g["tab"]["y"] + g["tab"]["h"] + 8, "a label must clear the tab")

    def test_a_frame_clears_the_lifelines_it_covers_so_its_tab_is_not_squeezed_against_a_bar(self):
        lay = self.lay("group")
        g = lay["groups"][0]
        self.assertLessEqual(g["x"], self.col(lay, "a")["cx"] - 10)
        self.assertGreaterEqual(g["x"] + g["w"], self.col(lay, "b")["cx"] + 10)

    def test_a_group_without_else_has_no_divider(self):
        self.assertIsNone(self.lay("group_no_else")["groups"][0]["divider"])

    def test_the_frame_is_wide_enough_for_its_tab(self):
        g = self.lay("group_no_else")["groups"][0]
        self.assertGreaterEqual(g["w"], g["tab"]["w"] + 6)

    def test_nested_frames_are_inset_inside_their_parent(self):
        lay = self.lay("nested_groups")
        outer = next(g for g in lay["groups"] if g["label"] == "outer")
        inner = next(g for g in lay["groups"] if g["label"] == "inner")
        self.assertEqual((outer["depth"], inner["depth"]), (0, 1))
        self.assertGreater(inner["x"], outer["x"] + 2)
        self.assertLess(inner["x"] + inner["w"], outer["x"] + outer["w"] - 2)
        self.assertGreater(inner["y"], outer["y"] + outer["tab"]["h"] - 1)
        self.assertLess(inner["y"] + inner["h"], outer["y"] + outer["h"] - 2)

    def test_everything_drawn_sits_inside_the_view_box(self):
        for name in ("basic", "group", "nested_groups", "note_one", "note_span", "self", "self_last", "bars", "ten"):
            lay = self.lay(name)
            vb = {"x": lay["viewBox"][0], "y": lay["viewBox"][1], "w": lay["viewBox"][2], "h": lay["viewBox"][3]}
            with self.subTest(scenario=name):
                for it in lay["columns"] + lay["notes"] + lay["groups"] + [m["labelBox"] for m in lay["messages"]]:
                    self.assertTrue(box_inside(it, vb), "%r is outside the view box %r" % (it, vb))
                for l in lay["lifelines"]:
                    self.assertLessEqual(l["y2"], vb["y"] + vb["h"] + 0.01)

    def test_no_label_covers_a_note_or_another_label(self):
        for name in ("basic", "group", "bars", "note_one"):
            lay = self.lay(name)
            boxes = [(("m", i), m["labelBox"]) for i, m in enumerate(lay["messages"])] + [(("n", i), n) for i, n in enumerate(lay["notes"])]
            with self.subTest(scenario=name):
                for i, (ka, a) in enumerate(boxes):
                    for kb, b in boxes[i + 1:]:
                        overlap = a["x"] < b["x"] + b["w"] - 0.5 and b["x"] < a["x"] + a["w"] - 0.5 and a["y"] < b["y"] + b["h"] - 0.5 and b["y"] < a["y"] + a["h"] - 0.5
                        self.assertFalse(overlap, "%r overlaps %r" % (ka, kb))

    def test_the_ten_participant_diagram_is_wide_but_finite(self):
        lay = self.lay("ten")
        self.assertEqual(len(lay["columns"]), 10)
        self.assertGreater(lay["viewBox"][2], 800)

    def test_unknown_participants_are_warned_about_and_skipped(self):
        lay = self.lay("unknown")
        self.assertEqual([m["label"] for m in lay["messages"]], ["kept"])
        self.assertEqual(lay["notes"], [])
        self.assertTrue(any("ghost" in w for w in lay["warns"]), lay["warns"])
        self.assertEqual([m["number"] for m in lay["messages"]], [1], "a skipped message takes no number")

    def test_degenerate_input_is_drawn_not_thrown(self):
        self.assertEqual(self.lay("empty")["columns"], [])
        self.assertEqual(len(self.lay("only_self")["messages"]), 1)
        self.assertEqual(self.lay("no_steps")["messages"], [])
        proto = self.lay("proto")
        self.assertEqual(len(proto["messages"]), 1)
        self.assertEqual(proto["warns"], [])

    def test_wide_characters_count_as_two_units_so_a_chinese_label_gets_twice_the_width(self):
        cjk, latin = self.lay("cjk"), self.lay("latin20")
        wc, wl = cjk["messages"][0]["labelBox"]["w"], latin["messages"][0]["labelBox"]["w"]
        self.assertAlmostEqual(wc / wl, 2.0, delta=0.05, msg="20 CJK characters measured %r, 20 Latin %r" % (wc, wl))
        a, b = self.col(cjk, "a"), self.col(cjk, "b")
        self.assertGreater(b["cx"] - a["cx"], self.col(latin, "b")["cx"] - self.col(latin, "a")["cx"], "the gap did not widen for the wide label")

    def test_a_chinese_label_stays_between_its_lifelines_and_inside_the_view_box(self):
        lay = self.lay("cjk")
        a, b = self.col(lay, "a"), self.col(lay, "b")
        box = lay["messages"][0]["labelBox"]
        self.assertGreaterEqual(box["x"], a["cx"])
        self.assertLessEqual(box["x"] + box["w"], b["cx"])
        vb = {"x": lay["viewBox"][0], "y": lay["viewBox"][1], "w": lay["viewBox"][2], "h": lay["viewBox"][3]}
        self.assertTrue(box_inside(box, vb), "%r is outside the view box %r" % (box, vb))

    def test_the_cut_length_is_measured_in_the_same_units(self):
        lay = self.lay("cjk_cut")
        msg = lay["messages"][0]
        self.assertTrue(msg["label"].endswith("\u2026"), msg["label"])
        self.assertLessEqual(units(msg["label"]), 48)
        self.assertGreaterEqual(units(msg["label"]), 46)
        self.assertEqual(msg["full"], CJK20 * 2, "the full label is kept for the hover title")
        group = lay["groups"][0]
        self.assertTrue(group["label"].endswith("\u2026"), group["label"])
        self.assertLessEqual(units(group["label"]), 40)
        self.assertEqual(group["full"], CJK20 * 2)
        head = self.lay("cjk_header")["columns"][0]
        self.assertTrue(head["label"].endswith("\u2026"), head["label"])
        self.assertLessEqual(units(head["label"]), 22)
        self.assertEqual(head["full"], CJK20)
        self.assertGreaterEqual(head["w"], 34 + units(head["label"]) * 6.9 + 12 - 0.5, "the header box is narrower than its text")

    def test_a_chinese_note_wraps_at_half_the_characters_a_latin_one_does(self):
        note = self.lay("cjk_note")["notes"][0]
        self.assertEqual("".join(note["lines"]), CJK20 * 3)
        self.assertGreater(len(note["lines"]), 3)
        for line in note["lines"]:
            self.assertLessEqual(units(line) * 6.2, note["w"] - 16 + 0.01, "a line is wider than the note box")


# ---- the renderer's markup (esbuild bundles the real component, React renders it to a string) --------------------------

NEEDED = ("react", "react-dom", "zod", "esbuild", "@openuidev/react-lang", "@openuidev/lang-core")


def node_missing_reason():
    if not shutil.which("node"):
        return "node is not on PATH"
    for mod in NEEDED:
        if not (BUILD / "node_modules" / mod / "package.json").is_file():
            return "build/node_modules/%s is missing (run `npm ci` in build/)" % mod
    return ""


RENDER_HARNESS = r"""
const path = require("path");
const cfg = JSON.parse(process.env.SEQ_CFG);
const req = require("module").createRequire(path.join(cfg.build, "package.json"));
const esbuild = req("esbuild");
const entry = [
  'import React from "react";',
  'import { renderToStaticMarkup } from "react-dom/server";',
  'import * as lang from "@openuidev/react-lang";',
  'import { createParser } from "@openuidev/lang-core";',
  'import { pack } from "./packs/sequence.jsx";',
  'export { React, renderToStaticMarkup, lang, createParser, pack };',
].join("\n");
const built = esbuild.buildSync({
  stdin: { contents: entry, resolveDir: path.join(cfg.build, "src"), loader: "js", sourcefile: "seq-harness.js" },
  bundle: true, platform: "node", format: "cjs", jsx: "automatic", write: false, logLevel: "error",
  define: { "process.env.NODE_ENV": '"production"' },
});
const mod = { exports: {} };
new Function("module", "exports", "require", built.outputFiles[0].text)(mod, mod.exports, require);
const { React, renderToStaticMarkup, lang, createParser, pack } = mod.exports;
const zod = req("zod/v4");
const Stack = lang.defineComponent({ name: "Stack", description: "stack", props: zod.object({ children: zod.array(zod.any()) }), component: () => null });
const library = lang.createLibrary({ root: "Stack", components: [Stack].concat(pack.components) });
const parser = createParser(library.toJSONSchema(), library.root);
const out = { pack: { name: pack.name, components: pack.components.map((c) => c.name) }, examples: {} };
const walk = (n, fn) => { if (n && typeof n === "object") { if (n.typeName) fn(n); for (const v of Object.values(n.props || {})) (Array.isArray(v) ? v : [v]).forEach((c) => walk(c, fn)); } };
for (const [name, src] of Object.entries(cfg.sources)) {
  const { root, meta } = parser.parse(src);
  const ex = { parsed: !!root, unresolved: meta.unresolved, orphaned: meta.orphaned, errors: (meta.errors || []).map((e) => e.message || String(e)), html: "" };
  walk(root, (n) => {
    if (n.typeName !== "SequenceDiagram") return;
    const comp = pack.components.find((c) => c.name === "SequenceDiagram");
    ex.html = renderToStaticMarkup(React.createElement(comp.component, { props: n.props }));
  });
  out.examples[name] = ex;
}
process.stdout.write(JSON.stringify(out));
"""


CUT_HEADER = "Participant header label that is far too long"
CUT_MESSAGE = "message label that is far too long to fit in forty-eight characters END"
CUT_GROUP = "group label that is far too long to fit in forty characters END"
CUT_SOURCE = "\n".join([
    "root = Stack([d])",
    "d = SequenceDiagram([p0, p1], [m1, g1])",
    'p0 = SeqParticipant("a", "%s")' % CUT_HEADER,
    'p1 = SeqParticipant("b", "B")',
    'm1 = SeqMessage("a", "b", "%s")' % CUT_MESSAGE,
    'g1 = SeqGroup("alt", "%s", [m2])' % CUT_GROUP,
    'm2 = SeqMessage("b", "a", "ok", "return")',
]) + "\n"


@unittest.skipIf(node_missing_reason(), node_missing_reason() or "")
class Renders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources = {n: source(n) for n in GOOD}
        sources["cut"] = CUT_SOURCE
        cfg = {"build": str(BUILD), "sources": sources}
        r = subprocess.run(["node", "-"], input=RENDER_HARNESS, capture_output=True, text=True, cwd=str(BUILD), timeout=120,
                           env=dict(os.environ, SEQ_CFG=json.dumps(cfg), DO_NOT_TRACK="1", OPENUI_TELEMETRY_DISABLED="1"))
        if r.returncode != 0:
            raise AssertionError("node render harness failed:\n" + (r.stderr or r.stdout)[-2000:])
        cls.r = json.loads(r.stdout)

    def test_it_registers_under_the_manifest_name(self):
        self.assertEqual(self.r["pack"], {"name": "sequence", "components": NAMES})

    def test_the_real_parser_accepts_the_examples(self):
        for name in GOOD:
            with self.subTest(example=name):
                ex = self.r["examples"][name]
                self.assertTrue(ex["parsed"])
                self.assertEqual((ex["unresolved"], ex["orphaned"], ex["errors"]), ([], [], []))

    def test_the_svg_is_well_formed_and_every_text_is_real_text(self):
        for name in GOOD:
            html = self.r["examples"][name]["html"]
            with self.subTest(example=name):
                self.assertIn("<svg", html)
                self.assertIn("viewBox=", html)
                for bad in ("NaN", "undefined", "Infinity", "[object"):
                    self.assertNotIn(bad, html)
                self.assertIn("<text", html)

    def test_every_participant_label_and_message_label_in_the_source_is_drawn(self):
        for name in GOOD:
            src, html = source(name), self.r["examples"][name]["html"]
            with self.subTest(example=name):
                for m in re.finditer(r'SeqParticipant\("[^"]+", "([^"]+)"', src):
                    self.assertIn(m.group(1), html)
                for m in re.finditer(r'SeqMessage\("[^"]+", "[^"]+", "([^"]+)"', src):
                    self.assertIn(m.group(1).replace("&", "&amp;"), html)

    def test_group_tabs_are_drawn_over_the_activation_bars_so_a_bar_never_hides_a_word(self):
        html = self.r["examples"]["sequence-diagram-cache-lookup.oui"]["html"]
        self.assertIn('rx="1.5"', html, "no activation bar in the sample")
        self.assertLess(html.rfind('rx="1.5"'), html.find('<tspan font-weight="700">alt</tspan>'))

    def test_numbers_are_muted_prefixes(self):
        html = self.r["examples"]["sequence-diagram-login.oui"]["html"]
        self.assertIn("1.", html)
        self.assertIn("var(--muted-foreground,", html)

    def test_colours_come_from_css_variables_not_hard_coded_values(self):
        for name in GOOD:
            html = self.r["examples"][name]["html"]
            with self.subTest(example=name):
                self.assertIsNone(re.search(r'(?:fill|stroke)="#[0-9a-fA-F]{3,6}"', html))
                self.assertIn("var(--foreground", html)

    def test_the_size_rules_match_the_other_diagrams(self):
        html = self.r["examples"]["sequence-diagram-login.oui"]["html"]
        self.assertIn("overflow-x:auto", html)
        self.assertRegex(html, r"max-width:\d+")
        self.assertRegex(html, r"min-width:\d+")
        self.assertIn("height:auto", html)

    def test_the_svg_never_shrinks_below_78_percent_of_its_natural_width_like_inframap(self):
        for name in GOOD:
            html = self.r["examples"][name]["html"]
            with self.subTest(example=name):
                m = re.search(r'<svg viewBox="(-?[\d.]+) (-?[\d.]+) ([\d.]+) ([\d.]+)"[^>]*style="([^"]*)"', html)
                if m is None:
                    self.fail("no svg style in the markup")
                w = float(m.group(3))
                floor = min(w, int(w * 0.78 + 0.5))  # min(natural, Math.round(0.78 x natural)), as in infra.jsx
                style = m.group(5)
                self.assertIn("max-width:%gpx" % w, style)
                self.assertIn("min-width:%gpx" % floor, style)
                self.assertLess(floor, w, "a diagram this wide must be allowed to shrink")

    def test_a_cut_label_keeps_its_full_text_in_a_title_for_hover(self):
        html = self.r["examples"]["cut"]["html"]
        titles = re.findall(r"<title>([^<]*)</title>", html)
        for what, full, shown in (
            ("message", CUT_MESSAGE, CUT_MESSAGE[:47] + "\u2026"),
            ("header", CUT_HEADER, CUT_HEADER[:21] + "\u2026"),
            ("group", CUT_GROUP, CUT_GROUP[:39] + "\u2026"),
        ):
            with self.subTest(label=what):
                self.assertTrue(any(full in t for t in titles), "no title holds the full %s label; titles: %r" % (what, titles))
                self.assertIn(shown, html, "the drawn %s label is the cut one" % what)
                self.assertNotIn(">" + full + "<", html, "the full %s label must not be drawn" % what)

    def test_a_label_that_was_not_cut_gets_no_extra_title(self):
        html = self.r["examples"]["sequence-diagram-login.oui"]["html"]
        titles = re.findall(r"<title>([^<]*)</title>", html)
        self.assertIn("client \u2192 web: POST /login", titles)
        self.assertEqual(len(titles), 6 + 4, titles)  # six messages and four headers, no group


# ---- docs, discovery words, skill -------------------------------------------------------------------------------------

class Docs(unittest.TestCase):
    def test_the_page_and_three_examples_exist_with_screenshots(self):
        self.assertTrue((ROOT / "docs" / "ui-components" / "SequenceDiagram.md").is_file())
        for name in GOOD:
            with self.subTest(example=name):
                self.assertTrue((EXAMPLES / name).is_file())
                self.assertTrue((ROOT / "docs" / "ui-components" / "images" / (name[:-4] + ".png")).is_file())

    def test_the_examples_use_generic_names_only(self):
        for name in GOOD:
            text = (EXAMPLES / name).read_text(encoding="utf-8")
            with self.subTest(example=name):
                self.assertEqual(helpers.private_setup_hits(text), [])
        ids = set()
        for name in GOOD:
            ids |= set(re.findall(r'SeqParticipant\("([^"]+)"', (EXAMPLES / name).read_text(encoding="utf-8")))
        self.assertLessEqual(ids, {"client", "web", "api", "db", "cache", "queue", "worker"})

    def test_the_page_explains_the_activation_rule(self):
        text = (ROOT / "docs" / "ui-components" / "SequenceDiagram.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?i)activation")
        self.assertIn("closes", text)

    def test_the_page_tells_the_truth_about_height_and_the_step_budget(self):
        text = (ROOT / "docs" / "ui-components" / "SequenceDiagram.md").read_text(encoding="utf-8")
        self.assertNotIn("Height has no limit", text)
        self.assertIn("native mode has no height limit", text)
        self.assertIn("about 1,200 px", text)
        self.assertIn("about 20 steps", text)
        self.assertIn("split longer flows into two diagrams", text)

    def test_the_page_says_where_text_can_be_selected(self):
        text = (ROOT / "docs" / "ui-components" / "SequenceDiagram.md").read_text(encoding="utf-8")
        self.assertIn("selected and copied", text)
        self.assertIn("both modes", text)

    def test_the_page_documents_returns_across_branches_and_self_returns(self):
        text = (ROOT / "docs" / "ui-components" / "SequenceDiagram.md").read_text(encoding="utf-8")
        self.assertIn("bare lifeline", text)
        self.assertIn("first branch", text)
        self.assertIn("dashed self loop", text)

    def test_example_message_ids_run_m1_m2_m3_without_gaps(self):
        for name in GOOD:
            text = (EXAMPLES / name).read_text(encoding="utf-8")
            nums = [int(n) for n in re.findall(r"^m(\d+) = SeqMessage", text, re.M)]
            with self.subTest(example=name):
                self.assertEqual(sorted(nums), list(range(1, len(nums) + 1)), nums)

    def test_the_readme_gives_one_figure_for_the_first_use_reference_and_it_is_true(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        intro = re.search(r"about ([\d,]+) tokens the first time it is used", readme)
        table = re.search(r"\| Component reference \| the first use in a chat \| about ([\d,]+) \|", readme)
        if intro is None or table is None:
            self.fail("the README lost one of the two places that give the size of the component reference")
        self.assertEqual(intro.group(1), table.group(1))
        real = (ROOT / "assets" / "components.md").stat().st_size / 4
        self.assertLessEqual(abs(int(table.group(1).replace(",", "")) - real), 50, "components.md is about %d tokens" % real)

    def test_the_docs_gate_passes_and_counts_the_new_total(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_docs.py")], capture_output=True, text=True, timeout=200,
                           env=dict(os.environ, DO_NOT_TRACK="1", PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("all 37 components documented", r.stdout)

    def test_the_gallery_index_and_the_readme_count_the_new_components(self):
        index = (ROOT / "docs" / "ui-components" / "README.md").read_text(encoding="utf-8")
        self.assertIn("[**SequenceDiagram**](SequenceDiagram.md)", index)
        self.assertIn("There are 23 components, plus 14 small helpers", index)
        for h in ("SeqParticipant", "SeqMessage", "SeqNote", "SeqGroup"):
            self.assertIn("`%s`" % h, index)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("**23 components** (37 with helpers)", readme)
        self.assertIn("SequenceDiagram", readme)
        self.assertIn("All 23 components", readme)


class Discovery(unittest.TestCase):
    def test_the_description_has_the_words_for_the_new_queries_and_stays_short(self):
        desc = schemas.RENDER_WIDGET["description"]
        low = desc.lower()
        for phrase in ("sequence diagram", "call flow", "request flow", "message sequence chart", "api call sequence"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, low)
        self.assertLessEqual(len(desc), 800)
        self.assertLessEqual(len(desc.split(". ")[0]), 60)

    def test_the_discovery_script_measures_the_new_queries(self):
        text = (ROOT / "tools" / "verify_discovery.py").read_text(encoding="utf-8")
        for q in ("sequence diagram", "call flow", "request flow", "message sequence chart", "API call sequence"):
            with self.subTest(query=q):
                self.assertIn('"%s"' % q, text)


class Skill(unittest.TestCase):
    TEXT = (ROOT / "skills" / "openui-render" / "SKILL.md").read_text(encoding="utf-8")

    def test_it_has_a_pick_the_component_row_for_sequences_of_calls(self):
        self.assertRegex(self.TEXT, r"\|[^|\n]*(sequence|calls)[^|\n]*\| `SequenceDiagram` \|")

    def test_it_has_the_rule_line_and_stays_within_the_raised_cap(self):
        self.assertIn("About 20 steps; split longer flows.", self.TEXT)
        self.assertIn("`SeqGroup` per decision", self.TEXT)
        self.assertIn("SeqGroup", self.TEXT)
        self.assertIn("return", self.TEXT)
        self.assertLessEqual(len(self.TEXT), 4500)
        self.assertGreater(len(self.TEXT), 3995, "the row was not added")
        self.assertTrue(self.TEXT.startswith("---\nname: openui-render\n"))

    def test_the_tests_that_pin_the_cap_agree_on_4500(self):
        for rel in ("tests/test_plugin.py", "tests/test_custom_components_skill.py"):
            with self.subTest(file=rel):
                self.assertIn("4500", (ROOT / rel).read_text(encoding="utf-8"))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        m = re.search(r"`hermes-openui:openui-render`, about ([\d,]+) tokens", readme)
        self.assertIsNotNone(m)
        self.assertLessEqual(abs(int(m.group(1).replace(",", "")) - len(self.TEXT) / 4), 25)


class Changelog(unittest.TestCase):
    def test_the_unreleased_section_lists_the_component_under_added(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        unreleased = text.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
        self.assertIn("### Added", unreleased)
        self.assertIn("SequenceDiagram", unreleased)


if __name__ == "__main__":
    unittest.main()
