"""The bundled `custom-components` skill teaches an agent to write, link and reload a pack.

These tests keep it honest in four ways.
* Shape and style: size cap, frontmatter, headings, no dashes, no private details.
* Wording: the sentences the lead's rulings require are pinned in a table below. The exact strings are on purpose, so a
  rewrite cannot drop one quietly.
* Facts: each claim the skill makes about the plugin is run against the real loader, CLI, Node validator and tool.
* The template and the argument examples are extracted from the skill and run through the loader, the validator and a real
  Chrome render (skipped, with the reason, when there is no Chrome or Node).
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402

ROOT = helpers.ROOT
SKILL = ROOT / "skills" / "custom-components" / "SKILL.md"
MAX_CHARS = 8000
CONFIG_KEY = "plugins.entries.hermes-openui.settings.components"

packs = helpers.sub("packs")
bundle = helpers.sub("bundle")
cli = helpers.sub("cli")
tools = helpers.sub("tools")
export = helpers.sub("export")
schemas = helpers.sub("schemas")
HAS_NODE = bool(shutil.which("node")) and bundle.VALIDATOR.is_file()
HAS_HERMES = bool(shutil.which("hermes"))
NODE_ENV = dict(os.environ, DO_NOT_TRACK="1", OPENUI_TELEMETRY_DISABLED="1")


def raw():
    return SKILL.read_bytes().decode("utf-8")


def body():
    return re.split(r"\n---\n", raw(), maxsplit=1)[1]


def fences(lang):
    return re.findall(r"```%s\n(.*?)```" % lang, raw(), re.S)


def prose():
    """The words a reader reads: no frontmatter, no fenced code, no inline code."""
    text = re.sub(r"```.*?```", "", body(), flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def frontmatter():
    m = re.match(r"---\n(.*?)\n---\n", raw(), re.S)
    assert m, "no frontmatter"
    return dict(line.split(": ", 1) for line in m.group(1).splitlines())


def section(title):
    return body().split("## " + title, 1)[1].split("\n## ", 1)[0]


def step(n):
    steps = re.split(r"(?m)^(?=\d+\. )", section("Procedure"))[1:]
    return steps[n - 1]


def template():
    blocks = [b for b in fences("js") if b.lstrip().startswith("/* hermes-openui-pack")]
    assert len(blocks) == 1, "the skill carries exactly one complete pack"
    return blocks[0]


def helpers_version():
    m = re.search(r"(?m)^version:\s*[\"']?([^\"'\n]+?)[\"']?\s*$", (ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    return m.group(1)


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def chrome_missing_reason():
    import importlib.util

    spec = importlib.util.spec_from_file_location("shoot_for_test", ROOT / "tools" / "shoot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        mod.find_chrome(None)
    except SystemExit as e:
        return str(e)
    return None


def pack_source(slug, comp, props, body_js, register_extra=""):
    """A small pack for a test. Only the `@@` tokens are replaced, so JavaScript with `%` and braces is safe."""
    text = (
        '/* hermes-openui-pack\n{"api": 1, "name": "@@SLUG@@", "components": {"@@COMP@@": "@@COMP@@(n: number). Test."}}\n*/\n'
        "(function () {\n  var mods = window.__HM.mods;\n  var h = mods.react.createElement, z = mods.zod.z;\n"
        '  var defineComponent = mods["@openuidev/react-lang"].defineComponent;\n'
        '  var C = defineComponent({ name: "@@COMP@@", description: "Test.", props: @@PROPS@@, component: function (ctx) { @@BODY@@ } });\n'
        '  window.__HM.register({ name: "@@SLUG@@", components: [C]@@EXTRA@@ });\n})();\n'
    )
    for token, value in (("@@SLUG@@", slug), ("@@COMP@@", comp), ("@@PROPS@@", props), ("@@BODY@@", body_js), ("@@EXTRA@@", register_extra)):
        text = text.replace(token, value)
    return text


class Tmp(unittest.TestCase):
    """A temp folder and a throwaway HERMES_HOME, so nothing a test renders lands in a real home."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._old_home = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(self.dir / "home")

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._old_home
        self.tmp.cleanup()

    def write(self, name, text):
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def render(self, source, *pack_paths, mode="preview"):
        return json.loads(tools.render_widget({"source": source}, mode=mode, settings={"components": [str(p) for p in pack_paths]}))


class Shape(unittest.TestCase):
    def test_frontmatter_starts_at_byte_zero_and_names_the_skill(self):
        self.assertTrue(SKILL.read_bytes().startswith(b"---\nname: custom-components\n"))
        fm = frontmatter()
        self.assertEqual(fm["name"], "custom-components")
        self.assertEqual(fm["version"], helpers_version())

    def test_description_is_one_short_sentence(self):
        desc = frontmatter()["description"].strip("\"'")
        self.assertLessEqual(len(desc), 80)
        self.assertEqual(desc.count(". "), 0, "one sentence only")

    def test_the_whole_file_stays_within_the_size_cap(self):
        self.assertLessEqual(len(raw()), MAX_CHARS, "the skill is loaded in full each time it is used")

    def test_sections_come_in_the_agreed_order(self):
        heads = re.findall(r"(?m)^## (.+)$", body())
        self.assertEqual(heads, ["When to use", "Procedure", "Template", "Rules", "Pitfalls", "Verification", "Making it built in (maintainers)"])

    def test_the_procedure_has_seven_steps_that_each_end_in_a_check(self):
        steps = re.split(r"(?m)^(?=\d+\. )", section("Procedure"))[1:]
        self.assertEqual([s.split(".", 1)[0] for s in steps], [str(i) for i in range(1, 8)])
        for s in steps:
            with self.subTest(step=s[:30]):
                self.assertIn("Done when", s)


class Style(unittest.TestCase):
    def test_no_docs_path_and_no_machine_local_path(self):
        text = raw()
        self.assertNotRegex(text, r"docs/", "the docs folder is not copied by scripts/install.sh")
        for bad in ("/Users/", "/home/", "/tmp/", "/private/", "~/", "C:\\"):
            with self.subTest(path=bad):
                self.assertNotIn(bad, text)

    def test_no_dash_characters(self):
        text = raw()
        for ch in ("\u2012", "\u2013", "\u2014", "\u2015", "\u2212"):
            with self.subTest(char=hex(ord(ch))):
                self.assertNotIn(ch, text)
        self.assertNotIn(" -- ", text)
        self.assertNotRegex(prose(), r"\w - \w", "a spaced hyphen is a dash in disguise")

    def test_no_private_setup_details_and_no_filler_words(self):
        self.assertEqual(helpers.private_setup_hits(raw()), [], "a skill is published: no host, address or product that identifies a real setup")
        text = raw().lower()
        for word in ("serves as", "seamless", "powerful", "robust", "leverage"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)

    def test_headings_are_sentence_case(self):
        for head in re.findall(r"(?m)^#+ (.+)$", body()):
            words = re.sub(r"`[^`]*`", "", head).split()
            for w in words[1:]:
                with self.subTest(heading=head, word=w):
                    self.assertFalse(w[0].isupper() and not w.isupper(), "headings use sentence case")

    def test_no_colon_used_as_a_mid_sentence_connector(self):
        for line in prose().splitlines():
            with self.subTest(line=line[:60]):
                self.assertNotRegex(line, r"[A-Za-z)]: *\S", "write two sentences instead of a colon")

    def test_it_is_ascii_so_the_character_count_is_the_byte_count(self):
        self.assertEqual(len(raw()), len(raw().encode("utf-8")))


