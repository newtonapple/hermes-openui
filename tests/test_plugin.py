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

    def test_registers_exactly_the_declared_tool(self):
        names = [t["name"] for t in self.ctx.tools]
        self.assertEqual(names, ["render_widget"])
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
        for word in ("chart", "graph", "plot", "diagram", "flowchart", "dashboard", "table", "map", "dag", "schema", "topology", "widget", "kpi", "pie", "bar"):
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

    def test_bundled_skill_is_registered_and_has_frontmatter(self):
        self.assertEqual([n for n, _ in self.ctx.skills], ["openui-render"])
        text = self.ctx.skills[0][1].read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: openui-render\n"))
        self.assertLess(len(text), 4000, "loaded in full each time the skill is used")

    def test_a_hermes_without_register_skill_still_gets_the_tool(self):
        class Old(FakeCtx):
            def register_skill(self, *a, **k):
                raise AttributeError("no register_skill")

        ctx = Old()
        helpers.load().register(ctx)
        self.assertEqual(len(ctx.tools), 1)


@unittest.skipUnless(shutil.which("node") and (ROOT / "build" / "node_modules" / "esbuild").exists(), "needs Node and `npm ci` in build/")
class DesktopHalf(unittest.TestCase):
    def test_app_loader_accepts_the_bundle(self):
        r = subprocess.run(["node", "tests/plugin-loader-check.mjs"], cwd=str(ROOT / "build"), capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("a real parser still finds after the rewrite: none", r.stdout)


if __name__ == "__main__":
    unittest.main()
