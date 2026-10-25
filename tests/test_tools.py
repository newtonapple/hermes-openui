import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402

tools = helpers.sub("tools")
bundle = helpers.sub("bundle")

GOOD = 'root = Stack([t, m])\nt = Text("Cluster", "title")\nm = Metric("GPU", "87%", "+4%", "warn")'
CHART = 'root = Stack([c])\nc = LineChart(["Mon", "Tue"], [Series("tok/s", [10, 12])])'
HAS_NODE = bool(shutil.which("node")) and bundle.VALIDATOR.is_file()


class WithHome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.tmp.name
        self.widgets = Path(self.tmp.name) / "widgets"

    def tearDown(self):
        if self._old is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._old
        self.tmp.cleanup()

    def files(self):
        return sorted(p.name for p in self.widgets.glob("*")) if self.widgets.exists() else []

    def call(self, **params):
        mode = params.pop("_mode", "preview")
        return json.loads(tools.render_widget(params, mode=mode))


class Reference(WithHome):
    def test_reference_flag(self):
        r = self.call(reference=True)
        self.assertTrue(r["ok"])
        self.assertIn("Stack(", r["reference"])
        self.assertIn("LineChart(", r["reference"])

    def test_no_source_returns_the_reference_instead_of_failing(self):
        self.assertIn("reference", self.call())
        self.assertIn("reference", self.call(source="   "))

    def test_reference_writes_nothing(self):
        self.call(reference=True)
        self.assertEqual(self.files(), [])


class Preview(WithHome):
    def test_happy_path(self):
        r = self.call(source=GOOD, name="gpu status")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["mode"], "preview")
        self.assertEqual(r["packs"], [])
        self.assertIn(r["checked"], ("node", "structural"))
        path = Path(r["directive"].split('"')[1])
        self.assertTrue(r["directive"].startswith('::preview{file="'))
        self.assertTrue(path.is_file() and path.suffix == ".html")
        self.assertEqual(path.parent, self.widgets)
        self.assertTrue(path.name.startswith("gpu-status-"))
        self.assertEqual(r["bytes"], path.stat().st_size)

    def test_chart_source_reports_its_pack(self):
        self.assertEqual(self.call(source=CHART)["packs"], ["charts"])

    def test_fenced_source_is_accepted(self):
        self.assertTrue(self.call(source="```\n%s\n```" % GOOD)["ok"])

    def test_same_name_never_overwrites(self):
        a = self.call(source=GOOD, name="x")["directive"]
        b = self.call(source=GOOD, name="x")["directive"]
        self.assertNotEqual(a, b)
        self.assertEqual(len(self.files()), 2)

    def test_name_cannot_escape_the_widgets_dir(self):
        r = self.call(source=GOOD, name="../../../etc/passwd")
        path = Path(r["directive"].split('"')[1])
        self.assertEqual(path.parent, self.widgets)
        self.assertNotIn("..", path.name)

    def test_bad_source_writes_nothing_and_explains(self):
        r = self.call(source='root = Stack([a])\na = Text("x")\nlost = Text("y")')
        self.assertFalse(r["ok"])
        self.assertTrue(any("not reachable" in e for e in r["errors"]))
        self.assertEqual(self.files(), [])

    def test_image_is_inlined(self):
        png = Path(self.tmp.name) / "p.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"1" * 64)
        r = self.call(source='root = Stack([i])\ni = Image("%s", "a")' % png)
        self.assertTrue(r["ok"], r)
        html = Path(r["directive"].split('"')[1]).read_text(encoding="utf-8")
        self.assertIn("data:image/png;base64,", html)
        self.assertNotIn(str(png), html)

    def test_bad_image_is_a_clean_error(self):
        r = self.call(source='root = Stack([i])\ni = Image("/nope/missing.png", "a")')
        self.assertFalse(r["ok"])
        self.assertIn("not found", r["errors"][0])
        self.assertEqual(self.files(), [])


class Native(WithHome):
    def test_writes_oui_and_returns_the_openui_directive(self):
        r = self.call(source=CHART, _mode="native")
        self.assertTrue(r["ok"], r)
        path = Path(r["directive"].split('"')[1])
        self.assertTrue(r["directive"].startswith('::openui{file="'))
        self.assertEqual(path.suffix, ".oui")
        self.assertIn("LineChart(", path.read_text(encoding="utf-8"))
        self.assertEqual(r["packs"], [])  # the desktop half carries the runtime
        self.assertLess(r["bytes"], 4096)


@unittest.skipUnless(HAS_NODE, "Node not available")
class NodeValidator(WithHome):
    def test_type_error_is_caught_only_by_the_real_parser(self):
        r = self.call(source='root = Stack([m])\nm = Metric(1, 2)')
        self.assertFalse(r["ok"])
        self.assertEqual(self.files(), [])

    def test_mismatched_chart_arrays(self):
        r = self.call(source='root = Stack([c])\nc = LineChart(["a","b","c"], [Series("s", [1, 2])])')
        self.assertFalse(r["ok"])
        self.assertTrue(any("parallel" in e or "values" in e for e in r["errors"]), r)

    def test_checked_by_node(self):
        self.assertEqual(self.call(source=GOOD)["checked"], "node")


class Robustness(WithHome):
    def test_non_dict_params(self):
        self.assertIn("reference", json.loads(tools.render_widget(None)))

    def test_non_string_source(self):
        self.assertIn("reference", self.call(source=5))

    def test_huge_source_is_refused(self):
        r = self.call(source="x" * (tools.MAX_SOURCE_CHARS + 1))
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