# Intentional: these exact strings are what the rulings require the skill to say. Each key is the place it must be said.
REQUIRED = {
    "When to use": ["Skip it when `Stack`, `Card`, `Table` and the charts can draw it"],
    "step 1": ["wait for a yes", "Done when the user agrees"],
    "step 2": [
        "`hermes config path`", "`<home>` below is the folder that holds the `config.yaml` it prints",
        "If `$HERMES_HOME` is set it must equal `<home>`", "show the user both paths and ask",
        "`hermes -p NAME`", "`profiles/NAME`", "touch no other profile",
        "`hermes openui components list` and note the slugs and component names", "a repeated slug disables one pack",
        "never overwrite an existing pack file",
        "`write_file`", "`<home>/packs/<slug>.js`", "write nowhere else", "`read_file`", "Done when `read_file` shows it",
    ],
    "step 3": [
        "`hermes openui components check <home>/packs/<slug>.js`", "Done when it prints `OK` (fix and rerun on `FAIL`). If a `Node was not found` note follows,",
        "the zod checks did not run", "ask the user to check the sample closely",
    ],
    "step 4": [
        "(read only; a non-zero exit means unset)", "If it holds `<home>/packs`, skip the rest of this step", "show the user the pack path",
        "wait for a yes before you run `config set`", "because `set` replaces the list",
        "absolute paths, never hand-edit the YAML", "every `.js` in it, not subfolders",
        "Capabilities > Plugins > hermes-openui",
    ],
    "step 5": [
        "`render_widget(reference=true)` again", "stale", "OpenUI Lang syntax rules", "\"Custom components\" is its last section",
        "lists the new component and every component the step 2 list showed", "the result has no `pack_warnings`",
        "also appears in a successful `render_widget` result", "absent when nothing is wrong",
    ],
    "step 6": [
        "`render_widget(source=..., name=...)`", "`name` is an optional label for the saved file", "`directive`", "`ok`", "`packs`", "`custom:<slug>`",
        "tell the user to read the pack file before relying on it", "the result has no `pack_warnings`", "and the user confirms the look",
    ],
    "step 7": ["fetch the reference again if a signature changed", "Done when the user is satisfied"],
    "Template": ["Change `progress` in three places (header `name`, `register`, file name)"],
    "Rules": [
        "Plain JavaScript, no `import`, no JSX", "`check` does not compare them", "an array of the `defineComponent` results", "(lowercase letters, digits, hyphens, at most 32, starting with a letter)",
        "`check` compares only the names, so keep it equal to the zod props by hand", "not the `description` of `defineComponent`",
        "an object array as `events: {date: string, title: string, detail?: string}[]`",
        "PascalCase letters and digits, at most 48", "put optional ones last", "plain objects", "is `undefined`", "`null` stays `null`",
        "No network or dynamic code, for example `fetch`, `WebSocket`, `EventSource`, `sendBeacon`, `eval(`, `Function(`, `import(`",
        "`check` names the exact word", "At most 200 KB",
        "The host defines `--foreground`, `--muted-foreground`, `--accent`, `--border` and `--card`", "`#f5a623`", "ignores theme changes",
        "The column is up to 640 px wide", "`overflowX: \"auto\"`", "`overflowWrap: \"anywhere\"`", "Do not set `fontFamily`",
        "clamps out-of-range values on purpose", "`validate: function (typeName, props)", "on the `register` argument",
        "an array of problem strings", "(not in `check`)", "must be pure",
    ],
    "Pitfalls": [
        "widget sandbox", "`export_widgets` pages", "Native mode refuses them",
        "To remove a pack, delete its file", "Only if that leaves a linked folder with no `.js` file, and after the user says yes",
        "write the list from step 4 back without that folder with `config set`",
        "Use `hermes config unset` only if it was the only entry, because it drops the whole list",
    ],
    "Verification": [
        "Report only what you saw", "`ok: false`", "fix exactly the `errors`", "`checked: \"node\"`", "\"structural\"",
        "means the Node check did not run (no Node, no validator file or a timeout), so the schema was not checked",
        "Neither runs your component function", "null-safe",
    ],
    "Making it built in (maintainers)": [
        "development checkout of newtonapple/hermes-openui, never in the installed copy", "section 3 of its `AGENTS.md`",
        "Ask before `cd build && npm ci`", "`npm run build` and the tests", "Ask before the commit and before the reload",
        "`hermes plugins install file://<checkout path> --force --enable` (add `-p NAME` for a named profile)", "NEW chat",
        "`hermes -p NAME gateway restart`", "separate shell",
    ],
}
# Words the older text used that were wrong or misleading.
FORBIDDEN = [
    "<name>", "dirty copy", "any pack code they did not ask for", "AccentColor", "(you cannot see it)",
    "with the header's name and components", "Its folder is the profile",
    "Node was missing", "also run `hermes config unset`", "The column is 640 px wide", "Skip this step when", "and no `Node was not found` note",
]


class Wording(unittest.TestCase):
    def where(self, key):
        return step(int(key.split()[1])) if key.startswith("step ") else section(key)

    def test_each_place_says_what_the_rulings_require(self):
        for key, needles in REQUIRED.items():
            text = self.where(key)
            for needle in needles:
                with self.subTest(place=key, needle=needle):
                    self.assertIn(needle, text)

    def test_the_older_wrong_wording_is_gone(self):
        for word in FORBIDDEN:
            with self.subTest(word=word):
                self.assertNotIn(word, raw())

    def test_the_slug_is_looked_up_before_the_file_is_written(self):
        s = step(2)
        self.assertLess(s.index("`hermes openui components list`"), s.index("`write_file`"))

    def test_step_4_reads_first_without_asking_and_asks_before_it_writes(self):
        s = step(4)
        self.assertLess(s.index("`hermes config get"), s.index("skip the rest of this step"), "the read decides whether to skip")
        self.assertLess(s.index("skip the rest of this step"), s.index("wait for a yes before you run `config set`"))
        self.assertLess(s.index("wait for a yes before you run `config set`"), s.index("`hermes config set"))
        self.assertIn("(read only;", s, "the read needs no ask, and the skill says so")

    def test_every_place_that_sets_or_unsets_the_config_is_preceded_by_an_ask_in_the_same_paragraph(self):
        # `config get` is exempt (it only reads). `config set` and `config unset` edit config.yaml, so a yes must come first.
        lines = [ln for ln in body().splitlines() if re.search(r"config (?:set|unset)", ln)]
        self.assertEqual(len(lines), 2, "step 4 and the removal advice are the only places that edit the config")
        for ln in lines:
            with self.subTest(line=ln[:50]):
                first = re.search(r"config (?:set|unset)", ln).start()
                self.assertRegex(ln[:first], r"\byes\b", "wait for the user's yes before the first edit")
        self.assertIn("after the user says yes", section("Pitfalls"))

    def test_the_ok_and_checked_fields_are_explained_where_the_agent_reads_them(self):
        v = section("Verification")
        self.assertLess(v.index("`ok: true`"), v.index("Neither runs your component function"))


