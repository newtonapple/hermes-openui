import base64
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402

page = helpers.sub("page")
bundle = helpers.sub("bundle")

DASH = 'root = Stack([t, m])\nt = Text("Hi", "title")\nm = Metric("GPU", "87%")'
CHART = 'root = Stack([c])\nc = LineChart(["a", "b"], [Series("s", [1, 2])])'


class PackSelection(unittest.TestCase):
    def test_core_only(self):
        self.assertEqual(page.select_packs(DASH), [])

    def test_chart_pulls_charts_pack(self):
        self.assertEqual(page.select_packs(CHART), ["charts"])

    def test_each_pack(self):
        cases = {
            "diagrams": 'root = Stack([d])\nd = Dag([DagNode("a","A")], [])',
            "map": 'root = Stack([m])\nm = GeoMap([GeoPoint("x", 1, 2)])',
            "text": 'root = Stack([m])\nm = Markdown("# hi")',
        }
        for pack, src in cases.items():
            with self.subTest(pack=pack):
                self.assertEqual(page.select_packs(src), [pack])

    def test_component_names_inside_strings_are_ignored(self):
        self.assertEqual(page.select_packs('root = Stack([a])\na = Text("LineChart( and Dag(", "body")'), [])

    def test_action_steps_are_not_components(self):
        self.assertEqual(page.select_packs('root = Stack([b])\nb = Button("Go", @ToAssistant("x"))'), [])

    def test_everything_flag(self):
        self.assertEqual(page.select_packs(DASH, everything=True), sorted(bundle.manifest()["packs"]))


class BuildPage(unittest.TestCase):
    def test_core_only_page(self):
        html, packs = page.build_page(DASH)
        self.assertEqual(packs, [])
        self.assertIn('data-oui="core"', html)
        self.assertNotIn('data-oui="charts"', html)
        self.assertLess(len(html.encode()), page.SAFE_BUDGET)

    def test_chart_page_embeds_only_charts(self):
        html, packs = page.build_page(CHART)
        self.assertEqual(packs, ["charts"])
        self.assertIn('data-oui="charts"', html)
        self.assertNotIn('data-oui="map"', html)

    def test_source_cannot_close_the_script_tag(self):
        html, _ = page.build_page('root = Stack([a])\na = Text("</script><b>x</b>", "body")')
        body = html.split('id="oui-src"', 1)[1].split("</script>", 1)[0]
        self.assertNotIn("<", body)

    def test_over_budget_is_refused_with_pack_costs(self):
        big = 'root = Stack([a])\na = Text("%s", "body")' % ("x" * 400_000)
        with self.assertRaises(page.WidgetError) as cm:
            page.build_page(big)
        self.assertIn("480 KB", str(cm.exception))


class Images(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def src(self, path):
        return 'root = Stack([i])\ni = Image("%s", "alt")' % path

    def test_png_is_inlined(self):
        p = self.dir / "a.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
        out = page.inline_images(self.src(p))
        self.assertIn("data:image/png;base64,", out)
        self.assertIn(base64.b64encode(p.read_bytes()).decode()[:20], out)

    def test_remote_and_data_uris_are_left_alone(self):
        for u in ("https://example.com/a.png", "data:image/png;base64,AAAA"):
            with self.subTest(u=u):
                self.assertEqual(page.inline_images(self.src(u)), self.src(u))

    def test_relative_path_is_refused(self):
        with self.assertRaises(page.WidgetError):
            page.inline_images(self.src("pic.png"))

    def test_non_image_extension_is_refused(self):
        p = self.dir / "secret.txt"
        p.write_text("nope")
        with self.assertRaises(page.WidgetError) as cm:
            page.inline_images(self.src(p))
        self.assertIn("Unsupported image type", str(cm.exception))

    def test_missing_file(self):
        with self.assertRaises(page.WidgetError):
            page.inline_images(self.src(self.dir / "nope.png"))

    def test_oversize_image(self):
        p = self.dir / "big.png"
        p.write_bytes(b"0" * (page.IMAGE_MAX + 1))
        with self.assertRaises(page.WidgetError) as cm:
            page.inline_images(self.src(p))
        self.assertIn("limit is 100 KB", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
