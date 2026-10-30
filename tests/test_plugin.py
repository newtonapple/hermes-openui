import gzip
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402

bundle = helpers.sub("bundle")
ROOT = helpers.ROOT
NETWORK = re.compile(r"fetch\(|XMLHttpRequest|sendBeacon|WebSocket\(|EventSource\(|posthog|cloudfront")


class FakeCtx:
    def __init__(self, config=None):
        self.tools, self.skills, self.config = [], [], config or {}

    def register_tool(self, **kw):
        self.tools.append(kw)

    def register_skill(self, name, path):
        self.skills.append((name, Path(path)))

    def get_config(self, key, default=None):
        return self.config.get(key, default)


class Assets(unittest.TestCase):
    def test_bundles_match_their_recorded_hashes(self):
        self.assertEqual(bundle.verify(), [])

    def test_manifest_lists_every_reference_component(self):
        ref = bundle.reference_text()
        for name in bundle.component_names():
            with self.subTest(component=name):
                self.assertIn(name + "(", ref)

    def test_no_network_code_in_any_shipped_browser_file(self):
        files = [ROOT / "assets" / bundle.manifest()["core"]["file"]] + [ROOT / "assets" / p["file"] for p in bundle.manifest()["packs"].values()]
        for f in files:
            with self.subTest(file=f.name):
                self.assertIsNone(NETWORK.search(gzip.decompress(f.read_bytes()).decode("utf-8")))
        self.assertIsNone(NETWORK.search((ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8")))


class Contract(unittest.TestCase):
    def setUp(self):
        self.ctx = FakeCtx()
        helpers.load().register(self.ctx)

    def test_registers_exactly_the_declared_tools(self):
        names = [t["name"] for t in self.ctx.tools]
        self.assertEqual(names, ["render_widget", "export_widgets"])
        yml = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
        declared = re.findall(r"^\s+-\s+(\w+)\s*$", yml.split("provides_tools:")[1].split("config_schema:")[0], re.M)
        self.assertEqual(sorted(declared), sorted(names))

    def test_schema_is_well_formed_and_short(self):
        t = self.ctx.tools[0]
        schema = t["schema"]
        self.assertEqual(schema["name"], t["name"])
        self.assertEqual(schema["parameters"]["type"], "object")
        self.assertEqual(schema["parameters"]["required"], [])
        self.assertLessEqual(len(json.dumps(schema)), 2600, "schema rides on every API call when Tool Search is off")
        first = schema["description"].split(". ")[0]
        self.assertLessEqual(len(first), 60, "Tool Search shows only ~60 chars of the first sentence")
        self.assertIn("DAG", first)

    def test_description_carries_the_words_people_say(self):
        # Tool Search finds a tool by the words in its text; each of these was a measured miss before they were added.
        text = self.ctx.tools[0]["schema"]["description"].lower()
        for word in ("chart", "graph", "plot", "diagram", "flowchart", "dashboard", "table", "map", "dag", "schema", "topology", "widget", "kpi", "pie", "bar", "infrastructure", "architecture", "server", "custom", "component",
                     "sequence diagram", "call flow", "request flow", "message sequence chart", "api call sequence"):
            with self.subTest(word=word):
                self.assertIn(word, text)

    def test_handler_returns_json(self):
        out = self.ctx.tools[0]["handler"]({"reference": True})
        self.assertTrue(json.loads(out)["ok"])

    def test_mode_is_read_at_call_time(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            old = os.environ.get("HERMES_HOME")
            os.environ["HERMES_HOME"] = d
            try:
                src = 'root = Stack([t])\nt = Text("hi", "body")'
                handler = self.ctx.tools[0]["handler"]
                self.assertEqual(json.loads(handler({"source": src}))["mode"], "preview")
                self.ctx.config["mode"] = "native"
                self.assertEqual(json.loads(handler({"source": src}))["mode"], "native")
                self.ctx.config["mode"] = "nonsense"
                self.assertEqual(json.loads(handler({"source": src}))["mode"], "preview")
            finally:
                if old is None:
                    os.environ.pop("HERMES_HOME", None)
                else:
                    os.environ["HERMES_HOME"] = old

    def test_bundled_skills_are_registered_and_have_frontmatter(self):
        self.assertEqual([n for n, _ in self.ctx.skills], ["custom-components", "openui-render"])
        longest = {"custom-components": 8000, "openui-render": 5000}  # loaded in full each time a skill is used
        for name, path in self.ctx.skills:
            with self.subTest(skill=name):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\nname: %s\n" % name))
                self.assertLessEqual(len(text), longest[name])

    def test_a_hermes_without_register_skill_still_gets_the_tools(self):
        class Old(FakeCtx):
            def register_skill(self, *a, **k):
                raise AttributeError("no register_skill")

        ctx = Old()
        helpers.load().register(ctx)
        self.assertEqual([t["name"] for t in ctx.tools], ["render_widget", "export_widgets"])


class NativeFillsTheColumn(unittest.TestCase):
    """The 640 px cap belongs to the app's preview frame. Native mode draws in the chat column, so the widget root must fill
    whatever width the column has (and may shrink below it) instead of stopping at 640. These tests read the source and the
    built file, so any spelling of a cap is found without Chrome; the opt-in tests/test_native_layout.py draws it."""

    ROOT_CLASS = "hermes-openui-root"
    ALLOWED_LIMITS = {"720px", "960px"}  # native-only: the pie with its legend, the map
    ANY_LIMIT = re.compile(r"max-?(?:width|inline-?size)", re.I)
    LIMIT_VALUE = re.compile(r"""max-?(?:width|inline-?size)["']?\s*:\s*["'`]?([^;,}"'`\s]+)""", re.I)

    def built(self):
        return (ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8")

    def source(self):
        """plugin.jsx without its comments (they may say 640 when they explain the old cap)."""
        text = (ROOT / "build" / "src" / "plugin" / "plugin.jsx").read_text(encoding="utf-8")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return re.sub(r"(?m)(^|[ \t])//.*$", "", text)

    def root_style(self):
        m = re.search(r'"data-hermes-openui-widget":"",style:\{([^{}]*)\}', self.built())
        if m is None:
            self.fail("the widget root element was not found in desktop/plugin.js")
        return m.group(1)

    def source_rules(self):
        src = self.source()
        m = re.search(r"const NATIVE_CSS = \[(.*?)\]\.join\(", src, re.S)
        self.assertIsNotNone(m, "NATIVE_CSS was not found in plugin.jsx")
        name = re.search(r'const ROOT_CLASS = "([^"]+)"', src).group(1)
        self.assertEqual(name, self.ROOT_CLASS)
        return [r.replace("${ROOT_CLASS}", name) for r in re.findall(r"`([^`]*)`", m.group(1))]

    def built_rules(self):
        found = [m for m in re.finditer(r"\[((?:`[^`]*`,?)+)\]\.join\(`(?:\\n|\n)`\)([;,)])", self.built()) if "[data-hermes-openui-map]" in m.group(1)]
        self.assertEqual(len(found), 1, "NATIVE_CSS was not found in desktop/plugin.js (did the minifier change its shape?)")
        return [re.sub(r"\$\{[A-Za-z_$][\w$]*\}", self.ROOT_CLASS, r) for r in re.findall(r"`([^`]*)`", found[0].group(1))]

    def test_the_built_widget_root_has_no_max_width_in_any_spelling(self):
        self.assertIsNone(self.ANY_LIMIT.search(self.root_style()), self.root_style())

    def test_the_built_widget_root_fills_and_may_shrink(self):
        style = self.root_style()
        self.assertIn('width:"100%"', style)
        self.assertIn("minWidth:0", style)

    def test_the_source_has_no_column_cap_left(self):
        src = self.source()
        self.assertFalse("MAX_COLUMN_WIDTH" in src, "plugin.jsx still defines a column cap")
        self.assertIsNone(re.search(r"\b640\b", src), "plugin.jsx names 640 in code")

    def test_every_limit_in_the_source_is_a_known_native_only_one(self):
        src = self.source()
        values = [m.group(1) for m in self.LIMIT_VALUE.finditer(src)]
        self.assertEqual(len(self.ANY_LIMIT.findall(src)), len(values), "a max-width / maxWidth is written in a form this test cannot read")
        self.assertTrue(values, "no limit found: the pie and map rules are gone, or this test reads the wrong file")
        self.assertLessEqual(set(values), self.ALLOWED_LIMITS, "an unexpected max-width in plugin.jsx: %s" % values)

    def test_the_built_stylesheet_is_the_one_in_the_source(self):
        rules = self.source_rules()
        self.assertTrue(rules)
        self.assertEqual(self.built_rules(), rules)

    def test_the_built_stylesheet_has_only_the_known_limits(self):
        limits = [m.group(1) for r in self.built_rules() for m in self.LIMIT_VALUE.finditer(r)]
        self.assertEqual(sorted(limits), ["720px", "960px"])

    def test_svg_text_can_be_selected_in_native_mode(self):
        # the app's own sheet has `img,picture,video,canvas,svg{user-select:none}`; this rule is more specific, so it wins
        rule = ".%s svg{user-select:text}" % self.ROOT_CLASS
        self.assertIn(rule, self.source_rules())
        self.assertIn(rule, self.built_rules())

    def test_the_widget_does_not_inherit_the_apps_message_text_rules(self):
        self.assertIn(".%s{overflow-wrap:normal}" % self.ROOT_CLASS, self.built_rules())
        self.assertIsNotNone(re.search(r'className:[^{}]*not-prose[^{}]*"data-hermes-openui-widget"', self.built()), "the built widget root lost not-prose")


@unittest.skipUnless(shutil.which("node") and (ROOT / "build" / "node_modules" / "esbuild").exists(), "needs Node and `npm ci` in build/")
class DesktopHalf(unittest.TestCase):
    def test_app_loader_accepts_the_bundle(self):
        r = subprocess.run(["node", "tests/plugin-loader-check.mjs"], cwd=str(ROOT / "build"), capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("a real parser still finds after the rewrite: none", r.stdout)


if __name__ == "__main__":
    unittest.main()