class Template(Tmp):
    def setUp(self):
        super().setUp()
        self.src = template()
        self.path = self.write("progress.js", self.src)
        self.header = packs.parse_header(self.src)

    def test_the_real_loader_accepts_it_with_no_problems(self):
        found, problems = packs.load([str(self.path)], bundle.component_names())
        self.assertEqual(problems, [])
        self.assertEqual(len(found), 1)
        self.assertEqual(list(found[0].components), list(self.header["components"]))

    def test_the_header_slug_is_the_slug_passed_to_register_and_it_occurs_nowhere_else(self):
        registered = re.search(r"register\(\{\s*name:\s*\"([^\"]+)\"", self.src).group(1)
        self.assertEqual(registered, self.header["name"])
        self.assertEqual(self.src.count('"%s"' % registered), 2, "the skill says to change it in three places: the header, register and the file name")

    def test_it_uses_css_variables_with_fallbacks_and_no_hard_coded_colour(self):
        self.assertRegex(self.src, r"var\(--[a-z-]+, [^)]+\)")
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b", self.src.split("*/", 1)[1]), "hard-coded colours do not follow the theme")
        self.assertIn("createElement", self.src, "no JSX in a pack")
        self.assertNotRegex(self.src, r"<[A-Za-z]+[ />]")

    def test_it_uses_only_the_color_variables_the_host_defines(self):
        # A variable the host does not define silently falls back, so a typo in a name draws, but never follows the theme.
        host = set(re.findall(r"var\((--[a-z-]+)", read("build/src/theme.js")))
        used = set(re.findall(r"var\((--[a-z-]+)", self.src))
        self.assertTrue(used, "the template uses theme variables")
        self.assertLessEqual(used, host)

    def test_the_reference_line_in_the_header_matches_the_zod_props(self):
        # The plugin compares neither, but the agent reads the header line and the validator reads the zod object.
        line = list(self.header["components"].values())[0]
        signature = re.match(r"\w+\((.*?)\)\.", line).group(1)
        declared = [(m.group(1), bool(m.group(2))) for m in re.finditer(r"(\w+)(\?)?: \w+", signature)]
        props = re.search(r"props: z\.object\(\{(.*)\}\),", self.src).group(1)
        actual = [(m.group(1), ".optional()" in m.group(2)) for m in re.finditer(r"(\w+): (z\.\w+\(\)(?:\.optional\(\))?)", props)]
        self.assertEqual(declared, actual)
        self.assertEqual([name for name, _ in declared], ["label", "value", "max"])

    def test_the_accent_fallback_is_a_keyword_chrome_draws(self):
        self.assertIn("var(--accent, Highlight)", self.src)
        self.assertNotIn("AccentColor", self.src, "Chrome does not know AccentColor, so the fill vanishes outside the Hermes app")

    def test_it_guards_the_edges_the_rules_name(self):
        self.assertIn("p.max > 0 ? p.max : 100", self.src)
        self.assertIn('overflowWrap: "anywhere"', self.src)
        self.assertIn("Math.max(0, Math.min(100,", self.src)

    @unittest.skipUnless(HAS_NODE, "needs Node and assets/validate.cjs")
    def test_hermes_openui_components_check_passes_it(self):
        code, text = cli.components_check([str(self.path)])
        self.assertEqual(code, 0, text)
        self.assertIn("OK", text)
        self.assertNotIn("Node was not found", text)

    @unittest.skipUnless(HAS_NODE, "needs Node and assets/validate.cjs")
    def test_the_real_validator_accepts_good_calls_and_rejects_bad_ones(self):
        found, _ = packs.load([str(self.path)], bundle.component_names())
        name = list(self.header["components"])[0]
        good = 'root = Stack([a, b, c])\na = %s("Disk used", 62)\nb = %s("Tests passed", 18, 24)\nc = %s("Edge", 150, null)' % (name, name, name)
        self.assertEqual(tools._node_validate(good, found), [])
        wrong_type = tools._node_validate('root = Stack([a])\na = %s("Disk used", "high")' % name, found)
        self.assertTrue(wrong_type, "zod must reject a string where a number is declared")

    @unittest.skipUnless(HAS_NODE, "needs Node and assets/validate.cjs")
    def test_check_notices_a_header_that_disagrees_with_the_script(self):
        name = list(self.header["components"])[0]
        broken = self.src.replace('"%s": "%s(' % (name, name), '"%sX": "%sX(' % (name, name))
        code, text = cli.components_check([str(self.write("broken.js", broken))])
        self.assertEqual(code, 1, text)
        self.assertIn("does not register it", text)

    def test_the_real_render_tool_uses_it_and_names_the_pack_custom_slug(self):
        r = self.render('root = Stack([a])\na = ProgressBar("Disk used", 62)', self.path)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["packs"], ["custom:progress"])
        self.assertTrue(r["directive"].startswith('::preview{file="'))


