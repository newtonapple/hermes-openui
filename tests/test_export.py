"""export_widgets: one standalone, offline HTML report written to a user-chosen (or default) place, with a safe destination policy."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402
from test_packs import pack_text  # noqa: E402  (a pack that really registers its component)

schemas = helpers.sub("schemas")
page = helpers.sub("page")
bundle = helpers.sub("bundle")
tools = helpers.sub("tools")
packs = helpers.sub("packs")
export = helpers.sub("export")

HAS_NODE = bool(shutil.which("node")) and bundle.VALIDATOR.is_file()
GOOD = 'root = Stack([t, m])\nt = Text("Cluster", "title")\nm = Metric("GPU", "87%", "+4%", "warn")'
CHART = 'root = Stack([c])\nc = LineChart(["Mon", "Tue"], [Series("tok/s", [10, 12])])'
BTN = 'root = Stack([b])\nb = Button("Retry", @ToAssistant("retry the job"))'
BLOB = re.compile(r'<script data-oui="([^"]+)" type="text/plain">(.*?)</script>', re.S)
PNG = b"\x89PNG\r\n\x1a\n"


def plugin_version():
    return re.search(r"^version:\s*(\S+)", (helpers.ROOT / "plugin.yaml").read_text(encoding="utf-8"), re.M).group(1)


def without_blobs(html):
    return BLOB.sub("", html)


def embedded_sources(html):
    return json.loads(re.search(r'<script id="oui-src" type="application/json">(.*?)</script>', html, re.S).group(1))


def script_by_id(html, ident):
    return re.search(r'<script id="%s">(.*?)</script>' % ident, html, re.S).group(1)


def run_node(script):
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class SchemaWords(unittest.TestCase):
    """Tool Search indexes the description AND the parameter names, so the words people say must be in them."""

    def setUp(self):
        self.s = schemas.EXPORT_WIDGETS
        props = self.s["parameters"]["properties"]
        names = list(props) + list(props["sections"]["items"]["properties"]) + [self.s["name"].replace("_", " ")]
        self.index = set(re.findall(r"[a-z0-9]+", (self.s["description"] + " " + " ".join(names)).lower()))

    def test_name_and_required(self):
        self.assertEqual(self.s["name"], "export_widgets")
        self.assertEqual(self.s["parameters"]["required"], ["sections"])
        self.assertEqual(self.s["parameters"]["type"], "object")

    def test_parameter_names(self):
        props = self.s["parameters"]["properties"]
        self.assertEqual(sorted(props), ["overwrite", "path", "sections", "theme", "title"])
        self.assertEqual(sorted(props["sections"]["items"]["properties"]), ["source", "title", "widget"])
        self.assertEqual(props["theme"]["enum"], ["auto", "light", "dark"])
        self.assertEqual(props["sections"]["type"], "array")
        self.assertEqual(props["sections"]["minItems"], 1)
        self.assertEqual(props["sections"]["maxItems"], 30)

    def test_description_is_short_with_a_short_first_sentence(self):
        d = self.s["description"]
        self.assertLess(len(d), 700)
        self.assertLessEqual(len(d.split(". ")[0]), 60, "Tool Search lists only ~60 characters of the first sentence")
        self.assertLessEqual(len(json.dumps(self.s)), 2600)

    def test_description_carries_the_words_people_say(self):
        for query in ("export html", "save as html", "share a report", "standalone page", "offline report", "export dashboard", "download chart"):
            with self.subTest(query=query):
                missing = [w for w in query.split() if w not in ("a", "as") and w not in self.index]
                self.assertEqual(missing, [])
        text = self.s["description"].lower()
        for phrase in ("openui lang", "already shown in this chat", "single", "offline html"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_description_leaves_render_widgets_keywords_to_render_widget(self):
        # Measured with Hermes's own Tool Search (BM25, stemmed): an export description that repeated render_widget's vocabulary (graph, table,
        # diagram, ...) pushed render_widget out of the top 5 for a bare "graph" or "table" query. These words stay out of it.
        own = {"export", "html", "report", "dashboard", "chart", "offline", "standalone"}
        shared = {"graph", "table", "diagram", "flowchart", "topology", "plot", "pie", "dag", "map", "kpi", "inline", "card", "tab"}
        words = set(re.findall(r"[a-z0-9]+", self.s["description"].lower()))
        self.assertEqual(sorted(words & shared), [])
        self.assertTrue(own <= words)
        self.assertLessEqual(len(re.findall(r"\bwidget\b", self.s["description"].lower())), 1, "'inline widget' queries belong to render_widget")

    def test_render_widget_schema_is_untouched(self):
        props = schemas.RENDER_WIDGET["parameters"]["properties"]
        self.assertEqual(sorted(props), ["name", "reference", "source"])
        self.assertTrue(schemas.RENDER_WIDGET["description"].startswith("Draw charts, graphs, DAG/ER diagrams"))


class InlineImageLimit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.img = Path(self.tmp.name) / "big.png"
        self.img.write_bytes(PNG + b"1" * (300 * 1024))
        self.src = 'root = Stack([i])\ni = Image("%s", "a")' % self.img

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_limit_is_unchanged(self):
        with self.assertRaisesRegex(page.WidgetError, "limit is 100 KB"):
            page.inline_images(self.src)

    def test_a_larger_limit_lets_the_image_through(self):
        out = page.inline_images(self.src, max_bytes=1024 * 1024)
        self.assertIn("data:image/png;base64,", out)

    def test_the_message_states_the_limit_in_force(self):
        with self.assertRaisesRegex(page.WidgetError, "limit is 200 KB"):
            page.inline_images(self.src, max_bytes=200 * 1024)


class ExportPage(unittest.TestCase):
    def assertIn(self, needle, hay, msg=None):  # a failing assertion must not print a multi-hundred-KB page
        if needle not in hay:
            self.fail("%r not found in the page (%d chars)" % (needle, len(hay)))

    def assertNotIn(self, needle, hay, msg=None):
        if needle in hay:
            self.fail("%r unexpectedly found (%d chars)" % (needle, len(hay)))

    SECTIONS = [{"title": "Overview", "source": GOOD}, {"title": None, "source": CHART}]

    def build(self, sections=None, title="Weekly report", **kw):
        return page.build_export_page(sections or self.SECTIONS, title, **kw)

    def test_returns_html_and_the_packs_used(self):
        html, used = self.build()
        self.assertEqual(used, ["charts"])
        self.assertTrue(html.startswith("<!doctype html>"))

    def test_is_self_contained_with_no_external_urls_outside_the_blobs(self):
        html, _ = self.build()
        rest = without_blobs(html)
        self.assertIsNone(re.search(r"https?://|(?:src|href)\s*=\s*[\"']?//|@import|url\(|<link\b", rest), "the template must not reach for the network")
        self.assertNotIn("<script src", rest)

    def test_page_basics(self):
        html, _ = self.build()
        self.assertIn('<html lang="en">', html)
        self.assertIn('<meta charset="utf-8">', html)
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', html)
        self.assertIn("<title>Weekly report</title>", html)
        self.assertIn("<h1>Weekly report</h1>", html)
        self.assertIn("<h2>Overview</h2>", html)
        self.assertEqual(html.count("<h2>"), 1, "an untitled section gets no heading")
        self.assertIn("max-width:960px", html)

    def test_footer_names_the_plugin_version(self):
        html, _ = self.build()
        self.assertIn("Exported from Hermes (hermes-openui %s)" % plugin_version(), html)

    def test_titles_are_escaped(self):
        html, _ = self.build([{"title": "A <b>&</b> B", "source": GOOD}], title='<img src=x onerror="1"> & co')
        rest = without_blobs(html)
        self.assertNotIn("<b>", rest)
        self.assertNotIn("<img", rest)
        self.assertIn("A &lt;b&gt;&amp;&lt;/b&gt; B", html)
        self.assertIn("&lt;img src=x onerror=&quot;1&quot;&gt; &amp; co", html)

    def test_sources_round_trip_and_cannot_close_the_script(self):
        evil = 'root = Stack([a])\na = Text("</script><b>x</b> <!-- ", "body")'
        html, _ = self.build([{"title": "t", "source": evil}, {"title": "u", "source": GOOD}])
        self.assertEqual(embedded_sources(html), [evil, GOOD])
        self.assertNotIn("</script><b>", html)

    def test_one_mount_container_per_section(self):
        html, _ = self.build()
        self.assertEqual(html.count('class="mount"'), 2)

    def test_only_the_packs_the_sources_use_and_each_once(self):
        two_charts = [{"title": "a", "source": CHART}, {"title": "b", "source": CHART.replace("Mon", "Wed")}]
        html, used = self.build(two_charts)
        self.assertEqual(used, ["charts"])
        names = [m.group(1) for m in BLOB.finditer(html)]
        self.assertEqual(names, ["core", "charts"])

    def test_core_only_for_plain_sources(self):
        html, used = self.build([{"title": "a", "source": GOOD}])
        self.assertEqual(used, [])
        self.assertEqual([m.group(1) for m in BLOB.finditer(html)], ["core"])

    def test_sections_mount_through_the_runtime_with_a_per_section_error(self):
        html, _ = self.build()
        boot = html.split("window.HermesOpenUI.mount", 1)
        self.assertEqual(len(boot), 2)
        self.assertIn("catch", boot[1].split("</script>", 1)[0])
        self.assertIn("could not be drawn", html)

    def test_buttons_outside_hermes_get_a_notice_instead_of_failing_silently(self):
        html, _ = self.build()
        self.assertIn("Interactive buttons work inside Hermes only", html)
        shim = script_by_id(html, "oui-hermes-shim")
        self.assertIn("window.hermes", shim)
        self.assertLess(html.index('id="oui-hermes-shim"'), html.index('data-oui="core"'))

    @unittest.skipUnless(HAS_NODE, "Node not available")
    def test_hermes_send_shim_resolves_with_ok_false_and_shows_the_notice(self):
        shim = script_by_id(self.build()[0], "oui-hermes-shim")
        out = run_node(
            "var note={hidden:true};var window={};var document={getElementById:function(){return note}};"
            "var setTimeout=function(){return 1},clearTimeout=function(){};"
            "%s\nwindow.hermes.send('x').then(function(r){console.log(JSON.stringify([r.ok,note.hidden]))})" % shim
        )
        self.assertEqual(json.loads(out), [False, False])

    @unittest.skipUnless(HAS_NODE, "Node not available")
    def test_the_shim_leaves_a_real_hermes_bridge_alone(self):
        shim = script_by_id(self.build()[0], "oui-hermes-shim")
        out = run_node("var window={hermes:{send:function(){return 'real'}}};var document={getElementById:function(){return {}}};%s\nconsole.log(window.hermes.send())" % shim)
        self.assertEqual(out, "real")

    def test_accent_is_a_concrete_colour_because_the_runtime_fallback_is_not_one_in_chrome(self):
        # The runtime falls back to the CSS keyword AccentColor, which Chrome does not support: buttons lose their border and tabs their
        # underline. A standalone page has no host theme to supply --accent, so the page must.
        html, _ = self.build()
        rest = without_blobs(html)
        self.assertNotIn("AccentColor", rest)
        self.assertIn(":root{--accent:#0969da}", rest)
        self.assertIn("@media (prefers-color-scheme:dark){:root{--accent:#5b9cf6}}", rest)
        dark, _ = self.build(theme="dark")
        self.assertIn(":root{--accent:#5b9cf6}", dark)
        self.assertNotIn("prefers-color-scheme:dark){:root", dark)
        light, _ = self.build(theme="light")
        self.assertIn(":root{--accent:#0969da}", light)
        self.assertNotIn("prefers-color-scheme:dark){:root", light)

    def test_print_css(self):
        html, _ = self.build()
        css = html.split("@media print", 1)[1].split("</style>", 1)[0]
        self.assertIn("box-shadow:none", css)
        self.assertRegex(css, r"break-inside:\s*avoid")

    def test_auto_theme_follows_the_viewer(self):
        html, _ = self.build()
        self.assertIn('<meta name="color-scheme" content="light dark">', html)
        self.assertRegex(html, r"html\{color-scheme:light dark[;}]")
        self.assertNotIn("matchMedia", without_blobs(html))

    def test_forced_dark_sets_the_scheme_and_installs_the_media_shim_before_the_runtime(self):
        html, _ = self.build(theme="dark")
        self.assertIn('<meta name="color-scheme" content="dark">', html)
        self.assertRegex(html, r"html\{color-scheme:dark[;}]")
        self.assertLess(html.index("matchMedia"), html.index('data-oui="core"'))
        self.assertLess(html.index("matchMedia"), html.index("window.HermesOpenUI.mount"))

    def test_forced_light(self):
        html, _ = self.build(theme="light")
        self.assertIn('<meta name="color-scheme" content="light">', html)
        self.assertRegex(html, r"html\{color-scheme:light[;}]")

    @unittest.skipUnless(HAS_NODE, "Node not available")
    def test_media_shim_answers_prefers_color_scheme_and_passes_other_queries_through(self):
        for theme, want in (("dark", [True, False, True]), ("light", [False, True, True])):
            with self.subTest(theme=theme):
                shim = script_by_id(self.build(theme=theme)[0], "oui-theme-shim")
                out = run_node(
                    "var window={matchMedia:function(q){return {matches:q==='(min-width: 1px)',media:q}}};%s\n"
                    "var m=function(q){return window.matchMedia(q).matches};"
                    "console.log(JSON.stringify([m('(prefers-color-scheme: dark)'),m('(prefers-color-scheme:light)'),m('(min-width: 1px)')]))" % shim
                )
                self.assertEqual(json.loads(out), want)

    def test_unknown_theme_is_refused(self):
        with self.assertRaises(page.WidgetError):
            self.build(theme="sepia")

    def test_custom_pack_used_by_two_sections_is_embedded_once(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "demo.js"
            f.write_text(pack_text(), encoding="utf-8")
            found, problems = packs.load([str(f)], bundle.component_names())
            self.assertEqual(problems, [])
            src = 'root = Stack([b])\nb = DemoBadge("hi")'
            html, used = self.build([{"title": "a", "source": src}, {"title": "b", "source": src.replace("hi", "yo")}, {"title": "c", "source": GOOD}], extra_packs=found)
        self.assertEqual(used, ["custom:demo"])
        self.assertEqual(html.count('data-oui="custom:demo"'), 1)

    def test_an_unused_custom_pack_is_not_embedded(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "demo.js"
            f.write_text(pack_text(), encoding="utf-8")
            found, _ = packs.load([str(f)], bundle.component_names())
            html, used = self.build(extra_packs=found)
        self.assertNotIn("custom:demo", html)
        self.assertEqual(used, ["charts"])

    def test_over_the_size_cap_is_a_helpful_error(self):
        big = 'root = Stack([a])\na = Text("%s", "body")' % ("x" * (3 * 1024 * 1024))
        with self.assertRaisesRegex(page.WidgetError, r"8 MB.*(smaller images|fewer sections)"):
            self.build([{"title": str(i), "source": big} for i in range(3)])

    def test_just_under_the_cap_builds(self):
        big = 'root = Stack([a])\na = Text("%s", "body")' % ("x" * (2 * 1024 * 1024))
        html, _ = self.build([{"title": str(i), "source": big} for i in range(3)])
        self.assertLess(len(html.encode("utf-8")), page.EXPORT_MAX_BYTES)


# --------------------------------------------------------------------------------------------------------------------
# The tool: sections, widgets, destination policy
# --------------------------------------------------------------------------------------------------------------------


def fake_guard(denied=None, approval=None, boom=False):
    """A stand-in for Hermes's `agent.file_safety`: refuses paths under `denied`, asks approval under `approval`."""
    agent = types.ModuleType("agent")
    agent.__path__ = []
    fs = types.ModuleType("agent.file_safety")

    def get_write_denied_error(path, **kw):
        if boom:
            raise RuntimeError("guard is broken")
        return "Refusing to write to a protected path: %s" % path if denied and str(path).startswith(str(denied)) else None

    def is_write_approval_required(path):
        if boom:
            raise RuntimeError("guard is broken")
        return bool(approval) and str(path).startswith(str(approval))

    fs.get_write_denied_error = get_write_denied_error
    fs.is_write_approval_required = is_write_approval_required
    agent.file_safety = fs
    return mock.patch.dict(sys.modules, {"agent": agent, "agent.file_safety": fs})


