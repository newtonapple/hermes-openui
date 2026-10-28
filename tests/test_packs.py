"""Custom component packs: linked from config, described by a JSON header, embedded in the widget page only when used."""
import base64
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
page = helpers.sub("page")
bundle = helpers.sub("bundle")
tools = helpers.sub("tools")

HAS_NODE = bool(shutil.which("node")) and bundle.VALIDATOR.is_file()
_DEFAULT = object()
HEADER = '/* hermes-openui-pack\n%s\n*/\n'
BODY = (
    "(function () {\n"
    "  var M = window.__HM.mods, React = M.react, z = M.zod.z, define = M['@openuidev/react-lang'].defineComponent;\n"
    "  var DemoBadge = define({ name: 'DemoBadge', description: 'A small badge.',\n"
    "    props: z.object({ text: z.string(), tone: z.enum(['ok', 'bad']).optional() }),\n"
    "    component: function (c) { return React.createElement('span', null, c.props.text); } });\n"
    "  window.__HM.register({ name: '%s', components: [DemoBadge],\n"
    "    validate: function (typeName, props) { return props.text === 'boom' ? ['DemoBadge text must not be boom'] : []; } });\n"
    "})();\n"
)


def pack_text(name="demo", comps=None, body=None):
    comps = comps if comps is not None else {"DemoBadge": "DemoBadge(text: string, tone?: \"ok\" | \"bad\") \u2014 A small badge."}
    return HEADER % json.dumps({"api": 1, "name": name, "components": comps}) + (body if body is not None else BODY % name)


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p


class ParseHeader(unittest.TestCase):
    def test_valid_header(self):
        h = packs.parse_header(pack_text())
        self.assertEqual(h["name"], "demo")
        self.assertEqual(list(h["components"]), ["DemoBadge"])

    def test_missing_header_names_the_marker(self):
        with self.assertRaisesRegex(packs.PackError, "hermes-openui-pack"):
            packs.parse_header("(function(){})();")

    def test_bad_json(self):
        with self.assertRaisesRegex(packs.PackError, "JSON"):
            packs.parse_header(HEADER % "{not json" + BODY % "x")

    def test_wrong_api_version(self):
        with self.assertRaisesRegex(packs.PackError, "api"):
            packs.parse_header(HEADER % json.dumps({"api": 2, "name": "x", "components": {"Ok": "Ok()"}}) + BODY % "x")

    def test_pack_name_must_be_a_simple_slug(self):
        with self.assertRaisesRegex(packs.PackError, "name"):
            packs.parse_header(pack_text(name="Bad Name!"))

    def test_component_names_must_be_pascal_case(self):
        with self.assertRaisesRegex(packs.PackError, "PascalCase"):
            packs.parse_header(pack_text(comps={"lower": "lower()"}))

    def test_at_least_one_component(self):
        with self.assertRaisesRegex(packs.PackError, "component"):
            packs.parse_header(pack_text(comps={}))