class FactsTheSkillStates(Tmp):
    """Each claim the skill makes about the plugin, run for real. If the plugin changes, these fail and the skill gets fixed."""

    def two_copies(self, slug_b):
        self.write("packs/a.js", template())
        self.write("packs/b.js", template().replace("ProgressBar", "Badge").replace('"progress"', '"%s"' % slug_b))

    def test_two_packs_with_one_slug_disable_one_of_them(self):
        self.two_copies("progress")
        found, problems = packs.load([str(self.dir / "packs")], bundle.component_names())
        self.assertEqual([p.name for p in found], ["progress"])
        self.assertEqual(len(problems), 1)
        self.assertIn("already used by another linked pack", problems[0])

    def test_a_new_slug_loads_both_and_the_file_name_does_not_have_to_match_the_slug(self):
        self.two_copies("badge")
        found, problems = packs.load([str(self.dir / "packs")], bundle.component_names())
        self.assertEqual(problems, [])
        self.assertEqual(sorted((p.name, p.path.name) for p in found), [("badge", "b.js"), ("progress", "a.js")])

    def test_the_limits_the_skill_states_are_the_loaders(self):
        slug = int(re.search(r"\{0,(\d+)\}", packs._PACK_NAME.pattern).group(1)) + 1
        comp = int(re.search(r"\{0,(\d+)\}", packs._COMPONENT.pattern).group(1)) + 1
        rules = section("Rules")
        self.assertIn("lowercase letters, digits, hyphens, at most %d, starting with a letter" % slug, rules)
        self.assertIsNone(packs._PACK_NAME.match("3d"), "a slug cannot start with a digit")
        self.assertIsNone(packs._PACK_NAME.match("-x"), "or a hyphen")
        self.assertIn("PascalCase letters and digits, at most %d" % comp, rules)
        self.assertIn("At most %d KB" % (packs.MAX_PACK_BYTES // 1024), rules)
        self.assertRegex("a" * slug, packs._PACK_NAME.pattern)
        self.assertNotRegex("a" * (slug + 1), packs._PACK_NAME.pattern)
        self.assertNotRegex("A" + "b" * comp, packs._COMPONENT.pattern)
        self.assertIsNone(packs._COMPONENT.match("Rating_Bar"), "an underscore is not a letter or digit")

    def test_every_forbidden_word_the_skill_lists_is_refused_by_the_loader(self):
        listed = re.search(r"for example (`[^.]*?`)\.", section("Rules")).group(1)
        words = re.findall(r"`([^`]+)`", listed)
        self.assertEqual(words, ["fetch", "WebSocket", "EventSource", "sendBeacon", "eval(", "Function(", "import("])
        for word in words:
            with self.subTest(word=word):
                call = word if word.endswith("(") else word + "()"
                p = self.write("bad.js", template().replace("var defineComponent", "%s;\n  var defineComponent" % call, 1))
                found, problems = packs.load([str(p)], bundle.component_names())
                self.assertEqual(found, [])
                self.assertIn(word.rstrip("("), problems[0])

    def test_a_folder_entry_links_each_js_in_it_but_not_subfolders(self):
        self.write("packs/a.js", template())
        self.write("packs/sub/b.js", template().replace("ProgressBar", "Badge").replace('"progress"', '"badge"'))
        found, problems = packs.load([str(self.dir / "packs")], bundle.component_names())
        self.assertEqual([p.name for p in found], ["progress"])
        self.assertEqual(problems, [])

    def test_a_linked_folder_with_no_js_left_is_a_reported_problem(self):
        (self.dir / "packs").mkdir()
        found, problems = packs.load([str(self.dir / "packs")], bundle.component_names())
        self.assertEqual(found, [])
        self.assertIn("the folder has no .js files", problems[0])

    def test_the_host_color_variables_are_the_ones_the_runtime_uses(self):
        defined = sorted(set(re.findall(r"var\((--[a-z-]+)", read("build/src/theme.js"))))
        rule = [b for b in section("Rules").splitlines() if b.startswith("- The host defines")][0]
        self.assertEqual(sorted(re.findall(r"`(--[a-z-]+)`", rule)), defined)
        self.assertEqual(defined, ["--accent", "--border", "--card", "--foreground", "--muted-foreground"])

    def test_the_built_ins_set_no_font_family_except_a_monospace_stack(self):
        for f in sorted((ROOT / "build" / "src").rglob("*.jsx")) + [ROOT / "build" / "src" / "theme.js"]:
            for hit in re.findall(r"fontFamily\s*[:=]\s*\{?([^,}\n]+)", f.read_text(encoding="utf-8")):
                with self.subTest(file=f.name, value=hit.strip()):
                    self.assertRegex(hit, r"(?i)mono")

    def test_the_column_width_matches_the_screenshot_tool(self):
        self.assertIn("The column is up to 640 px wide", section("Rules"))
        self.assertIn("widget column width in CSS px (default 640", read("tools/shoot.py"))

    def test_the_setting_path_in_the_skill_is_the_one_in_the_plugin_and_the_cli_help(self):
        label = "Capabilities > Plugins > hermes-openui"
        self.assertIn(label, step(4))
        self.assertIn(label, cli.LINK_HELP)
        yml = read("plugin.yaml")
        self.assertIn("Capabilities > Plugins", yml)
        self.assertRegex(yml, r"(?m)^name: hermes-openui$")
        self.assertRegex(yml, r"(?m)^  components:\n    type: list")

    def test_native_mode_refuses_a_pack_and_an_export_page_runs_it(self):
        pack = self.write("progress.js", template())
        native = self.render('root = Stack([a])\na = ProgressBar("x", 1)', pack, mode="native")
        self.assertFalse(native["ok"])
        self.assertIn("only work in preview mode", " ".join(native["errors"]))
        params = {"sections": [{"source": 'root = Stack([a])\na = ProgressBar("x", 1)'}], "path": str(self.dir / "out.html")}
        out = json.loads(export.export_widgets(params, settings={"components": [str(pack)]}))
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["packs"], ["custom:progress"])

    def test_the_render_tool_has_the_parameters_and_result_fields_the_skill_names(self):
        self.assertEqual(sorted(schemas.RENDER_WIDGET["parameters"]["properties"]), ["name", "reference", "source"])
        pack = self.write("progress.js", template())
        ok = self.render('root = Stack([a])\na = ProgressBar("x", 1)', pack)
        for field in ("ok", "directive", "packs", "checked"):
            with self.subTest(field=field):
                self.assertRegex(step(6) + section("Verification"), r"`%s\b" % field)
                self.assertIn(field, ok)
        bad = self.render("root = Stack([a])\na = Nope(1)", pack)
        self.assertEqual(sorted(bad), ["errors", "fix", "ok"])
        self.assertIn("`errors`", section("Verification"))

    def test_pack_warnings_is_a_field_of_the_reference_result_and_of_a_render(self):
        self.write("packs/progress.js", template())
        self.write("packs/broken.js", "// no header")
        settings = {"components": [str(self.dir / "packs")]}
        ref = json.loads(tools.render_widget({"reference": True}, settings=settings))
        self.assertIn("broken.js", " ".join(ref["pack_warnings"]))
        self.assertIn("Custom components", ref["reference"])
        ok = json.loads(tools.render_widget({"source": 'root = Stack([a])\na = ProgressBar("x", 1)'}, settings=settings))
        self.assertIn("pack_warnings", ok)

    def test_pack_warnings_is_absent_when_there_is_nothing_to_warn_about(self):
        # The skill says "absent when nothing is wrong", so an agent can treat the field as a signal.
        self.write("packs/progress.js", template())
        settings = {"components": [str(self.dir / "packs")]}
        ref = json.loads(tools.render_widget({"reference": True}, settings=settings))
        ok = json.loads(tools.render_widget({"source": 'root = Stack([a])\na = ProgressBar("x", 1)'}, settings=settings))
        self.assertNotIn("pack_warnings", ref)
        self.assertNotIn("pack_warnings", ok)

    def test_a_new_pack_that_takes_a_used_slug_passes_check_and_the_reference_lists_it_but_the_older_component_is_lost_and_pack_warnings_says_so(self):
        # The collision the skill guards against. The new file sorts first, so it wins and the older pack is skipped.
        self.write("packs/progress.js", template())
        new = self.write("packs/badge.js", template().replace("ProgressBar", "Badge"))
        settings = {"components": [str(self.dir / "packs")]}
        if HAS_NODE:
            self.assertEqual(cli.components_check([str(new)])[0], 0, "check alone cannot see the collision")
        ref = json.loads(tools.render_widget({"reference": True}, settings=settings))
        custom = ref["reference"].split("## Custom components", 1)[1]
        self.assertIn("Badge(", custom, "the new component is listed, so 'it is listed' alone proves nothing")
        self.assertNotIn("ProgressBar(", custom, "the older component is gone: step 5 must compare with the step 2 list")
        self.assertIn("already used by another linked pack", " ".join(ref["pack_warnings"]))
        ok = json.loads(tools.render_widget({"source": 'root = Stack([a])\na = Badge("x", 1)'}, settings=settings))
        self.assertTrue(ok["ok"], ok)
        self.assertEqual(ok["packs"], ["custom:progress"], "the pack name looks right in step 6 too")
        self.assertIn("already used by another linked pack", " ".join(ok["pack_warnings"]))
        lost = json.loads(tools.render_widget({"source": 'root = Stack([a])\na = ProgressBar("x", 1)'}, settings=settings))
        self.assertFalse(lost["ok"], "the user's earlier component stops working")

    def test_the_skill_tells_the_agent_to_compare_with_the_earlier_list_and_to_read_pack_warnings_in_steps_5_and_6(self):
        self.assertIn("note the slugs and component names", step(2))
        self.assertIn("never overwrite an existing pack file", step(2))
        self.assertRegex(step(5), r"lists the new component and every component the step 2 list showed")
        for n in (5, 6):
            with self.subTest(step=n):
                self.assertIn("the result has no `pack_warnings`", step(n))
                self.assertLess(step(n).index("Done when"), step(n).index("`pack_warnings`"), "it is part of the check")

    def test_the_header_line_is_the_one_the_agent_reads_and_check_compares_only_the_names(self):
        marker = "ZZ-DESCRIPTION-MARKER"
        line = "Events(events: {date: string, title: string, detail?: string}[]). A list of events."
        src = pack_source("events", "Events", "z.object({ events: z.array(z.object({ date: z.string(), title: z.string(), detail: z.string().optional() })) })", "return null;")
        src = src.replace('"Events(n: number). Test."', json.dumps(line)).replace('description: "Test."', 'description: "%s"' % marker)
        p = self.write("packs/events.js", src)
        settings = {"components": [str(p)]}
        ref = json.loads(tools.render_widget({"reference": True}, settings=settings))
        self.assertIn(line, ref["reference"], "an object array written in the zod shape is accepted and shown as written")
        self.assertNotIn(marker, json.dumps(ref), "the description given to defineComponent is not in the reference")
        bad = json.loads(tools.render_widget({"source": "root = Stack([a])\na = Events(1)"}, settings=settings))
        self.assertNotIn(marker, json.dumps(bad), "nor in an error")
        ok = json.loads(tools.render_widget({"source": 'root = Stack([a])\na = Events([{date: "d", title: "t"}])'}, settings=settings))
        self.assertTrue(ok["ok"], ok)
        self.assertNotIn(marker, json.dumps(ok))
        if HAS_NODE:
            wrong_line = src.replace(json.dumps(line)[1:-1], "Events(totally: other, args: string). Different.")
            code, text = cli.components_check([str(self.write("packs/wrong.js", wrong_line))])
            self.assertEqual(code, 0, "check compares only the names: " + text)

    def test_without_node_check_prints_the_note_and_the_render_says_structural(self):
        pack = self.write("progress.js", template())
        with mock.patch.object(tools.shutil, "which", return_value=None):
            code, text = cli.components_check([str(pack)])
            self.assertEqual(code, 0, text)
            self.assertIn("Node was not found", text)
            r = self.render('root = Stack([a])\na = ProgressBar("x", 1)', pack)
        self.assertEqual(r["checked"], "structural")
        self.assertIn("Node was not found", step(3))
        self.assertIn('"structural"', section("Verification"))

    def test_structural_means_the_node_check_did_not_run_in_each_of_its_three_cases(self):
        # tools.py: _node_validate returns None (so checked is "structural") with no Node, with no validator file and on a timeout.
        pack = self.write("progress.js", template())
        source = 'root = Stack([a])\na = ProgressBar("x", 1)'
        cases = {
            "no Node": mock.patch.object(tools.shutil, "which", return_value=None),
            "no validator file": mock.patch.object(tools.bundle, "VALIDATOR", self.dir / "missing-validate.cjs"),
            "a timeout": mock.patch.object(tools.subprocess, "run", side_effect=subprocess.TimeoutExpired("node", 1)),
        }
        for label, patch in cases.items():
            with self.subTest(case=label), patch:
                r = self.render(source, pack)
                self.assertTrue(r["ok"], r)
                self.assertEqual(r["checked"], "structural")
        meaning = section("Verification")
        self.assertIn("\"structural\"` means the Node check did not run (no Node, no validator file or a timeout)", meaning)
        self.assertIn("so the schema was not checked", meaning)
        self.assertNotIn("Node was missing", meaning, "that was only one of the three cases")

    @unittest.skipUnless(HAS_NODE, "needs Node and assets/validate.cjs")
    def test_with_node_the_render_says_node_and_a_component_that_throws_still_passes_everything(self):
        throws = self.write("throws.js", pack_source("throws", "Throws", "z.object({ n: z.number() })", 'throw new Error("boom");'))
        code, text = cli.components_check([str(throws)])
        self.assertEqual(code, 0, text)
        r = self.render("root = Stack([a])\na = Throws(1)", throws)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["checked"], "node")
        self.assertIn("Neither runs your component function", section("Verification"))

    @unittest.skipUnless(HAS_NODE, "needs Node and assets/validate.cjs")
    def test_the_validate_hook_runs_when_a_source_is_rendered_and_not_in_check(self):
        hook = pack_source("hooked", "Hooked", "z.object({ n: z.number() })", "return null;",
                           ', validate: function (typeName, props) { return props.n < 0 ? ["n must be 0 or more."] : []; }')
        p = self.write("hooked.js", hook)
        code, text = cli.components_check([str(p)])
        self.assertEqual(code, 0, text)
        bad = self.render("root = Stack([a])\na = Hooked(-1)", p)
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["errors"], ["n must be 0 or more."])
        self.assertTrue(self.render("root = Stack([a])\na = Hooked(2)", p)["ok"])
        params = {"sections": [{"source": "root = Stack([a])\na = Hooked(-1)"}], "path": str(self.dir / "o.html")}
        out = json.loads(export.export_widgets(params, settings={"components": [str(p)]}))
        self.assertFalse(out["ok"], "export_widgets runs the same hook")

    @unittest.skipUnless(HAS_NODE, "needs Node and assets/validate.cjs")
    def test_check_does_not_compare_the_header_slug_with_the_one_passed_to_register(self):
        mismatch = template().replace('register({ name: "progress"', 'register({ name: "other"')
        self.assertNotEqual(mismatch, template())
        code, text = cli.components_check([str(self.write("mismatch.js", mismatch))])
        self.assertEqual(code, 0, "if this starts to fail, check now compares them: update the skill, which says it does not")
        self.assertIn("`check` does not compare them", section("Rules"))