def no_guard():
    """`from agent.file_safety import ...` raises ImportError, even on a machine where Hermes itself is importable."""
    return mock.patch.dict(sys.modules, {"agent.file_safety": None})


class WithHome(unittest.TestCase):
    """An isolated profile: HERMES_HOME and HOME are temp folders, and Hermes's own guard is absent unless a test injects one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.hermes = self.root / "hermes"
        self.home = self.root / "home"
        self.hermes.mkdir()
        self.home.mkdir()
        self.exports = self.hermes / "exports"
        self.widgets = self.hermes / "widgets"
        patcher = mock.patch.dict(os.environ, {"HERMES_HOME": str(self.hermes), "HOME": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        g = no_guard()
        g.start()
        self.addCleanup(g.stop)
        self.addCleanup(self.tmp.cleanup)

    def call(self, settings=None, **params):
        return json.loads(export.export_widgets(params, settings=settings))

    def exported(self):
        return sorted(p for p in self.root.rglob("*") if p.suffix in (".html", ".htm") or p.name.endswith(".tmp"))

    def render(self, source, name="w", mode="preview"):
        r = json.loads(tools.render_widget({"source": source, "name": name}, mode=mode))
        self.assertTrue(r["ok"], r)
        return Path(re.search(r'file="([^"]+)"', r["directive"]).group(1))

    def page_of(self, result):
        return Path(result["path"]).read_text(encoding="utf-8")


class ArtifactSignals(WithHome):
    """Hermes has no artifacts folder: the Desktop's Artifacts view and the messaging gateways read what a tool result and a reply
    carry. A strong result key plus a `MEDIA:` line makes the export a downloadable, previewable file card, and a native attachment
    on messaging platforms. A refused export must carry none of it."""

    def test_the_result_names_the_file_as_an_artifact(self):
        r = self.call(sections=[{"source": GOOD}])
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["artifact_path"], r["path"])
        self.assertEqual(r["media_tag"], "MEDIA:" + r["path"])

    def test_the_artifact_is_an_html_file_the_desktop_and_gateway_deliver(self):
        r = self.call(sections=[{"source": GOOD}], path=str(self.home / "report.html"))
        self.assertTrue(r["media_tag"].endswith(".html"))

    def test_the_instruction_tells_the_agent_to_put_the_tag_on_its_own_line(self):
        r = self.call(sections=[{"source": GOOD}])
        nxt = r["next"]
        self.assertIn("media_tag", nxt)
        self.assertIn("own line", nxt)
        self.assertIn("backticks", nxt)  # Hermes does not deliver a tag inside inline code
        self.assertIn("do not paste", nxt.lower())

    def test_a_path_with_spaces_stays_one_tag(self):
        folder = self.home / "My Reports"
        r = self.call(sections=[{"source": GOOD}], path=str(folder))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["media_tag"], "MEDIA:" + r["path"])
        self.assertIn("My Reports", r["media_tag"])

    def test_a_refused_export_carries_no_artifact_keys(self):
        for params in ({"sections": [{"source": "root = Stack([x])"}]}, {"sections": [{"source": GOOD}], "path": "/etc/r.html"}, {"sections": []}):
            with self.subTest(params=params):
                r = self.call(**params)
                self.assertFalse(r["ok"])
                for key in ("artifact_path", "media_tag", "path"):
                    self.assertNotIn(key, r)

    def test_the_plain_path_key_is_still_there_for_the_cli(self):
        r = self.call(sections=[{"source": GOOD}])
        self.assertTrue(Path(r["path"]).is_file())


class SectionRules(WithHome):
    def test_happy_path_writes_the_default_exports_folder(self):
        r = self.call(sections=[{"title": "Overview", "source": GOOD}, {"title": "Trend", "source": CHART}])
        self.assertTrue(r["ok"], r)
        path = Path(r["path"])
        self.assertEqual(path.parent, self.exports)
        self.assertRegex(path.name, r"^hermes-report-[0-9a-f]{6}\.html$")
        self.assertEqual(r["bytes"], path.stat().st_size)
        self.assertEqual(r["sections"], 2)
        self.assertEqual(r["packs"], ["charts"])
        self.assertIn(r["checked"], ("node", "structural"))
        self.assertIn("media_tag", r["next"])
        self.assertIn("offline", r["next"])
        self.assertTrue(path.read_text(encoding="utf-8").startswith("<!doctype html>"))
        self.assertEqual(self.exported(), [path])

    def test_title_names_the_page_and_the_file(self):
        r = self.call(title="Q3 GPU costs & more", sections=[{"source": GOOD}])
        self.assertTrue(r["ok"], r)
        self.assertRegex(Path(r["path"]).name, r"^q3-gpu-costs-more-[0-9a-f]{6}\.html$")
        html = self.page_of(r)
        self.assertIn("<title>Q3 GPU costs &amp; more</title>", html)

    def test_a_title_with_no_usable_letters_still_gets_a_readable_name(self):
        r = self.call(title="///", sections=[{"source": GOOD}])
        self.assertRegex(Path(r["path"]).name, r"^report-[0-9a-f]{6}\.html$")

    def test_same_title_twice_never_collides(self):
        a = self.call(title="Same", sections=[{"source": GOOD}])["path"]
        b = self.call(title="Same", sections=[{"source": GOOD}])["path"]
        self.assertNotEqual(a, b)

    def test_export_dir_setting_replaces_the_default_folder(self):
        r = self.call(settings={"export_dir": str(self.root / "reports")}, sections=[{"source": GOOD}])
        self.assertEqual(Path(r["path"]).parent, self.root / "reports")
        self.assertFalse(self.exports.exists())

    def test_export_dir_setting_expands_the_tilde(self):
        r = self.call(settings={"export_dir": "~/Reports"}, sections=[{"source": GOOD}])
        self.assertEqual(Path(r["path"]).parent, self.home / "Reports")

    def test_fenced_source_is_accepted(self):
        self.assertTrue(self.call(sections=[{"source": "```\n%s\n```" % GOOD}])["ok"])

    def test_bad_shapes_are_refused_and_write_nothing(self):
        cases = [
            {},
            {"sections": []},
            {"sections": "nope"},
            {"sections": [GOOD]},
            {"sections": [{"title": "only a title"}]},
            {"sections": [{"source": GOOD, "widget": "x"}]},
            {"sections": [{"source": "  "}]},
            {"sections": [{"source": 5}]},
            {"sections": [{"source": GOOD, "title": 5}]},
            {"sections": [{"source": GOOD}] * 31},
        ]
        for params in cases:
            with self.subTest(params=str(params)[:60]):
                r = self.call(**params)
                self.assertFalse(r["ok"], r)
                self.assertTrue(r["errors"])
                self.assertIn("Nothing was written", r["fix"])
        self.assertEqual(self.exported(), [])
        self.assertFalse(self.exports.exists(), "a refused call must not even create the default folder")

    def test_thirty_sections_is_allowed(self):
        r = self.call(sections=[{"source": GOOD}] * 30)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["sections"], 30)

    def test_both_source_and_widget_names_the_section(self):
        r = self.call(sections=[{"source": GOOD}, {"title": "Both", "source": GOOD, "widget": "x"}])
        self.assertTrue(r["errors"][0].startswith('Section 2 ("Both"): '), r)
        self.assertIn("exactly one", r["errors"][0])

    def test_a_non_dict_or_none_params_is_a_clean_error(self):
        for params in (None, "x", 5, []):
            r = json.loads(export.export_widgets(params))
            self.assertFalse(r["ok"])

    def test_sections_given_as_a_json_string_are_understood(self):
        r = self.call(sections=json.dumps([{"title": "a", "source": GOOD}]))
        self.assertTrue(r["ok"], r)

    def test_unknown_theme_is_refused(self):
        r = self.call(sections=[{"source": GOOD}], theme="sepia")
        self.assertFalse(r["ok"])
        self.assertIn("theme", r["errors"][0])

    def test_theme_is_applied(self):
        r = self.call(sections=[{"source": GOOD}], theme="dark")
        html = self.page_of(r)
        self.assertIn('<meta name="color-scheme" content="dark">', html)
        self.assertIn('id="oui-theme-shim"', html)

    def test_pack_problems_become_warnings_not_failures(self):
        r = self.call(settings={"components": [str(self.root / "missing.js")]}, sections=[{"source": GOOD}])
        self.assertTrue(r["ok"], r)
        self.assertTrue(r.get("pack_warnings"), r)


class ValidationNamesTheSection(WithHome):
    BAD = 'root = Stack([a])\na = Text("x")\nlost = Text("y")'

    def test_titled_section(self):
        r = self.call(sections=[{"title": "Fine", "source": GOOD}, {"title": "GPU load", "source": self.BAD}])
        self.assertFalse(r["ok"])
        self.assertTrue(r["errors"][0].startswith('Section 2 ("GPU load"): '), r)
        self.assertIn("not reachable", r["errors"][0])
        self.assertEqual(self.exported(), [])

    def test_untitled_section(self):
        r = self.call(sections=[{"source": self.BAD}])
        self.assertTrue(r["errors"][0].startswith("Section 1: "), r)

    def test_every_bad_section_is_reported_in_one_call(self):
        r = self.call(sections=[{"title": "A", "source": self.BAD}, {"source": GOOD}, {"title": "C", "source": self.BAD}])
        starts = [e.split(":")[0] for e in r["errors"]]
        self.assertIn('Section 1 ("A")', starts)
        self.assertIn('Section 3 ("C")', starts)
        self.assertNotIn("Section 2", " ".join(starts))

    def test_unknown_component_is_named_with_its_section(self):
        r = self.call(sections=[{"title": "Nope", "source": 'root = Stack([a])\na = Bogus("x")'}])
        self.assertTrue(r["errors"][0].startswith('Section 1 ("Nope"): '), r)
        self.assertIn("Bogus", r["errors"][0])

    @unittest.skipUnless(HAS_NODE, "Node not available")
    def test_the_real_parser_errors_name_the_section_too(self):
        r = self.call(sections=[{"source": GOOD}, {"title": "Typed", "source": "root = Stack([m])\nm = Metric(1, 2)"}])
        self.assertFalse(r["ok"])
        self.assertTrue(r["errors"][0].startswith('Section 2 ("Typed"): '), r)

    @unittest.skipUnless(HAS_NODE, "Node not available")
    def test_checked_by_node(self):
        self.assertEqual(self.call(sections=[{"source": GOOD}])["checked"], "node")

    def test_a_huge_source_is_refused_with_the_section_named(self):
        r = self.call(sections=[{"title": "Big", "source": "x" * (tools.MAX_SOURCE_CHARS + 1)}])
        self.assertTrue(r["errors"][0].startswith('Section 1 ("Big"): '), r)


class WidgetSections(WithHome):
    def test_source_is_recovered_from_the_html_widget_file(self):
        src = 'root = Stack([t])\nt = Text("a < b </script> & \\"quoted\\" \u00e9", "body")\n'
        path = self.render(src, name="gpu status")
        self.assertEqual(export.widget_source(path.name), src)
        self.assertEqual(export.widget_source(path.stem), src)

    def test_source_is_recovered_from_a_native_oui_file(self):
        path = self.render(CHART, name="native one", mode="native")
        self.assertEqual(path.suffix, ".oui")
        self.assertEqual(export.widget_source(path.stem), lint_stripped(CHART))
        self.assertEqual(export.widget_source(path.name), lint_stripped(CHART))

    def test_a_widget_section_is_exported_with_the_same_source(self):
        path = self.render(CHART, name="chart")
        r = self.call(sections=[{"title": "Earlier", "widget": path.stem}])
        self.assertTrue(r["ok"], r)
        self.assertEqual(embedded_sources(self.page_of(r)), [lint_stripped(CHART)])
        self.assertEqual(r["packs"], ["charts"])

    def test_mixed_sections_keep_their_order(self):
        w1 = self.render(CHART, name="one")
        w2 = self.render(GOOD, name="two", mode="native")
        r = self.call(sections=[{"widget": w1.name}, {"source": GOOD}, {"widget": w2.stem}])
        self.assertTrue(r["ok"], r)
        self.assertEqual(embedded_sources(self.page_of(r)), [lint_stripped(CHART), lint_stripped(GOOD), lint_stripped(GOOD)])

    def test_a_widget_with_an_inlined_image_survives(self):
        img = self.root / "p.png"
        img.write_bytes(PNG + b"1" * 64)
        path = self.render('root = Stack([i])\ni = Image("%s", "a")' % img, name="img")
        r = self.call(sections=[{"widget": path.stem}])
        self.assertTrue(r["ok"], r)
        self.assertIn("data:image/png;base64,", self.page_of(r))

    def test_unknown_widget_names_the_section_and_lists_recent_ones(self):
        path = self.render(GOOD, name="known")
        r = self.call(sections=[{"source": GOOD}, {"title": "Old", "widget": "nothing-here-abc123"}])
        self.assertFalse(r["ok"])
        self.assertTrue(r["errors"][0].startswith('Section 2 ("Old"): '), r)
        self.assertIn("not found", r["errors"][0])
        self.assertIn(path.stem, r["errors"][0])

    def test_only_plain_file_names_are_accepted(self):
        self.render(GOOD, name="real")
        outside = self.root / "secret.html"
        outside.write_text("<script id=\"oui-src\" type=\"application/json\">\"root = Stack([])\"</script>", encoding="utf-8")
        bad = ["../secret.html", "../../etc/passwd", "a/b.html", "/etc/passwd", str(outside), "..", ".", "", "  ", "a..b.html", "..hidden", "x\\y", "..\\secret", "a\x00b.html", "~/x.html", "name.txt", "secret.sh", 5, None, ["a"]]
        for name in bad:
            with self.subTest(name=name):
                r = self.call(sections=[{"widget": name}])
                self.assertFalse(r["ok"], r)
                self.assertTrue(r["errors"][0].startswith("Section 1"), r)
        self.assertFalse(self.exports.exists())
        self.assertEqual([p for p in self.exported() if p.parent not in (self.widgets, self.root)], [])

    def test_a_double_dot_is_refused_as_a_name_even_when_such_a_file_exists(self):
        self.render(GOOD)
        (self.widgets / "dots..x-abc123.oui").write_text(GOOD, encoding="utf-8")
        for name in ("dots..x-abc123", "dots..x-abc123.oui"):
            with self.subTest(name=name):
                r = self.call(sections=[{"widget": name}])
                self.assertFalse(r["ok"], r)
                self.assertIn("plain file name", r["errors"][0])

    def test_a_symlink_in_the_widgets_folder_cannot_read_outside_it(self):
        self.render(GOOD)
        secret = self.root / "outside.oui"
        secret.write_text(GOOD, encoding="utf-8")
        link = self.widgets / "sneaky.oui"
        link.symlink_to(secret)
        r = self.call(sections=[{"widget": "sneaky"}])
        self.assertFalse(r["ok"], r)
        self.assertIn("not found", r["errors"][0])

    def test_a_page_that_is_not_a_widget_is_a_clean_error(self):
        self.render(GOOD)
        (self.widgets / "plain-abc123.html").write_text("<html><body>hi</body></html>", encoding="utf-8")
        r = self.call(sections=[{"widget": "plain-abc123"}])
        self.assertFalse(r["ok"])
        self.assertIn("not a widget", r["errors"][0])

    def test_widgets_are_looked_up_in_this_profiles_folder_only(self):
        other = self.root / "other-profile" / "widgets"
        other.mkdir(parents=True)
        (other / "theirs-abc123.oui").write_text(GOOD, encoding="utf-8")
        self.assertFalse(self.call(sections=[{"widget": "theirs-abc123"}])["ok"])

    def test_every_problem_is_its_own_error_entry(self):
        r = self.call(sections=[{"widget": "../a"}, {"title": "B", "widget": "../b"}, {"source": GOOD}])
        self.assertEqual(len(r["errors"]), 2)
        self.assertTrue(r["errors"][0].startswith("Section 1 (widget ../a): "))
        self.assertTrue(r["errors"][1].startswith('Section 2 ("B"): '))

    def test_widget_source_error_type(self):
        with self.assertRaises(export.ExportError):
            export.widget_source("../x")


def lint_stripped(src):
    """What render_widget stores: the source with fences and surrounding blank lines removed, one trailing newline."""
    return helpers.sub("lint").strip_fences(src)


class Images(WithHome):
    def make(self, size, name="big.png"):
        p = self.root / name
        p.write_bytes(PNG + b"1" * size)
        return p

    def src(self, img):
        return 'root = Stack([i])\ni = Image("%s", "a")' % img

    def test_an_image_over_100kb_is_allowed_in_an_export(self):
        img = self.make(300 * 1024)
        r = self.call(sections=[{"source": self.src(img)}])
        self.assertTrue(r["ok"], r)
        self.assertGreater(r["bytes"], 300 * 1024)
        self.assertIn("data:image/png;base64,", self.page_of(r))

    def test_the_same_image_is_still_rejected_by_render_widget(self):
        img = self.make(300 * 1024)
        r = json.loads(tools.render_widget({"source": self.src(img)}, mode="preview"))
        self.assertFalse(r["ok"])
        self.assertIn("limit is 100 KB", r["errors"][0])

    def test_an_image_over_1mb_is_rejected_with_the_section_named(self):
        img = self.make(1100 * 1024)
        r = self.call(sections=[{"source": GOOD}, {"title": "Photo", "source": self.src(img)}])
        self.assertFalse(r["ok"])
        self.assertTrue(r["errors"][0].startswith('Section 2 ("Photo"): '), r)
        self.assertIn("limit is 1024 KB", r["errors"][0])
        self.assertEqual(self.exported(), [])

    def test_a_missing_image_names_the_section(self):
        r = self.call(sections=[{"title": "Gone", "source": self.src(self.root / "nope.png")}])
        self.assertTrue(r["errors"][0].startswith('Section 1 ("Gone"): '), r)
        self.assertIn("not found", r["errors"][0])

    def test_the_page_size_cap_is_reported_and_nothing_is_written(self):
        img = self.make(1000 * 1000)
        r = self.call(sections=[{"title": "Photo %d" % i, "source": self.src(img)} for i in range(7)])
        self.assertFalse(r["ok"])
        self.assertIn("8 MB", r["errors"][0])
        self.assertEqual(self.exported(), [])


class CustomPacks(WithHome):
    SRC = 'root = Stack([b])\nb = DemoBadge("hi")'

    def link(self):
        f = self.root / "demo.js"
        f.write_text(pack_text(), encoding="utf-8")
        return {"components": [str(f)]}

    def test_a_pack_used_by_two_sections_is_embedded_once(self):
        r = self.call(settings=self.link(), sections=[{"title": "a", "source": self.SRC}, {"title": "b", "source": self.SRC.replace("hi", "yo")}, {"source": CHART}])
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["packs"], ["charts", "custom:demo"])
        html = self.page_of(r)
        self.assertEqual(html.count('data-oui="custom:demo"'), 1)
        self.assertEqual(html.count('data-oui="charts"'), 1)

    def test_unlinked_custom_component_is_an_unknown_component_in_that_section(self):
        r = self.call(sections=[{"source": GOOD}, {"title": "Badge", "source": self.SRC}])
        self.assertFalse(r["ok"])
        self.assertTrue(r["errors"][0].startswith('Section 2 ("Badge"): '), r)
        self.assertIn("DemoBadge", r["errors"][0])


class Destination(WithHome):
    def ok(self, **kw):
        r = self.call(sections=[{"source": GOOD}], **kw)
        self.assertTrue(r["ok"], r)
        return Path(r["path"])

    def refused(self, **kw):
        r = self.call(sections=[{"source": GOOD}], **kw)
        self.assertFalse(r["ok"], r)
        self.assertIn("Nothing was written", r["fix"])
        return " ".join(r["errors"])

    def test_explicit_file_path_creates_missing_folders(self):
        target = self.home / "Reports" / "2026" / "gpu.html"
        self.assertEqual(self.ok(path=str(target)), target)
        self.assertTrue(target.read_text(encoding="utf-8").startswith("<!doctype html>"))

    def test_htm_and_uppercase_extensions_are_accepted(self):
        for name in ("a.htm", "b.HTML"):
            with self.subTest(name=name):
                self.assertEqual(self.ok(path=str(self.home / name)), self.home / name)

    def test_existing_folder_gets_a_readable_name(self):
        folder = self.home / "Documents"
        folder.mkdir()
        p = self.ok(path=str(folder), title="Weekly GPU report")
        self.assertEqual(p.parent, folder)
        self.assertRegex(p.name, r"^weekly-gpu-report-[0-9a-f]{6}\.html$")

    def test_new_folder_is_created_after_the_checks(self):
        folder = self.home / "Brand" / "New"
        p = self.ok(path=str(folder))
        self.assertEqual(p.parent, folder)

    def test_trailing_slash_means_folder_even_with_a_dot_in_the_name(self):
        p = self.ok(path=str(self.home / "v1.2") + "/")
        self.assertEqual(p.parent, self.home / "v1.2")

    def test_tilde_is_expanded(self):
        self.assertEqual(self.ok(path="~/Desktop/r.html"), self.home / "Desktop" / "r.html")

    def test_relative_path_is_refused(self):
        for path in ("report.html", "./report.html", "reports/r.html", "..\\r.html"):
            with self.subTest(path=path):
                self.assertIn("absolute", self.refused(path=path))
        self.assertEqual(self.exported(), [])

    def test_wrong_extension_is_refused(self):
        for name in ("report.txt", "report.pdf", "notes.py", "report.html.sh", "report.md"):
            with self.subTest(name=name):
                self.assertIn(".html", self.refused(path=str(self.home / name)))
        self.assertEqual(list(self.home.glob("report*")), [])

    def test_an_existing_non_html_file_is_never_touched(self):
        f = self.home / "keep.txt"
        f.write_text("mine", encoding="utf-8")
        self.refused(path=str(f), overwrite=True)
        self.assertEqual(f.read_text(encoding="utf-8"), "mine")

    def test_a_folder_named_like_a_page_is_refused(self):
        d = self.home / "oops.html"
        d.mkdir()
        self.assertIn("folder", self.refused(path=str(d), overwrite=True))

    def test_existing_file_is_refused_without_overwrite_and_left_alone(self):
        f = self.home / "r.html"
        f.write_text("old", encoding="utf-8")
        self.assertIn("overwrite", self.refused(path=str(f)))
        self.assertEqual(f.read_text(encoding="utf-8"), "old")

    def test_overwrite_true_replaces_it(self):
        f = self.home / "r.html"
        f.write_text("old", encoding="utf-8")
        self.assertEqual(self.ok(path=str(f), overwrite=True), f)
        self.assertTrue(f.read_text(encoding="utf-8").startswith("<!doctype html>"))

    def test_overwrite_given_as_a_string_true_is_understood(self):
        f = self.home / "r.html"
        f.write_text("old", encoding="utf-8")
        self.ok(path=str(f), overwrite="true")
        self.assertNotEqual(f.read_text(encoding="utf-8"), "old")

    def test_no_temp_files_are_left_behind(self):
        self.ok(path=str(self.home / "r.html"))
        self.ok()
        self.assertEqual([p for p in self.root.rglob("*") if p.name.endswith(".tmp")], [])

    def test_dot_dot_is_normalised_before_the_checks(self):
        ssh = self.home / ".ssh"
        ssh.mkdir()
        msg = self.refused(path=str(self.home / "Documents" / ".." / ".ssh" / "r.html"))
        self.assertIn("protected", msg)
        self.assertEqual(list(ssh.iterdir()), [])

    def test_a_denied_path_is_refused_with_the_guards_text_and_creates_no_folders(self):
        denied = self.root / "denied"
        denied.mkdir()
        with fake_guard(denied=denied):
            msg = self.refused(path=str(denied / "deep" / "er" / "r.html"))
        self.assertIn("Refusing to write to a protected path", msg)
        self.assertEqual(list(denied.iterdir()), [])

    def test_a_path_needing_approval_is_refused_and_explained(self):
        area = self.root / "needs-approval"
        area.mkdir()
        with fake_guard(approval=area):
            msg = self.refused(path=str(area / "r.html"))
        self.assertIn("approval", msg)
        self.assertIn("normal folder", msg)
        self.assertEqual(list(area.iterdir()), [])

    def test_a_symlink_into_a_denied_folder_is_followed_before_checking(self):
        denied = self.root / "denied"
        denied.mkdir()
        safe = self.root / "safe"
        safe.mkdir()
        (safe / "link").symlink_to(denied, target_is_directory=True)
        with fake_guard(denied=os.path.realpath(str(denied))):
            self.refused(path=str(safe / "link" / "r.html"))
            self.refused(path=str(safe / "link" / "newdir") + "/")
        self.assertEqual(list(denied.iterdir()), [])

    def test_a_symlink_into_a_protected_folder_is_refused_without_the_guard_too(self):
        ssh = self.home / ".ssh"
        ssh.mkdir()
        (self.home / "innocent").symlink_to(ssh, target_is_directory=True)
        self.refused(path=str(self.home / "innocent" / "r.html"))
        self.assertEqual(list(ssh.iterdir()), [])

    def test_a_symlinked_default_exports_folder_cannot_reach_a_protected_one(self):
        ssh = self.home / ".ssh"
        ssh.mkdir()
        self.exports.symlink_to(ssh, target_is_directory=True)
        r = self.call(sections=[{"source": GOOD}])
        self.assertFalse(r["ok"], r)
        self.assertEqual(list(ssh.iterdir()), [])

    def test_a_dangling_symlink_target_is_checked_where_it_points(self):
        ssh = self.home / ".ssh"
        ssh.mkdir()
        (self.home / "r.html").symlink_to(ssh / "authorized.html")
        self.refused(path=str(self.home / "r.html"), overwrite=True)
        self.assertEqual(list(ssh.iterdir()), [])


class CheckDestinationFallback(WithHome):
    """Without Hermes's own guard (`agent.file_safety` not importable) a conservative built-in denylist applies."""

    def denied(self, path):
        msg = export.check_destination(str(path))
        self.assertIsNotNone(msg, "%s should be refused" % path)
        self.assertIn("protected", msg)

    def test_credential_folders_under_home(self):
        for rel in (".ssh", ".aws", ".gnupg", ".config/gcloud", ".kube", ".docker"):
            with self.subTest(rel=rel):
                self.denied(self.home / rel / "r.html")
                self.denied(self.home / rel / "sub" / "deeper" / "r.html")

    def test_case_insensitive_file_systems(self):
        self.denied(self.home / ".SSH" / "r.html")
        self.denied(self.home / ".Config" / "GCloud" / "r.html")

    def test_hermes_home_secrets_and_code(self):
        for rel in (".env", "auth.json", "config.yaml", "plugins/x/r.html", "skills/x/r.html", "sessions/r.html", "plugins", "skills"):
            with self.subTest(rel=rel):
                self.denied(self.hermes / rel)

    def test_other_profiles_of_the_default_hermes_root(self):
        self.denied(self.home / ".hermes" / "plugins" / "r.html")
        self.denied(self.home / ".hermes" / "profiles" / "work" / "skills" / "r.html")
        self.denied(self.home / ".hermes" / "profiles" / "work" / "config.yaml")

    def test_system_roots(self):
        for root in ("/etc", "/usr", "/bin", "/sbin", "/System", "/Library", "/private/etc", "/var/root"):
            with self.subTest(root=root):
                self.denied(root + "/r.html")
                self.denied(root + "/a/b/r.html")

    def test_normal_places_are_fine(self):
        for p in (self.home / "Documents" / "r.html", self.home / "Desktop" / "r.html", self.hermes / "exports" / "r.html", self.hermes / "widgets" / "r.html", self.root / "any" / "r.html",
                  self.home / ".sshfoo" / "r.html", self.home / "ssh" / "r.html", self.home / ".config" / "other" / "r.html", self.hermes / "pluginsx" / "r.html", "/tmp/r.html", "/usr2/r.html"):
            with self.subTest(path=str(p)):
                self.assertIsNone(export.check_destination(str(p)))

    def test_nothing_is_created_by_checking(self):
        export.check_destination(str(self.home / "a" / "b" / "r.html"))
        self.assertEqual(list(self.home.iterdir()), [])

    def test_a_broken_guard_falls_back_to_the_denylist(self):
        with fake_guard(boom=True):
            self.denied(self.home / ".ssh" / "r.html")
            self.assertIsNone(export.check_destination(str(self.home / "ok" / "r.html")))


