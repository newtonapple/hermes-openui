"""Shipped files describe no private setup.

The checks name no one. They look for what a private setup leaves behind: an address, a URL, a host name with a common
top-level domain, a `.ts.net` host, a numbered spark host. Public product names (the words in `helpers.PRODUCT_WORDS`) are
not secret, but a public fixture still has no reason to use them.
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402

# The owner's own domain, built from two parts so that this file does not hold the word itself.
OWNER = re.compile("only" + "gens", re.I)
SKIP_DIRS = {".git", "node_modules", "__pycache__", "dist"}
SCANNED = ("tests", "skills", "docs", "examples", "scripts", "tools", "build/src", "build/scripts", "build/tests", "assets", "desktop")
TOP_LEVEL_NAMES = ("LICENSE",)
SKIPPED_SUFFIXES = (".png", ".jpg", ".pyc", ".woff", ".woff2", ".gz")


def shipped_text_files():
    top = [p for p in sorted(helpers.ROOT.iterdir()) if p.is_file() and (p.suffix in (".md", ".py", ".yaml", ".yml", ".json", ".txt") or p.name in TOP_LEVEL_NAMES)]
    found = list(top)
    for name in SCANNED:
        for p in sorted((helpers.ROOT / name).rglob("*")):
            if p.is_file() and not (set(p.parts) & SKIP_DIRS) and p.suffix not in SKIPPED_SUFFIXES:
                found.append(p)
    return found


class Owner(unittest.TestCase):
    def test_no_shipped_text_file_holds_the_owner_domain(self):
        hits = [p.relative_to(helpers.ROOT).as_posix() for p in shipped_text_files() if OWNER.search(p.read_text(encoding="utf-8", errors="ignore"))]
        self.assertEqual(hits, [], "tests are published with the plugin; use the generic detector in helpers.py instead of a name")

    def test_the_tests_folder_itself_is_scanned(self):
        names = {p.relative_to(helpers.ROOT).as_posix() for p in shipped_text_files()}
        self.assertIn("tests/test_hygiene.py", names)
        self.assertIn("tests/test_infra_builtin.py", names)
        self.assertIn("tests/test_report_example.py", names)

    def test_the_built_source_the_bundled_assets_the_desktop_file_and_the_licence_are_scanned_too(self):
        names = {p.relative_to(helpers.ROOT).as_posix() for p in shipped_text_files()}
        for expected in ("build/src/theme.js", "assets/components.md", "assets/validate.cjs", "desktop/plugin.js", "LICENSE"):
            with self.subTest(file=expected):
                self.assertTrue(expected in names, "not scanned: " + expected)
        self.assertFalse([n for n in names if n.endswith(".gz")], "compressed bundles are skipped")
        self.assertFalse([n for n in names if "node_modules" in n.split("/")])


class Detector(unittest.TestCase):
    BAD = {
        "llm.example.com": "a host name with a common top-level domain",
        "api.team.io": "a host name",
        "https://status": "a URL",
        "10.0.0.5": "an IPv4 address",
        "box.tail1234.ts.net": "a `.ts.net` host",
        "spark-1": "a numbered spark host",
        "vllm": "a public product word",
    }
    GOOD = (
        "Postgres",
        "web-1",
        "Load balancer",
        "plugins.entries.hermes-openui.settings.components",
        "config.yaml",
        "hermes-openui",
        "Capabilities > Plugins > hermes-openui",
        "window.__HM.register",
    )

    def test_it_flags_each_kind_of_private_detail(self):
        for text, why in self.BAD.items():
            with self.subTest(text=text, why=why):
                self.assertTrue(helpers.private_setup_hits("a node called %s" % text), why)

    def test_it_leaves_ordinary_words_alone(self):
        for text in self.GOOD:
            with self.subTest(text=text):
                self.assertEqual(helpers.private_setup_hits(text), [])

    def test_a_fixture_that_names_a_host_is_caught_the_way_the_infra_test_catches_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.oui"
            bad.write_text('root = InfraMap([zone])\nzone = InfraZone("Core", [n])\nn = InfraNode("llm", "LLM gateway", "service", "llm.example.com")\n', encoding="utf-8")
            hits = helpers.private_setup_hits(bad.read_text(encoding="utf-8"))
        self.assertIn("llm.example.com", hits)

    def test_the_public_fixtures_and_the_example_report_pass_the_same_check(self):
        scanned = 0
        for folder in ("tests/fixtures", "examples/reports"):
            for p in sorted((helpers.ROOT / folder).rglob("*")):
                if p.is_file() and p.suffix in (".oui", ".json"):
                    scanned += 1
                    with self.subTest(file=p.relative_to(helpers.ROOT).as_posix()):
                        self.assertEqual(helpers.private_setup_hits(p.read_text(encoding="utf-8")), [])
        self.assertGreater(scanned, 3)

    def test_the_native_harness_sample_widget_passes_the_same_check(self):
        # It is a Python string, so the file scan above never sees it.
        sys.path.insert(0, str(helpers.ROOT / "tools"))
        try:
            import verify_native  # pyright: ignore[reportMissingImports] (path added above)
        finally:
            sys.path.remove(str(helpers.ROOT / "tools"))
        self.assertEqual(helpers.private_setup_hits(verify_native.BUTTON_AND_CHOICE), [])


if __name__ == "__main__":
    unittest.main()