# Intentional: the argument types and the OpenUI Lang value for each, written out so the skill and the validator stay in step.
TYPES = [
    ("z.string()", '"a"'),
    ("z.number()", "3"),
    ("z.boolean()", "true"),
    ('z.enum(["a", "b"])', '"a"'),
    ("z.array(z.string())", '["a", "b"]'),
    ("z.array(z.object({ label: z.string(), n: z.number() }))", '[{label: "a", n: 1}]'),
]


class ArgumentTypes(Tmp):
    def test_the_skill_lists_exactly_these_pairs(self):
        self.assertEqual(re.findall(r"`(z\.[^`]+)` `([^`]+)`", section("Rules")), TYPES)

    def sink(self):
        props = ", ".join("a%d: %s" % (i, t) for i, (t, _) in enumerate(TYPES))
        props += ", o: z.string().optional(), p: z.number().optional()"
        keys = json.dumps(["a%d" % i for i in range(len(TYPES))] + ["o", "p"])
        body_js = (
            "var keys = %s;"
            ' return h("pre", { "data-sink": "1" }, keys.map(function (k) { var v = ctx.props[k]; return k + "=" + (v === undefined ? "undefined" : JSON.stringify(v)); }).join(" | "));'
        ) % keys
        return self.write("sink.js", pack_source("sink", "Sink", "z.object({ %s })" % props, body_js))

    def calls(self):
        values = ", ".join(v for _, v in TYPES)
        return 'root = Stack([a, b, c])\na = Sink(%s)\nb = Sink(%s, null, null)\nc = Sink(%s, "x", 7)' % (values, values, values)

    @unittest.skipUnless(HAS_NODE, "needs Node and assets/validate.cjs")
    def test_the_real_validator_accepts_every_pair_with_optionals_left_out_null_or_given(self):
        found, problems = packs.load([str(self.sink())], bundle.component_names())
        self.assertEqual(problems, [])
        self.assertEqual(tools._node_validate(self.calls(), found), [])
        wrong = tools._node_validate(self.calls().replace('Sink("a", 3', 'Sink("a", "three"', 1), found)
        self.assertTrue(wrong, "zod still rejects a wrong type")

    def test_how_each_value_arrives_in_a_real_browser(self):
        reason = chrome_missing_reason()
        if reason:
            self.skipTest("no Chrome: " + reason)
        sink = self.sink()
        oui = self.write("sink.oui", self.calls())
        png = self.dir / "sink.png"
        shoot = [sys.executable, str(ROOT / "tools" / "shoot.py")]
        run = subprocess.run(shoot + [str(oui), str(png), "--pack", str(sink), "--keep-html"], capture_output=True, text=True, timeout=180, env=NODE_ENV)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        expr = "Array.from(document.querySelectorAll('[data-sink]')).map(function (e) { return e.textContent; })"
        probe = subprocess.run(shoot + ["--html", str(png.with_suffix(".html")), str(self.dir / "again.png"), "--eval", expr], capture_output=True, text=True, timeout=180, env=NODE_ENV)
        self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
        self.assertIn("console errors: 0", probe.stdout)
        rows = json.loads(re.search(r"eval: (.*)", probe.stdout).group(1))
        self.assertEqual(len(rows), 3)
        left_out, nulls, given = rows
        self.assertIn("o=undefined | p=undefined", left_out)
        self.assertIn("o=null | p=null", nulls)
        self.assertIn('o="x" | p=7', given)
        for row in rows:
            self.assertIn('a5=[{"label":"a","n":1}]', row, "an array of objects arrives as plain objects")
            self.assertIn('a4=["a","b"]', row)
            self.assertIn("a2=true", row)