class Load(Tmp):
    def test_loads_a_file(self):
        p = self.write("demo.js", pack_text())
        found, problems = packs.load([str(p)], {"Stack"})
        self.assertEqual(problems, [])
        self.assertEqual([x.name for x in found], ["demo"])
        self.assertEqual(found[0].path, p)
        self.assertIn("DemoBadge", found[0].components)

    def test_a_directory_loads_every_js_file_sorted_and_ignores_the_rest(self):
        self.write("b.js", pack_text("bee", {"BeeThing": "BeeThing()"}))
        self.write("a.js", pack_text("ay", {"AyThing": "AyThing()"}))
        self.write("notes.txt", "not a pack")
        found, problems = packs.load([str(self.dir)], set())
        self.assertEqual(problems, [])
        self.assertEqual([x.name for x in found], ["ay", "bee"])

    def test_expands_the_home_directory(self):
        old = os.environ.get("HOME", "")
        os.environ["HOME"] = str(self.dir)
        try:
            self.write("demo.js", pack_text())
            found, problems = packs.load(["~/demo.js"], set())
        finally:
            os.environ["HOME"] = old
        self.assertEqual((len(found), problems), (1, []))

    def test_missing_path_is_a_problem_not_an_exception(self):
        found, problems = packs.load([str(self.dir / "nope.js")], set())
        self.assertEqual(found, [])
        self.assertRegex(problems[0], "nope.js")

    def test_component_that_shadows_a_builtin_is_rejected(self):
        p = self.write("bad.js", pack_text("bad", {"Stack": "Stack()"}))
        found, problems = packs.load([str(p)], {"Stack"})
        self.assertEqual(found, [])
        self.assertRegex(problems[0], "Stack")

    def test_two_packs_cannot_claim_one_component(self):
        a = self.write("a.js", pack_text("a", {"Same": "Same()"}))
        b = self.write("b.js", pack_text("b", {"Same": "Same()"}))
        found, problems = packs.load([str(a), str(b)], set())
        self.assertEqual([x.name for x in found], ["a"])
        self.assertRegex(problems[0], "Same")

    def test_two_packs_cannot_share_a_name(self):
        a = self.write("a.js", pack_text("dup", {"One": "One()"}))
        b = self.write("b.js", pack_text("dup", {"Two": "Two()"}))
        found, problems = packs.load([str(a), str(b)], set())
        self.assertEqual(len(found), 1)
        self.assertRegex(problems[0], "dup")

    def test_network_and_eval_apis_are_refused(self):
        for bad in ("fetch('https://x.example')", "new XMLHttpRequest()", "navigator.sendBeacon('/x')", "new WebSocket('wss://x')",
                    "eval('1')", "new Function('return 1')", "import('https://x.example/m.js')"):
            with self.subTest(bad=bad):
                p = self.write("bad.js", pack_text(body="(function(){ %s; })();\n" % bad))
                found, problems = packs.load([str(p)], set())
                self.assertEqual(found, [], bad)
                self.assertTrue(problems, bad)

    def test_a_word_inside_a_string_or_comment_is_not_a_false_alarm(self):
        p = self.write("ok.js", pack_text(body='// we never call fetch( here\n(function(){ var s = "eval( is just text"; })();\n'))
        found, problems = packs.load([str(p)], set())
        self.assertEqual((len(found), problems), (1, []))

    def test_oversized_pack_is_refused(self):
        p = self.write("big.js", pack_text(body="// " + "x" * (packs.MAX_PACK_BYTES + 10) + "\n"))
        found, problems = packs.load([str(p)], set())
        self.assertEqual(found, [])
        self.assertRegex(problems[0], "KB")

    def test_one_broken_pack_does_not_take_the_others_down(self):
        good = self.write("good.js", pack_text())
        bad = self.write("bad.js", "no header here")
        found, problems = packs.load([str(bad), str(good)], set())
        self.assertEqual([x.name for x in found], ["demo"])
        self.assertEqual(len(problems), 1)


class Helpers(Tmp):
    def setUp(self):
        super().setUp()
        self.a = packs.load([str(self.write("a.js", pack_text("a", {"AlphaThing": "AlphaThing(x: string) \u2014 first.", "AlphaPart": "AlphaPart()"})))], set())[0][0]
        self.b = packs.load([str(self.write("b.js", pack_text("b", {"BetaThing": "BetaThing() \u2014 second."})))], set())[0][0]

    def test_component_map(self):
        m = packs.by_component([self.a, self.b])
        self.assertEqual(m["AlphaPart"].name, "a")
        self.assertEqual(m["BetaThing"].name, "b")

    def test_used_ignores_text_inside_strings(self):
        src = 'root = Stack([x, t])\nx = AlphaThing("hello")\nt = Text("BetaThing( is only text")'
        self.assertEqual([p.name for p in packs.used(src, [self.a, self.b])], ["a"])

    def test_reference_lists_every_signature(self):
        ref = packs.reference([self.a, self.b])
        for line in ("AlphaThing(x: string)", "AlphaPart()", "BetaThing()"):
            self.assertIn(line, ref)
        self.assertIn("Custom components", ref)

    def test_reference_is_empty_when_nothing_is_linked(self):
        self.assertEqual(packs.reference([]), "")


class PageEmbedding(Tmp):
    def setUp(self):
        super().setUp()
        self.p = packs.load([str(self.write("demo.js", pack_text()))], set())[0][0]

    def test_a_used_custom_pack_is_embedded_and_round_trips(self):
        html, names = page.build_page('root = Stack([b])\nb = DemoBadge("hi")', extra_packs=[self.p])
        self.assertIn("custom:demo", names)
        m = re.search(r'<script data-oui="custom:demo" type="text/plain">([^<]+)</script>', html)
        assert m is not None, "no blob for the custom pack"
        self.assertEqual(gzip.decompress(base64.b64decode(m.group(1))).decode("utf-8"), self.p.source)

    def test_an_unused_custom_pack_costs_nothing(self):
        html, names = page.build_page('root = Stack([t])\nt = Text("hi")', extra_packs=[self.p])
        self.assertNotIn("custom:demo", names)
        self.assertNotIn('data-oui="custom:demo"', html)

    def test_custom_blobs_come_after_the_core(self):
        html, _ = page.build_page('root = Stack([b])\nb = DemoBadge("hi")', extra_packs=[self.p])
        self.assertLess(html.index('data-oui="core"'), html.index('data-oui="custom:demo"'))


