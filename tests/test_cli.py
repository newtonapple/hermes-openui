"""`hermes openui ...`: manage linked component packs from the terminal."""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402
from test_packs import BODY, FakeCtx, pack_text  # noqa: E402

cli = helpers.sub("cli")
bundle = helpers.sub("bundle")
tools = helpers.sub("tools")
HAS_NODE = bool(shutil.which("node")) and bundle.VALIDATOR.is_file()


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p


class ComponentsList(Tmp):
    def test_nothing_linked_says_how_to_link(self):
        code, text = cli.components_list({})
        self.assertEqual(code, 0)
        self.assertIn("components", text)
        self.assertIn("No component packs", text)

    def test_lists_each_pack_with_its_components_and_path(self):
        p = self.write("demo.js", pack_text())
        code, text = cli.components_list({"components": [str(p)]})
        self.assertEqual(code, 0, text)
        self.assertIn("demo", text)
        self.assertIn("DemoBadge", text)
        self.assertIn(str(p), text)

    def test_problems_are_shown_and_make_the_exit_code_nonzero(self):
        good = self.write("demo.js", pack_text())
        code, text = cli.components_list({"components": [str(good), str(self.dir / "missing.js")]})
        self.assertEqual(code, 1)
        self.assertIn("missing.js", text)
        self.assertIn("DemoBadge", text)  # the good pack is still listed


class ComponentsCheck(Tmp):
    def test_a_good_pack_passes(self):
        p = self.write("demo.js", pack_text())
        code, text = cli.components_check([str(p)])
        self.assertEqual(code, 0, text)
        self.assertIn("OK", text)

    def test_a_pack_with_a_forbidden_api_fails_and_says_why(self):
        p = self.write("bad.js", pack_text(body="(function(){ fetch('https://x.example'); })();\n"))
        code, text = cli.components_check([str(p)])
        self.assertEqual(code, 1)
        self.assertIn("fetch", text)

    def test_a_missing_header_fails(self):
        p = self.write("bare.js", "(function(){})();\n")
        code, text = cli.components_check([str(p)])
        self.assertEqual(code, 1)
        self.assertIn("hermes-openui-pack", text)

    @unittest.skipUnless(HAS_NODE, "needs Node and assets/validate.cjs")
    def test_a_header_that_disagrees_with_the_script_fails_through_the_real_validator(self):
        p = self.write("lies.js", pack_text(comps={"DemoBadge": "DemoBadge(text: string)", "Ghost": "Ghost()"}))
        code, text = cli.components_check([str(p)])
        self.assertEqual(code, 1, text)
        self.assertIn("Ghost", text)

    @unittest.skipUnless(HAS_NODE, "needs Node and assets/validate.cjs")
    def test_a_script_that_throws_on_load_fails(self):
        p = self.write("boom.js", pack_text(body="(function(){ throw new Error('kaboom'); })();\n"))
        code, text = cli.components_check([str(p)])
        self.assertEqual(code, 1, text)
        self.assertIn("kaboom", text)

    def test_without_node_it_says_what_it_could_not_check(self):
        p = self.write("demo.js", pack_text())
        real = cli.tools._node_validate
        cli.tools._node_validate = lambda *a, **k: None
        try:
            code, text = cli.components_check([str(p)])
        finally:
            cli.tools._node_validate = real
        self.assertEqual(code, 0, text)
        self.assertIn("Node", text)

    def test_no_paths_is_an_error(self):
        code, text = cli.components_check([])
        self.assertEqual(code, 2)


class WithHome(Tmp):
    def setUp(self):
        super().setUp()
        self._old = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(self.dir / "home")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._old
        super().tearDown()

    def widget(self, text="hi", name="w"):
        r = json.loads(tools.render_widget({"source": 'root = Stack([t])\nt = Text("%s")' % text, "name": name}, mode="preview"))
        self.assertTrue(r["ok"], r)
        return Path(r["directive"].split('file="')[1].rstrip('"}')).name


class WidgetsList(WithHome):
    def test_empty_home(self):
        code, text = cli.widgets_list()
        self.assertEqual(code, 0)
        self.assertIn("No widgets", text)

    def test_newest_first_with_the_name_to_pass_to_export(self):
        old = self.widget("old", "first")
        os.utime(Path(os.environ["HERMES_HOME"]) / "widgets" / old, (time.time() - 3600, time.time() - 3600))
        new = self.widget("new", "second")
        code, text = cli.widgets_list()
        self.assertEqual(code, 0)
        self.assertLess(text.index(new[:-5]), text.index(old[:-5]))
        self.assertIn(new[:-5], text)  # the stem is what export_widgets takes