class Commands(unittest.TestCase):
    # Intentional: the commands written out in full. A rename in the skill, a typo in the config key or a changed flag fails here.
    COMMANDS = [
        "hermes config path",
        "hermes openui components list",
        "hermes openui components check <home>/packs/<slug>.js",
        "hermes config get %s --json" % CONFIG_KEY,
        "hermes config set %s '[\"<home>/packs\"]'" % CONFIG_KEY,
        "hermes config unset",
        "hermes -p NAME",
        "hermes plugins install file://<checkout path> --force --enable",
        "hermes -p NAME gateway restart",
    ]

    def test_the_skill_names_these_hermes_commands_and_no_others(self):
        self.assertEqual(set(re.findall(r"`(hermes [^`]+)`", raw())), set(self.COMMANDS))

    def test_every_hermes_openui_command_parses_with_the_plugins_own_cli(self):
        found = set(re.findall(r"hermes(?: -p \w+)? openui((?: [a-z]+)+)", raw()))
        self.assertEqual(found, {" components check", " components list"})
        for tail in sorted(found):
            with self.subTest(command="hermes openui" + tail):
                parser = argparse.ArgumentParser()
                cli.setup_parser(parser)
                args = parser.parse_args(tail.split() + (["pack.js"] if tail.endswith("check") else []))
                self.assertEqual(args.openui_cmd, "components")
                self.assertIn(args.components_cmd, ("check", "list"))

    def test_the_set_command_is_one_shell_word_per_argument_and_its_value_is_a_json_list_of_absolute_paths(self):
        command = [c for c in re.findall(r"`(hermes [^`]+)`", raw()) if c.startswith("hermes config set")][0]
        words = shlex.split(command.replace("<home>", "/home-dir"))
        self.assertEqual(words[:3], ["hermes", "config", "set"])
        self.assertEqual(len(words), 5, words)
        self.assertEqual(words[3], CONFIG_KEY)
        self.assertEqual(json.loads(words[4]), ["/home-dir/packs"])

    def test_the_check_command_is_the_one_the_cli_handles_and_its_ok_word_is_what_it_prints(self):
        self.assertIn("Done when it prints `OK`", step(3))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "progress.js"
            p.write_text(template(), encoding="utf-8")
            code, text = cli.components_check([str(p)])
        self.assertEqual(code, 0, text)
        self.assertTrue(text.startswith("OK "), text)
        bad = cli.components_check(["/no/such/pack.js"])
        self.assertEqual(bad[0], 1)
        self.assertTrue(bad[1].startswith("FAIL "), bad[1])
        self.assertIn("rerun on `FAIL`", step(3))

    def test_the_config_key_is_the_one_the_plugin_reads(self):
        self.assertIn(CONFIG_KEY, raw())
        yml = read("plugin.yaml")
        self.assertRegex(yml, r"(?m)^name: hermes-openui$")
        self.assertRegex(yml, r"(?m)^  components:$")
        self.assertIn('("components", [])', read("__init__.py"), "the plugin reads the `components` setting")

    def test_the_list_command_prints_the_taken_slugs_and_the_reason_a_pack_was_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.js").write_text(template(), encoding="utf-8")
            (Path(d) / "b.js").write_text(template().replace("ProgressBar", "Badge"), encoding="utf-8")
            code, text = cli.components_list({"components": [d]})
        self.assertEqual(code, 1)
        self.assertRegex(text, r"(?m)^progress  1 component")
        self.assertIn("Problems (these packs are skipped):", text)
        self.assertIn("already used by another linked pack", text)

    def test_the_chat_tool_names_match(self):
        self.assertIn("render_widget(reference=true)", raw())
        self.assertIn("render_widget(source=..., name=...)", raw())
        self.assertEqual(sorted(set(re.findall(r"`(write_file|read_file)`", raw()))), ["read_file", "write_file"])
        self.assertEqual(sorted(schemas.RENDER_WIDGET["parameters"]["properties"]), ["name", "reference", "source"])

    def test_the_reload_command_is_the_same_in_the_skill_and_in_agents_md(self):
        agents = read("AGENTS.md")
        self.assertIn("hermes plugins install file:///absolute/path --enable", agents)
        self.assertIn("commit and run the same command with `--force`", agents)
        self.assertIn("`hermes plugins update hermes-openui` also pulls new commits from a `file://` source", agents)
        self.assertIn("hermes plugins install file://<checkout path> --force --enable", raw())