class ToolIntegration(unittest.TestCase):
    SRC = 'root = Stack([b])\nb = DemoBadge("hi")'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.tmp.name
        self.pack = Path(self.tmp.name) / "demo.js"
        self.pack.write_text(pack_text(), encoding="utf-8")
        self.settings = {"components": [str(self.pack)]}

    def tearDown(self):
        if self._old is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._old
        self.tmp.cleanup()

    def call(self, mode="preview", settings=_DEFAULT, **params):
        s = self.settings if settings is _DEFAULT else settings
        return json.loads(tools.render_widget(params, mode=mode, settings=s))

    def test_unknown_without_the_config(self):
        r = self.call(source=self.SRC, settings={})
        self.assertFalse(r["ok"])
        self.assertTrue(any("Unknown component `DemoBadge`" in e for e in r["errors"]), r)

    def test_known_when_linked_and_the_page_carries_the_pack(self):
        r = self.call(source=self.SRC, name="badge")
        self.assertTrue(r["ok"], r)
        self.assertIn("custom:demo", r["packs"])
        m = re.search(r'file="([^"]+)"', r["directive"])
        assert m is not None
        html = Path(m.group(1)).read_text(encoding="utf-8")
        self.assertIn('data-oui="custom:demo"', html)

    def test_reference_gains_a_custom_section_only_when_linked(self):
        with_cfg = self.call(reference=True)["reference"]
        without = self.call(reference=True, settings={})["reference"]
        self.assertIn("DemoBadge(text: string", with_cfg)
        self.assertNotIn("DemoBadge", without)
        self.assertTrue(with_cfg.startswith(without))

    def test_native_mode_refuses_custom_components(self):
        r = self.call(mode="native", source=self.SRC)
        self.assertFalse(r["ok"])
        self.assertTrue(any("preview" in e for e in r["errors"]), r)

    def test_native_mode_still_renders_builtin_only_sources(self):
        r = self.call(mode="native", source='root = Stack([t])\nt = Text("hi")')
        self.assertTrue(r["ok"], r)

    def test_a_broken_pack_warns_but_builtin_widgets_still_render(self):
        r = self.call(source='root = Stack([t])\nt = Text("hi")', settings={"components": [str(Path(self.tmp.name) / "missing.js")]})
        self.assertTrue(r["ok"], r)
        self.assertTrue(r.get("pack_warnings"), r)

    def test_settings_default_to_none_without_error(self):
        r = json.loads(tools.render_widget({"source": 'root = Stack([t])\nt = Text("hi")'}, mode="preview"))
        self.assertTrue(r["ok"], r)


class FakeCtx:
    """The slice of Hermes's plugin context that register() uses."""

    def __init__(self, config=None):
        self.tools, self.config = [], dict(config or {})

    def register_tool(self, **kw):
        self.tools.append(kw)

    def register_skill(self, name, path):
        pass

    def get_config(self, key, default=None):
        return self.config.get(key, default)


class RegisterSettings(Tmp):
    SRC = 'root = Stack([b])\nb = DemoBadge("hi", "ok")'

    def setUp(self):
        super().setUp()
        self._old = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(self.dir)
        self.pack = self.write("demo.js", pack_text())
        self.ctx = FakeCtx()
        helpers.load().register(self.ctx)
        self.handler = next(t["handler"] for t in self.ctx.tools if t["name"] == "render_widget")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._old
        super().tearDown()

    def test_the_components_setting_is_read_at_call_time(self):
        self.assertFalse(json.loads(self.handler({"source": self.SRC}))["ok"])  # not linked yet
        self.ctx.config["components"] = [str(self.pack)]  # changed in the settings form after registration
        r = json.loads(self.handler({"source": self.SRC}))
        self.assertTrue(r["ok"], r)
        self.assertIn("custom:demo", r["packs"])

    def test_unlinking_takes_effect_without_a_restart(self):
        self.ctx.config["components"] = [str(self.pack)]
        self.assertTrue(json.loads(self.handler({"source": self.SRC}))["ok"])
        self.ctx.config["components"] = []
        self.assertFalse(json.loads(self.handler({"source": self.SRC}))["ok"])

    def export_handler(self):
        return next(t["handler"] for t in self.ctx.tools if t["name"] == "export_widgets")

    def test_export_uses_the_export_dir_setting_read_at_call_time(self):
        folder = self.dir / "my-exports"
        self.ctx.config["export_dir"] = str(folder)
        r = json.loads(self.export_handler()({"title": "T", "sections": [{"source": 'root = Stack([t])\nt = Text("hi")'}]}))
        self.assertTrue(r["ok"], r)
        self.assertEqual(Path(r["path"]).resolve().parent, folder.resolve())

    def test_export_defaults_to_the_exports_folder_of_the_profile(self):
        r = json.loads(self.export_handler()({"sections": [{"source": 'root = Stack([t])\nt = Text("hi")'}]}))
        self.assertTrue(r["ok"], r)
        self.assertEqual(Path(r["path"]).resolve().parent, (self.dir / "exports").resolve())

    def test_export_sees_linked_packs(self):
        self.ctx.config["components"] = [str(self.pack)]
        r = json.loads(self.export_handler()({"sections": [{"source": self.SRC}]}))
        self.assertTrue(r["ok"], r)
        self.assertIn("custom:demo", r["packs"])

    def test_a_non_list_setting_does_not_crash(self):
        self.ctx.config["components"] = 42
        r = json.loads(self.handler({"source": 'root = Stack([t])\nt = Text("hi")'}))
        self.assertTrue(r["ok"], r)