class CheckDestinationWithGuard(WithHome):
    def test_denied_text_is_returned_verbatim(self):
        with fake_guard(denied="/guarded"):
            self.assertEqual(export.check_destination("/guarded/r.html"), "Refusing to write to a protected path: /guarded/r.html")

    def test_approval_required_is_refused_and_explained(self):
        with fake_guard(approval="/needs-ok"):
            msg = export.check_destination("/needs-ok/r.html")
        self.assertIn("approval", msg)
        self.assertIn("normal folder", msg)
        self.assertIn("file tools", msg)

    def test_allowed_path_passes(self):
        with fake_guard(denied="/guarded", approval="/needs-ok"):
            self.assertIsNone(export.check_destination(str(self.home / "r.html")))

    def test_the_builtin_list_applies_on_top_of_the_guard(self):
        # Hermes's own guard allows ~/.hermes/plugins, skills, auth.json and /etc (measured against the real module). An exported
        # page has no business in them, so the built-in list refuses them even when the guard has no objection.
        with fake_guard():
            for p in (self.home / ".ssh" / "r.html", self.hermes / "plugins" / "x" / "r.html", self.hermes / "auth.json", "/etc/r.html"):
                with self.subTest(path=str(p)):
                    msg = export.check_destination(str(p))
                    self.assertIsNotNone(msg, "%s should be refused" % p)
                    self.assertIn("protected", msg)

    def test_a_folder_both_agree_on_is_allowed(self):
        with fake_guard():
            self.assertIsNone(export.check_destination(str(self.home / "Documents" / "r.html")))