class OtherSkill(unittest.TestCase):
    """openui-render is the skill every agent sees first; it has to lead to this one without naming a path that may not exist."""

    def test_it_points_to_the_skill_and_not_to_a_docs_path(self):
        text = (ROOT / "skills" / "openui-render" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("skill_view('hermes-openui:custom-components')", text)
        self.assertNotIn("docs/custom-components.md", text)
        self.assertLessEqual(len(text), 4500)


class Docs(unittest.TestCase):
    """The human docs say what the skill does, with the same names and the same measured numbers."""

    NAME = "hermes-openui:custom-components"

    def test_the_guide_has_a_section_about_asking_the_agent(self):
        text = read("docs/custom-components.md")
        self.assertIn("\n## Ask the agent to write one\n", text)
        sect = text.split("## Ask the agent to write one", 1)[1].split("\n## ", 1)[0]
        self.assertIn(self.NAME, sect)
        # what the skill tells the agent to do, not a promise about what a model always does
        self.assertRegex(sect, r"The skill tells the agent to ask before[^.]*config\.yaml")
        self.assertNotRegex(sect, r"(?i)\bthe agent asks before")

    def test_the_readme_says_the_skill_tells_the_agent_to_ask_and_does_not_promise_it(self):
        text = read("README.md")
        self.assertRegex(text, r"the skill tells it to ask before it edits `config\.yaml`")
        self.assertNotRegex(text, r"\(it asks before it edits")

    def test_readme_and_agents_name_the_skill(self):
        for name in ("README.md", "AGENTS.md"):
            with self.subTest(file=name):
                self.assertIn(self.NAME, read(name))

    def test_the_context_cost_table_matches_the_measured_sizes(self):
        schema_tokens = len(json.dumps(helpers.sub("schemas").RENDER_WIDGET)) / 4
        row = re.search(r"\| Tool schema \([\d.]+ KB\)[^|]*\|[^|]*\| about (\d+) \|", read("README.md"))
        self.assertIsNotNone(row, "the README table has no tool schema row")
        self.assertLessEqual(abs(int(row.group(1)) - schema_tokens), 5)
        skill_tokens = len(raw()) / 4
        m = re.search(r"custom-components`, about ([\d,]+) tokens", read("README.md"))
        self.assertIsNotNone(m, "the README does not give the size of the new skill")
        self.assertLessEqual(abs(int(m.group(1).replace(",", "")) - skill_tokens), 25, "characters / 4, measured")

    def test_agents_md_states_the_current_discovery_numbers(self):
        text = read("AGENTS.md")
        self.assertIn("33 of 33", text)
        self.assertNotIn("25 of 25", text)
        self.assertNotIn("28 of 28 keyword", text)
        # one source of truth for the numbers: the harness itself
        harness = read("tools/verify_discovery.py")
        queries = re.search(r"KEYWORD = \[(.*?)\]", harness, re.S).group(1)
        self.assertEqual(len(re.findall(r'"[^"]+"', queries)), 33)
        for q in ("custom component", "new component", "add a component", "make me a new component"):
            self.assertIn('"%s"' % q, harness)

    def test_the_agents_release_steps_cover_the_second_skill(self):
        self.assertIn("skills/*/SKILL.md", read("AGENTS.md"))

    # The skill and its description change shipped in 0.2.1, so their changelog entries stay under that heading. A rule such as
    # "under Unreleased or the new release" passes only until the next release moves the heading, and then it blocks that release.
    SHIPPED_IN = "0.2.1"

    def changelog_heading_of(self, phrase):
        """The `## [...]` heading whose section holds `phrase`."""
        holders = [sec for sec in re.split(r"(?m)^(?=## \[)", read("CHANGELOG.md"))[1:] if phrase in sec]
        self.assertEqual(len(holders), 1, "%r should be in exactly one release section" % phrase)
        return re.match(r"## \[([^\]]+)\]", holders[0]).group(1)

    def test_the_changelog_records_the_skill_and_the_description_change_under_the_release_that_shipped_them(self):
        text = read("CHANGELOG.md")
        self.assertRegex(text, r"(?s)### Added.*custom-components")
        self.assertRegex(text, r"(?s)### Changed.*27 of 28.*28 of 28")
        self.assertNotRegex(text, "\u2014|\u2013")
        for phrase in ("A bundled skill, `hermes-openui:custom-components`", "27 of 28"):
            with self.subTest(entry=phrase):
                self.assertEqual(self.changelog_heading_of(phrase), self.SHIPPED_IN)

    def test_agents_md_gives_a_measured_test_time_and_the_link_line_form_for_a_release(self):
        text = read("AGENTS.md")
        self.assertNotIn("must pass; ~2 s", text, "the suite runs Node and Chrome and takes far longer than that")
        self.assertIn("must pass; about 40 s with Node and Chrome", text)
        self.assertIn("[X.Y.Z]: https://github.com/newtonapple/hermes-openui/releases/tag/vX.Y.Z", text)
        links = re.findall(r"(?m)^\[(\d[^\]]*)\]: (\S+)$", read("CHANGELOG.md"))
        for version, url in links:
            self.assertEqual(url, "https://github.com/newtonapple/hermes-openui/releases/tag/v%s" % version)

    def test_the_changelog_says_what_the_tests_do_and_does_not_claim_the_template_cannot_rot(self):
        text = read("CHANGELOG.md")
        self.assertNotIn("cannot go stale", text)
        self.assertIn("the tests load, validate and render that template", text)

    def test_agents_md_states_rules_and_leaves_lab_notes_out(self):
        text = read("AGENTS.md")
        self.assertIn("--force", text)
        self.assertNotIn("(tested", text)


class Browser(Tmp):
    """The template, drawn by a real Chrome (through tools/shoot.py, the only launcher this repo uses)."""

    PROBE = (
        "(function () {"
        " var divs = Array.from(document.querySelectorAll('#root div'));"
        " var fills = divs.filter(function (d) { return /%$/.test(d.style.width || ''); });"
        " var long = divs.find(function (d) { return d.firstChild && d.firstChild.nodeType === 3 && d.firstChild.textContent.indexOf('WWWWWWWWWW') === 0; });"
        " return { text: document.body.innerText,"
        " fills: fills.map(function (d) { return { pct: d.style.width, w: d.getBoundingClientRect().width, h: d.getBoundingClientRect().height, track: d.parentElement.getBoundingClientRect().width, trackH: d.parentElement.getBoundingClientRect().height, trackBg: getComputedStyle(d.parentElement).backgroundColor, bg: getComputedStyle(d).backgroundColor }; }),"
        " longOverflow: long ? long.scrollWidth - long.clientWidth : null };"
        "})()"
    )

    def shoot(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "tools" / "shoot.py")] + [str(a) for a in args], capture_output=True, text=True, timeout=180, env=NODE_ENV)

    def test_it_renders_with_the_theme_variables_and_the_fill_is_visible(self):
        reason = chrome_missing_reason()
        if reason:
            self.skipTest("no Chrome: " + reason)
        pack = self.write("progress.js", template())
        oui = self.write("sample.oui", (
            "root = Stack([a, b, c, d, e, f])\na = ProgressBar(\"Disk used\", 62)\nb = ProgressBar(\"Tests passed\", 18, 24)\n"
            "c = ProgressBar(\"Zero max\", 5, 0)\nd = ProgressBar(\"Over\", 150)\ne = ProgressBar(\"Neg\", -4)\nf = ProgressBar(\"%s\", 50)\n" % ("W" * 170)))
        png = self.dir / "out.png"
        run = self.shoot(oui, png, "--pack", pack, "--keep-html")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertTrue(png.read_bytes().startswith(b"\x89PNG"))
        self.assertIn("custom:progress", run.stdout)
        # Drawn on its own page with no host theme: this is where a fallback that Chrome does not know shows up as an invisible fill.
        probe = self.shoot("--html", png.with_suffix(".html"), self.dir / "again.png", "--eval", self.PROBE)
        self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
        self.assertIn("console errors: 0", probe.stdout)
        shown = json.loads(re.search(r"eval: (.*)", probe.stdout).group(1))
        text = " ".join(shown["text"].split())
        for expected in ("Disk used 62%", "Tests passed 75%", "Zero max 5%", "Over 100%", "Neg 0%"):
            self.assertIn(expected, text)
        fills = shown["fills"]
        # in the order of the sample: 62, 75, 5 (max 0 counts as 100), 150 clamped, -4 clamped, 50
        self.assertEqual([f["pct"] for f in fills], ["62%", "75%", "5%", "100%", "0%", "50%"])
        for f in fills:
            with self.subTest(fill=f["pct"]):
                self.assertAlmostEqual(f["w"] / f["track"] * 100, float(f["pct"].rstrip("%")), delta=1, msg="the drawn fill is not the share it claims")
                self.assertGreater(f["trackH"], 0, "the bar has no height, so nothing is drawn")
                self.assertGreater(f["h"], 0, "the fill has no height")
                self.assertNotIn(f["trackBg"], ("rgba(0, 0, 0, 0)", "transparent"), "the track is invisible")
                if f["pct"] != "0%":
                    self.assertGreater(f["w"], 0, "the fill has no width")
                    self.assertNotIn(f["bg"], ("rgba(0, 0, 0, 0)", "transparent"), "the fill is invisible")
        self.assertEqual(shown["longOverflow"], 0, "a long label with no spaces must wrap, not run past its box")