class ExportCommand(WithHome):
    def test_exports_named_widgets_to_the_path(self):
        a, b = self.widget("alpha", "a"), self.widget("beta", "b")
        out = self.dir / "out" / "report.html"
        code, text = cli.export_command([a[:-5], b[:-5]], title="Two", out=str(out), overwrite=False, theme="auto", settings={})
        self.assertEqual(code, 0, text)
        self.assertTrue(out.is_file())
        self.assertIn(str(out), text)
        html = out.read_text(encoding="utf-8")
        self.assertIn("<title>Two</title>", html)
        self.assertEqual(html.count('<div class="mount"></div>'), 2, "one mount point per exported widget")

    def test_defaults_go_to_the_exports_folder(self):
        a = self.widget("alpha", "a")
        code, text = cli.export_command([a[:-5]], title=None, out=None, overwrite=False, theme="auto", settings={})
        self.assertEqual(code, 0, text)
        self.assertIn(str(Path(os.environ["HERMES_HOME"]) / "exports"), text.replace("/private", ""))

    def test_an_unknown_widget_is_an_error_with_a_hint(self):
        code, text = cli.export_command(["nope-123456"], title=None, out=str(self.dir / "r.html"), overwrite=False, theme="auto", settings={})
        self.assertEqual(code, 1)
        self.assertIn("nope-123456", text)

    def test_a_protected_destination_is_refused(self):
        a = self.widget("alpha", "a")
        code, text = cli.export_command([a[:-5]], title=None, out="/etc/r.html", overwrite=False, theme="auto", settings={})
        self.assertEqual(code, 1)
        self.assertIn("protected", text)
        self.assertFalse(Path("/etc/r.html").exists())

    def test_an_existing_file_needs_overwrite(self):
        a = self.widget("alpha", "a")
        out = self.dir / "r.html"
        out.write_text("keep me")
        code, text = cli.export_command([a[:-5]], title=None, out=str(out), overwrite=False, theme="auto", settings={})
        self.assertEqual(code, 1)
        self.assertEqual(out.read_text(), "keep me")
        code, _ = cli.export_command([a[:-5]], title=None, out=str(out), overwrite=True, theme="auto", settings={})
        self.assertEqual(code, 0)
        self.assertNotEqual(out.read_text(), "keep me")


class Wiring(unittest.TestCase):
    def test_register_adds_one_openui_command(self):
        calls = []

        class Ctx(FakeCtx):
            def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
                calls.append((name, setup_fn, handler_fn))

        helpers.load().register(Ctx())
        self.assertEqual([c[0] for c in calls], ["openui"])

    def test_an_older_hermes_without_register_cli_command_still_registers_the_tool(self):
        ctx = FakeCtx()
        helpers.load().register(ctx)  # FakeCtx has no register_cli_command
        self.assertTrue(any(t["name"] == "render_widget" for t in ctx.tools))

    def test_the_parser_accepts_the_documented_commands(self):
        parser = argparse.ArgumentParser(prog="hermes openui")
        cli.setup_parser(parser)
        self.assertEqual(parser.parse_args(["components", "list"]).components_cmd, "list")
        self.assertEqual(parser.parse_args(["components", "check", "a.js", "b.js"]).paths, ["a.js", "b.js"])
        a = parser.parse_args(["export", "w1", "w2", "--title", "T", "--out", "/x/r.html", "--overwrite", "--theme", "dark"])
        self.assertEqual((a.widgets, a.title, a.out, a.overwrite, a.theme), (["w1", "w2"], "T", "/x/r.html", True, "dark"))
        self.assertEqual(parser.parse_args(["widgets"]).openui_cmd, "widgets")

    def test_handle_dispatches_and_returns_an_exit_code(self):
        parser = argparse.ArgumentParser(prog="hermes openui")
        cli.setup_parser(parser)
        self.assertEqual(cli.handle(parser.parse_args(["components", "list"]), {}), 0)

    def test_handle_with_no_subcommand_prints_help_and_succeeds(self):
        parser = argparse.ArgumentParser(prog="hermes openui")
        cli.setup_parser(parser)
        self.assertEqual(cli.handle(parser.parse_args([]), {}, out=lambda s: None), 0)


if __name__ == "__main__":
    unittest.main()