class ShootHtmlMode(unittest.TestCase):
    """tools/shoot.py --html: argument handling and the offline-proof summary (Chrome itself is exercised by the visual check)."""

    @classmethod
    def setUpClass(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location("shoot_cli", helpers.ROOT / "tools" / "shoot.py")
        cls.shoot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.shoot)

    def parse(self, *argv):
        return self.shoot.parse_args(list(argv))

    def refuses(self, *argv):
        import contextlib
        import io

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.parse(*argv)

    def test_html_mode_takes_a_file_and_one_output(self):
        a = self.parse("--html", "report.html", "out.png", "--theme", "light")
        self.assertEqual((a.html, a.paths, a.theme, a.width), ("report.html", ["out.png"], "light", 1100))

    def test_html_mode_defaults_to_auto_theme_and_accepts_dark(self):
        self.assertEqual(self.parse("--html", "r.html", "o.png").theme, "auto")
        self.assertEqual(self.parse("--html", "r.html", "o.png", "--theme", "dark", "--width", "700").width, 700)

    def test_example_mode_is_unchanged(self):
        a = self.parse("ex.oui", "out.png")
        self.assertEqual((a.html, a.paths, a.theme, a.width, a.scale), (None, ["ex.oui", "out.png"], "dark", 640, 2))
        b = self.parse("ex.oui", "out.png", "--theme", "light", "--pack", "p.js", "--keep-html")
        self.assertEqual((b.theme, b.pack, b.keep_html), ("light", ["p.js"], True))

    def test_wrong_argument_shapes_are_refused(self):
        self.refuses("--html", "r.html")
        self.refuses("--html", "r.html", "a.png", "b.png")
        self.refuses("ex.oui")
        self.refuses("ex.oui", "o.png", "--theme", "auto")
        self.refuses("ex.oui", "o.png", "--eval", "1")
        self.refuses("--html", "r.html", "o.png", "--pack", "p.js")

    def test_problem_summary_separates_errors_failures_and_outside_requests(self):
        events = [
            {"method": "Runtime.exceptionThrown", "params": {"exceptionDetails": {"text": "Uncaught", "exception": {"description": "TypeError: x"}}}},
            {"method": "Runtime.consoleAPICalled", "params": {"type": "warning", "args": [{"value": "just a warning"}]}},
            {"method": "Runtime.consoleAPICalled", "params": {"type": "error", "args": [{"value": "boom"}]}},
            {"method": "Network.loadingFailed", "params": {"errorText": "net::ERR_INTERNET_DISCONNECTED"}},
            {"method": "Network.requestWillBeSent", "params": {"request": {"url": "file:///tmp/r.html"}}},
            {"method": "Network.requestWillBeSent", "params": {"request": {"url": "data:image/png;base64,AA"}}},
            {"method": "Network.requestWillBeSent", "params": {"request": {"url": "https://cdn.example.com/x.js"}}},
        ]
        p = self.shoot.page_problems(events)
        self.assertEqual(p["console_errors"], ["TypeError: x", "boom"])
        self.assertEqual(p["failed_requests"], ["net::ERR_INTERNET_DISCONNECTED"])
        self.assertEqual(p["outside_requests"], ["https://cdn.example.com/x.js"])

    def test_a_missing_file_is_a_clean_exit(self):
        with self.assertRaises(SystemExit):
            self.shoot.shoot_html(Path("/nonexistent/none.html"), Path("/tmp/none.png"))


if __name__ == "__main__":
    unittest.main()