class StalePointers(unittest.TestCase):
    """A script install has no docs/ folder, so nothing the plugin prints or declares may send an agent there."""

    SKILL_NAME = "hermes-openui:custom-components"

    def test_the_text_list_prints_when_nothing_is_linked_names_the_skill_and_no_docs_path(self):
        self.assertNotIn("docs/", cli.LINK_HELP)
        self.assertIn("skill_view('%s')" % self.SKILL_NAME, cli.LINK_HELP)
        code, text = cli.components_list({})
        self.assertEqual(code, 0)
        self.assertIn(cli.LINK_HELP, text)

    def test_the_components_setting_description_names_the_skill_and_no_docs_path(self):
        desc = re.search(r"(?m)^  components:\n(?:    .*\n)*?    description: \"(.*)\"$", read("plugin.yaml")).group(1)
        self.assertNotIn("docs/", desc)
        self.assertIn("skill_view('%s')" % self.SKILL_NAME, desc)
        self.assertIn("Paths to component pack files", desc, "the setting is still described")

    def test_nothing_the_plugin_ships_for_agents_or_the_settings_page_points_to_a_docs_path(self):
        for name in ("plugin.yaml", "cli.py", "tools.py", "schemas.py", "skills/openui-render/SKILL.md", "skills/custom-components/SKILL.md"):
            with self.subTest(file=name):
                self.assertNotIn("docs/custom-components.md", read(name))

    def test_the_package_docstring_describes_both_bundled_skills(self):
        doc = helpers.load().__doc__
        self.assertIn("bundled skills", doc)
        self.assertNotIn("a bundled skill", doc)


@unittest.skipUnless(
    HAS_HERMES and os.environ.get("OPENUI_TEST_HERMES") == "1",
    "opt in with OPENUI_TEST_HERMES=1: a fresh Hermes home makes the CLI prepare its own dependencies first, which is slow",
)
class HermesCommands(unittest.TestCase):
    """The commands the skill gives for linking, run against a throwaway Hermes home (never the real one)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls.tmp.name).resolve()
        cls.env = dict(os.environ, HERMES_HOME=str(cls.home), DO_NOT_TRACK="1")
        # The first call in a fresh home prepares Hermes's dependencies and can fail once; later calls work.
        cls.hermes("config", "path")
        out = cls.hermes("config", "path")
        cls.honoured = out.returncode == 0 and out.stdout.strip() == str(cls.home / "config.yaml")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def hermes(cls, *args):
        return subprocess.run(["hermes"] + list(args), capture_output=True, text=True, timeout=300, env=cls.env)

    def setUp(self):
        for f in self.home.glob("config.yaml"):
            f.unlink()

    def guard(self):
        if not self.honoured:
            self.skipTest("this hermes does not honour HERMES_HOME for `config`, so it is not run here")

    def command(self, prefix):
        lines = [c for c in re.findall(r"`(hermes [^`]*)`", raw()) if c.startswith(prefix)]
        self.assertEqual(len(lines), 1, "the skill shows one `%s` command" % prefix)
        return shlex.split(lines[0].replace("<home>", str(self.home)))[1:]

    def test_config_path_prints_the_config_file_and_its_folder_is_the_home(self):
        self.guard()
        out = self.hermes(*self.command("hermes config path"))
        self.assertEqual(Path(out.stdout.strip()).parent, self.home)

    def test_the_documented_set_command_merges_under_the_existing_plugins_block(self):
        self.guard()
        (self.home / "config.yaml").write_text("plugins:\n  enabled:\n    - hermes-openui\n  disabled: []\n", encoding="utf-8")
        out = self.hermes(*self.command("hermes config set"))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        text = (self.home / "config.yaml").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"(?m)^plugins:", text)), 1, "a second top-level plugins key is not valid YAML")
        self.assertIn("- hermes-openui", text)
        got = self.hermes(*self.command("hermes config get"))
        self.assertEqual(json.loads(got.stdout), [str(self.home / "packs")])

    def test_get_with_json_reports_an_unset_list_with_a_non_zero_exit_and_unset_removes_it(self):
        self.guard()
        self.assertNotEqual(self.hermes(*self.command("hermes config get")).returncode, 0)
        self.hermes(*self.command("hermes config set"))
        removed = self.hermes("config", "unset", CONFIG_KEY)
        self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
        self.assertNotEqual(self.hermes(*self.command("hermes config get")).returncode, 0)

    def test_a_shorter_list_removes_one_entry_and_unset_drops_the_whole_list(self):
        # The removal advice: write the list back without the folder, and use `unset` only when it was the only entry.
        self.guard()
        two = json.dumps(["/one", "/two"])
        self.assertEqual(self.hermes("config", "set", CONFIG_KEY, two).returncode, 0)
        self.assertEqual(json.loads(self.hermes("config", "get", CONFIG_KEY, "--json").stdout), ["/one", "/two"])
        self.assertEqual(self.hermes("config", "set", CONFIG_KEY, json.dumps(["/one"])).returncode, 0)
        self.assertEqual(json.loads(self.hermes("config", "get", CONFIG_KEY, "--json").stdout), ["/one"], "set replaces the list")
        self.hermes("config", "set", CONFIG_KEY, two)
        self.assertEqual(self.hermes("config", "unset", CONFIG_KEY).returncode, 0)
        self.assertNotEqual(self.hermes("config", "get", CONFIG_KEY, "--json").returncode, 0, "unset removed both entries")

    def test_the_commands_exist_in_this_hermes(self):
        for args in (("config", "path", "--help"), ("config", "get", "--help"), ("config", "set", "--help"), ("config", "unset", "--help"),
                     ("plugins", "install", "--help"), ("gateway", "restart", "--help")):
            with self.subTest(command=" ".join(args)):
                self.assertEqual(self.hermes(*args).returncode, 0)
        install_help = self.hermes("plugins", "install", "--help").stdout
        for flag in ("--force", "--enable"):
            self.assertIn(flag, install_help)
        self.assertIn("-p", self.hermes("--help").stdout)


if __name__ == "__main__":
    unittest.main()
