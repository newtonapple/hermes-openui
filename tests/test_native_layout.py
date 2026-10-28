"""Opt-in layout check of native mode in headless Chrome: OPENUI_TEST_CHROME=1 python3 -m unittest tests.test_native_layout

It draws the real desktop/plugin.js (stub SDK) at two chat-column widths in ONE Chrome launch and runs the checks of
tools/verify_native.py; a second launch repeats it inside the app's wrapper classes and stylesheet when Hermes Desktop is
installed. It skips when Chrome is missing. It shows how the plugin's output lays out in plain Chrome, not how Hermes Desktop
lays it out.
"""
import contextlib
import importlib.util
import io
import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_driver():
    spec = importlib.util.spec_from_file_location("verify_native", ROOT / "tools" / "verify_native.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_native"] = mod
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless(os.environ.get("OPENUI_TEST_CHROME") == "1", "opt in with OPENUI_TEST_CHROME=1: it launches Chrome")
@unittest.skipUnless(shutil.which("node") and (ROOT / "build" / "node_modules" / "esbuild").exists(), "needs Node and `npm ci` in build/")
class NativeLayout(unittest.TestCase):
    def check(self, *args):
        driver = load_driver()
        if not driver.chrome_available():
            self.skipTest("no Chrome found (set $CHROME)")
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = driver.main(["--widths", "360,1000", *args])
        except SystemExit as e:  # the driver stops the process when node or Chrome fails
            self.fail("the layout check could not run: %s" % e)
        self.assertEqual(code, 0, out.getvalue()[-2000:])
        self.assertIn("0 problem(s)", out.getvalue())

    def test_widgets_fill_wide_columns_and_scroll_in_a_narrow_one(self):
        self.check()

    def test_the_same_with_the_apps_stylesheet_around_the_widget(self):
        if not load_driver().find_app_css():
            self.skipTest("no installed Hermes Desktop stylesheet to draw against")
        self.check("--app-css", "auto")


if __name__ == "__main__":
    unittest.main()
