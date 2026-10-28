"""The pack-authoring guide's example must actually work: extract it from the markdown and run it through the real loader and validator."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402

packs = helpers.sub("packs")
bundle = helpers.sub("bundle")
tools = helpers.sub("tools")
DOC = (helpers.ROOT / "docs" / "custom-components.md").read_text(encoding="utf-8")
HAS_NODE = bool(shutil.which("node")) and bundle.VALIDATOR.is_file()


def js_blocks():
    return re.findall(r"```js\n(.*?)```", DOC, re.S)


class GuideExample(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        blocks = [b for b in js_blocks() if b.lstrip().startswith("/* hermes-openui-pack")]
        self.assertTrue(blocks, "the guide has no complete example pack")
        self.path = Path(self.tmp.name) / "badges.js"
        self.path.write_text(blocks[0], encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_example_pack_loads_with_no_problems(self):
        found, problems = packs.load([str(self.path)], bundle.component_names())
        self.assertEqual(problems, [])
        self.assertEqual([p.name for p in found], ["badges"])
        self.assertEqual(list(found[0].components), ["StatusPill"])

    @unittest.skipUnless(HAS_NODE, "needs Node and assets/validate.cjs")
    def test_the_example_pack_passes_the_real_validator_and_enforces_its_schema(self):
        found, _ = packs.load([str(self.path)], bundle.component_names())
        good = 'root = Stack([a, b])\na = StatusPill("Postgres up", "ok")\nb = StatusPill("Queue slow")'
        self.assertEqual(tools._node_validate(good, found), [])
        bad = tools._node_validate('root = Stack([a])\na = StatusPill("x", "purple")', found)
        self.assertTrue(bad, "an invalid tone must be rejected by the zod enum")

    def test_every_forbidden_api_the_guide_lists_is_really_refused(self):
        listed = re.search(r"\| Forbidden \| (.*?) \|", DOC)
        assert listed is not None
        names = re.findall(r"`([^`]+)`", listed.group(1))
        self.assertGreaterEqual(len(names), 8)
        for name in names:
            with self.subTest(api=name):
                body = "(function(){ %s; })();" % (name if name.endswith("(") is False else name + ")")
                if name == "new Function":
                    body = "(function(){ new Function('return 1'); })();"
                text = '/* hermes-openui-pack\n{"api":1,"name":"x","components":{"Xx":"Xx()"}}\n*/\n' + body
                p = Path(self.tmp.name) / "x.js"
                p.write_text(text, encoding="utf-8")
                found, problems = packs.load([str(p)], set())
                self.assertEqual(found, [], "%s was accepted although the guide says it is forbidden" % name)


EXPORT_DOC = (helpers.ROOT / "docs" / "exporting.md").read_text(encoding="utf-8")
export = helpers.sub("export")


class ExportGuide(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.tmp.name

    def tearDown(self):
        if self._old is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._old
        self.tmp.cleanup()

    def test_the_request_in_the_guide_exports(self):
        blocks = re.findall(r"```json\n(.*?)```", EXPORT_DOC, re.S)
        self.assertTrue(blocks, "the guide has no example request")
        r = json.loads(export.export_widgets(json.loads(blocks[0])))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["sections"], 2)

    def test_every_parameter_the_guide_lists_is_in_the_tool_schema(self):
        schema = helpers.sub("schemas").EXPORT_WIDGETS["parameters"]["properties"]
        listed = re.findall(r"^\| `(\w+)` \|", EXPORT_DOC.split("## What the agent sends")[1].split("A `widget` name")[0], re.M)
        self.assertEqual(sorted(listed), sorted(schema))

    def test_the_documented_limits_match_the_code(self):
        self.assertIn("120 characters", EXPORT_DOC)
        self.assertEqual(export.MAX_TITLE_CHARS, 120)
        self.assertIn("one to 30 sections", EXPORT_DOC.lower())
        self.assertEqual(export.MAX_SECTIONS, 30)
        self.assertIn("8 MB", EXPORT_DOC)
        self.assertEqual(helpers.sub("page").EXPORT_MAX_BYTES, 8 * 1024 * 1024)
        self.assertEqual(export.EXPORT_IMAGE_MAX, 1024 * 1024)

    def test_every_protected_place_the_guide_lists_is_refused(self):
        for place in ("~/.ssh", "~/.aws", "~/.gnupg", "~/.config/gcloud", "~/.kube", "~/.docker", "/etc", "/usr", "/bin", "/sbin", "/System", "/Library", "/private/etc", "/var/root"):
            with self.subTest(place=place):
                self.assertIn(place, EXPORT_DOC)
                self.assertIsNotNone(export.check_destination(os.path.expanduser(place) + "/r.html"), place)


class ExamplePathsInTheDocs(unittest.TestCase):
    """A doc that tells a reader to open or link `examples/...` must name a file that is there. This caught the guides still pointing
    at the user pack after InfraMap became a built-in."""

    PATH = re.compile(r"(?<!components/)examples/[\w/-]+(?:\.[\w-]+)+")  # `docs/ui-components/examples/` is another folder

    def docs(self):
        root = helpers.ROOT
        return [root / "README.md", root / "AGENTS.md", *sorted((root / "docs").glob("*.md"))]

    def test_every_examples_path_the_docs_mention_exists(self):
        missing = []
        for doc in self.docs():
            for path in sorted(set(self.PATH.findall(doc.read_text(encoding="utf-8")))):
                if not (helpers.ROOT / path).exists():
                    missing.append("%s mentions %s" % (doc.name, path))
        self.assertEqual(missing, [])

    def test_the_guard_sees_a_path_inside_a_longer_one(self):
        found = self.PATH.findall("- <home>/plugins/hermes-openui/examples/packs/x.js and `examples/a-b.oui`.")
        self.assertEqual(found, ["examples/packs/x.js", "examples/a-b.oui"])

    def test_the_guard_skips_the_component_docs_examples_folder(self):
        self.assertEqual(self.PATH.findall("see `docs/ui-components/examples/metric-tones.oui`"), [])


if __name__ == "__main__":
    unittest.main()
