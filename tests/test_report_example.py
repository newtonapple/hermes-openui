"""The documented example report must export cleanly: it is what the docs screenshot and the export guide show."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402

export = helpers.sub("export")
ROOT = helpers.ROOT


class ExampleReport(unittest.TestCase):
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

    def params(self):
        return json.loads((ROOT / "examples" / "reports" / "platform-status.json").read_text(encoding="utf-8"))

    def test_the_platform_report_exports_with_no_pack_linked(self):
        r = json.loads(export.export_widgets(self.params(), settings={}))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["sections"], 3)
        self.assertEqual(sorted(r["packs"]), ["charts", "infra", "text"])  # InfraMap is built in; no custom pack is needed
        html = Path(r["path"]).read_text(encoding="utf-8")
        self.assertEqual(html.count('<div class="mount"></div>'), 3)

    def test_a_link_that_names_a_label_is_reported_with_its_section_and_the_right_id(self):
        params = self.params()
        old = 'InfraLink("browsers", "cdn", "HTTPS")'
        self.assertIn(old, params["sections"][0]["source"])
        params["sections"][0]["source"] = params["sections"][0]["source"].replace(old, 'InfraLink("browsers", "CDN", "HTTPS")')
        r = json.loads(export.export_widgets(params, settings={}))
        self.assertFalse(r["ok"])
        self.assertTrue(any("Section 1" in e and "InfraMap" in e and "`CDN` is a label; the id is `cdn`" in e for e in r["errors"]), r)

    def test_no_example_names_a_real_stack(self):
        text = (ROOT / "examples" / "reports" / "platform-status.json").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?i)litellm|vllm|dgx|spark-?\d|qwen|homelab|tailnet|onlygens")


if __name__ == "__main__":
    unittest.main()