class ManifestSettings(unittest.TestCase):
    def test_config_schema_declares_the_new_settings(self):
        yml = (helpers.ROOT / "plugin.yaml").read_text(encoding="utf-8")
        schema = yml.split("config_schema:")[1]
        for key, kind in (("components", "list"), ("export_dir", "str"), ("mode", "str")):
            with self.subTest(key=key):
                m = re.search(r"^  %s:\n    type: (\w+)" % key, schema, re.M)
                self.assertIsNotNone(m, key)
                self.assertEqual(m.group(1) if m else None, kind)


@unittest.skipUnless(HAS_NODE, "needs Node and assets/validate.cjs")
class ValidatorWithPacks(Tmp):
    GOOD = 'root = Stack([b])\nb = DemoBadge("hi", "ok")'

    def run_validator(self, source, *pack_paths):
        src = self.write("w.oui", source)
        cmd = ["node", str(bundle.VALIDATOR)]
        for p in pack_paths:
            cmd += ["--pack", str(p)]
        r = subprocess.run(cmd + [str(src)], capture_output=True, text=True, timeout=60, env=dict(os.environ, DO_NOT_TRACK="1"))
        return r.returncode, r.stdout + r.stderr

    def test_a_valid_source_passes_with_the_pack_linked(self):
        pack = self.write("demo.js", pack_text())
        code, out = self.run_validator(self.GOOD, pack)
        self.assertEqual(code, 0, out)

    def test_the_same_source_fails_without_the_pack(self):
        code, out = self.run_validator(self.GOOD)
        self.assertEqual(code, 1)
        self.assertIn("DemoBadge", out)

    def test_the_real_zod_schema_is_enforced(self):
        pack = self.write("demo.js", pack_text())
        code, out = self.run_validator('root = Stack([b])\nb = DemoBadge(5)', pack)
        self.assertEqual(code, 1, out)
        self.assertIn("DemoBadge", out)

    def test_the_pack_validate_hook_adds_cross_checks(self):
        pack = self.write("demo.js", pack_text())
        code, out = self.run_validator('root = Stack([b])\nb = DemoBadge("boom")', pack)
        self.assertEqual(code, 1, out)
        self.assertIn("must not be boom", out)

    def test_a_validate_hook_that_throws_is_reported_not_fatal(self):
        body = BODY.replace("return props.text === 'boom' ? ['DemoBadge text must not be boom'] : [];", "throw new Error('hook blew up');")
        pack = self.write("demo.js", pack_text(body=body % "demo"))
        code, out = self.run_validator(self.GOOD, pack)
        self.assertEqual(code, 1, out)
        self.assertIn("hook blew up", out)

    def test_a_pack_that_fails_to_load_is_named(self):
        pack = self.write("demo.js", pack_text(body="(function(){ throw new Error('bad pack'); })();\n"))
        code, out = self.run_validator(self.GOOD, pack)
        self.assertEqual(code, 1, out)
        self.assertIn("demo.js", out)
        self.assertIn("bad pack", out)

    def test_header_and_registered_components_must_agree(self):
        pack = self.write("demo.js", pack_text(comps={"DemoBadge": "DemoBadge(text: string)", "Ghost": "Ghost()"}))
        code, out = self.run_validator(self.GOOD, pack)
        self.assertEqual(code, 1, out)
        self.assertIn("Ghost", out)

    def test_tools_node_validate_passes_the_packs_through(self):
        found, _ = packs.load([str(self.write("demo.js", pack_text()))], bundle.component_names())
        self.assertEqual(tools._node_validate(self.GOOD, found), [])
        errs = tools._node_validate('root = Stack([b])\nb = DemoBadge("boom")', found)
        self.assertTrue(errs and "must not be boom" in " ".join(errs), errs)


if __name__ == "__main__":
    unittest.main()
