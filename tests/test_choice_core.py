"""Choice batch card: the PURE modules (build/src/components/choice-core.js, which takes its sanitizer from notes-core.js) run under Node, no bundler.

The message is the contract with the agent, so it has golden tests (the one question line is byte for byte what agents already expect); the
sanitizer is tested on hostile words against the app's own reference pattern; the limits at their exact boundaries; the answer state in
single and multiple mode, with an Other text that is empty and filled; the store with a broken sessionStorage. What a browser does with a
click or a key is NOT tested here (tests/test_choice_native.py drives real Chrome).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402

ROOT = helpers.ROOT
SRC = ROOT / "build" / "src" / "components"
ENV = dict(os.environ, DO_NOT_TRACK="1", OPENUI_TELEMETRY_DISABLED="1", PYTHONDONTWRITEBYTECODE="1")

HARNESS = r"""
const m = await import(process.env.CHOICE_URL);
const n = await import(process.env.NOTES_URL);
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const fn = new AsyncFunction("m", "n", process.env.CHOICE_BODY);
process.stdout.write(JSON.stringify(await fn(m, n)));
"""

# The app's own pattern for a reference in a draft. COPIED from apps/desktop/src/components/assistant-ui/reference-kinds.ts (REFERENCE_PATTERN, the
# source of rich-editor.ts REF_RE): a message that matches it turns into an attached reference (a file, a URL, a session ...) when it is sent.
APP_REF = re.compile(r"""@(file|folder|url|image|tool|line|terminal|session):(`[^`\n]+`|"[^"\n]+"|'[^'\n]+'|\S+)""")

# The gateway that receives the message expands more than the app does. COPIED from agent/context_references.py lines 79-85 (REFERENCE_PATTERN: a bare
# @diff or @staged, and @file|folder|git|url:value; _PLUGIN_REFERENCE_PATTERN: any @word:value a plugin provider registered), run by tui_gateway/prompt_turn.py
# (lines 709-725) on every message that holds an "@". Both have the lookbehind (?<![\w/]).
_QUOTED = r"""(?:`[^`\n]+`|"[^"\n]+"|'[^'\n]+')"""
GATEWAY_REF = re.compile(r"(?<![\w/])@(?:(?P<simple>diff|staged)\b|(?P<kind>file|folder|git|url):(?P<value>" + _QUOTED + r"(?::\d+(?:-\d+)?)?|\S+))")
GATEWAY_PLUGIN_REF = re.compile(r"(?<![\w/])@(?P<kind>[a-zA-Z][a-zA-Z0-9_-]*):(?P<value>" + _QUOTED + r"(?::\d+(?:-\d+)?)?|\S+)")
# The app runs a text as a slash COMMAND when it matches this. COPIED from apps/shared/src/slash.ts line 11 (SLASH_COMMAND_RE; isSlashCommandText in
# lib/chat-runtime.ts strips leading attachment-reference lines and trims the start before testing it).
SLASH_COMMAND_RE = re.compile(r"^/[^\s/]*(?:\s|\Z)")


def refs(text):
    """Everything in the text that the app (APP_REF) or the gateway (both patterns) would turn into a reference."""
    return APP_REF.findall(text) + GATEWAY_REF.findall(text) + GATEWAY_PLUGIN_REF.findall(text)


PRE = r"""
const mk = (q, o, multiple, other) => m.makeChoice({ question: q, options: o, multiple: multiple, other: other });
"""


def js(body):
    r = subprocess.run(["node", "--input-type=module", "-e", HARNESS], capture_output=True, text=True, timeout=60,
                       env=dict(ENV, CHOICE_URL=(SRC / "choice-core.js").as_uri(), NOTES_URL=(SRC / "notes-core.js").as_uri(),
                                CHOICE_BODY=PRE + body))
    if r.returncode != 0:
        raise AssertionError("node failed:\n" + (r.stderr or r.stdout)[-2500:])
    return json.loads(r.stdout)


class SharedSanitizer(unittest.TestCase):
    def test_choice_cleans_words_with_the_functions_of_notes_not_a_copy(self):
        # choice-core imports strip, collapse, clip, neutralize and hashText from notes-core.js; this proves the words come out the same on hostile input
        out = js("""
          const hostile = "a\\u202Eb\\u200Bc\\u0007d  @file:/x @URL:y me@home @@tool:z\\u00ADq\\n\\t@Session:1";
          const c = m.makeChoice({ question: hostile, options: [hostile] });
          return { choice: c.question, option: c.options[0], quote: n.cleanText(hostile, 200), neutral: n.neutralize("x @file:/y me@home") };
        """)
        self.assertEqual(out["choice"], out["quote"])
        self.assertEqual(out["option"], out["quote"])
        self.assertIn("(at)file:/x (at)URL:y me@home @(at)tool:z", out["choice"])
        self.assertIn("(at)Session:1", out["choice"])
        self.assertEqual(out["neutral"], "x (at)file:/y me@home")
        # one source of truth: no second REF_KINDS list in the Choice code
        self.assertNotIn("terminal|session", (SRC / "choice-core.js").read_text(encoding="utf-8"))


class State(unittest.TestCase):
    def test_single_mode_toggles_unselects_and_moves(self):
        r = js("""
          const c = mk("Which node?", ["web-1", "web-2", "web-3"]);
          let a = {};
          const picks = (x) => (x[c.key] ? x[c.key].picks : []);
          a = m.toggleOption(a, c, 0); const first = picks(a);
          a = m.toggleOption(a, c, 2); const moved = picks(a);
          a = m.toggleOption(a, c, 2); const off = picks(a);
          a = m.toggleOption(a, c, 1); a = m.toggleOther(a, c); const other = { picks: picks(a), on: a[c.key].other };
          a = m.toggleOption(a, c, 0); const back = { picks: picks(a), on: a[c.key].other };
          return { first, moved, off, other, back, answered: m.isAnswered(c, a) };
        """)
        self.assertEqual(r["first"], [0])
        self.assertEqual(r["moved"], [2])
        self.assertEqual(r["off"], [])
        self.assertEqual(r["other"], {"picks": [], "on": True})  # Other replaces the option in single mode
        self.assertEqual(r["back"], {"picks": [0], "on": False})  # an option replaces Other
        self.assertTrue(r["answered"])

    def test_multiple_mode_toggles_independently_and_combines_with_other(self):
        r = js("""
          const c = mk("Checks?", ["disk", "memory", "net"], true);
          let a = {};
          a = m.toggleOption(a, c, 2); a = m.toggleOption(a, c, 0); const two = a[c.key].picks;
          a = m.toggleOther(a, c); a = m.setOtherText(a, c, "also the logs");
          const combined = { picks: a[c.key].picks, other: a[c.key].other, text: a[c.key].text };
          a = m.toggleOption(a, c, 2); const dropped = a[c.key].picks;
          return { two, combined, dropped, words: m.answerWords(c, a) };
        """)
        self.assertEqual(r["two"], [0, 2])  # kept in option order, not click order
        self.assertEqual(r["combined"], {"picks": [0, 2], "other": True, "text": "also the logs"})
        self.assertEqual(r["dropped"], [0])
        self.assertEqual(r["words"], "disk; other: also the logs")

    def test_an_other_row_that_is_open_but_empty_is_not_an_answer(self):
        r = js("""
          const c = mk("Why?", ["a", "b"]);
          let a = m.toggleOther({}, c);
          const empty = m.isAnswered(c, a);
          a = m.setOtherText(a, c, "   \\n \\u200B ");
          const blank = m.isAnswered(c, a);
          a = m.setOtherText(a, c, "because");
          const filled = m.isAnswered(c, a);
          const hidden = mk("Why?", ["a", "b"], false, false);
          let h = m.toggleOther({}, hidden); h = m.setOtherText(h, hidden, "text");
          return { empty, blank, filled, hiddenAnswered: m.isAnswered(hidden, h), words: m.answerWords(c, a), hiddenWords: m.answerWords(hidden, h),
                   progress: m.progress([c, hidden], { ...a, ...h }) };
        """)
        self.assertEqual([r["empty"], r["blank"], r["filled"]], [False, False, True])
        self.assertFalse(r["hiddenAnswered"])  # other: false ignores any Other state
        self.assertEqual(r["words"], "other: because")
        self.assertEqual(r["hiddenWords"], "")
        self.assertEqual(r["progress"], {"answered": 1, "total": 2})

    def test_other_text_is_cut_at_500_characters_and_keeps_its_own_at_sign(self):
        r = js("""
          const c = mk("Q?", ["a"]);
          let a = m.toggleOther({}, c);
          a = m.setOtherText(a, c, "x".repeat(600));
          const long = a[c.key].text.length;
          a = m.setOtherText(a, c, "mail me @file:/etc/hosts \\u202E now\\u0007");
          return { long, words: m.answerWords(c, a) };
        """)
        self.assertEqual(r["long"], 500)
        self.assertEqual(r["words"], "other: mail me @file:/etc/hosts  now")  # the user's own @ stays; control and format characters go

    def test_two_questions_with_the_same_words_are_one_question(self):
        r = js("""
          const a = mk("Same?", ["x", "y"]), b = mk("Same?", ["x", "y"]), c = mk("Same?", ["x", "y"], true);
          const list = m.uniqueChoices([a, b, c]);
          return { keys: [a.key === b.key, a.key === c.key], count: list.length };
        """)
        self.assertEqual(r["keys"], [True, False])
        self.assertEqual(r["count"], 2)

    def test_collect_walks_the_whole_tree_including_a_tab_that_was_never_shown(self):
        r = js("""
          const el = (typeName, props) => ({ type: "element", typeName, props });
          const tree = el("Stack", { children: [
            el("Choice", { question: "First?", options: ["a", "b"], hint: null, multiple: null }),
            el("Tabs", { items: [
              el("TabItem", { label: "A", content: [el("Choice", { question: "Second?", options: ["c"], multiple: true })] }),
              el("TabItem", { label: "B", content: [el("Card", { children: [el("Choice", { question: "Third?", options: ["d"], other: false })] })] }),
            ] }),
            el("Choice", { question: "First?", options: ["a", "b"] }),
          ] });
          const list = m.collectChoices(tree);
          return { q: list.map((c) => c.question), multiple: list.map((c) => c.multiple), other: list.map((c) => c.other), none: m.collectChoices(null).length };
        """)
        self.assertEqual(r["q"], ["First?", "Second?", "Third?"])  # document order, the repeated one only once
        self.assertEqual(r["multiple"], [False, True, False])
        self.assertEqual(r["other"], [True, True, False])
        self.assertEqual(r["none"], 0)


class Message(unittest.TestCase):
    def test_one_question_in_single_mode_keeps_the_wire_format_byte_for_byte(self):
        r = js("""
          const c = mk("Which node should I restart first?", ["web-1", "web-2", "web-3"]);
          const a = m.toggleOption({}, c, 1);
          return m.buildMessage([c], a, "stem1");
        """)
        self.assertEqual(r["text"], "Which node should I restart first? \u2014 web-2")
        self.assertTrue(r["compat"])

    def test_golden_three_questions_with_multiple_other_and_no_answer(self):
        r = js("""
          const c1 = mk("Which node should I restart first?", ["web-1", "web-2"]);
          const c2 = mk("Which checks should I run?", ["disk", "memory", "net"], true);
          const c3 = mk("Clear the cache on db?", ["Yes", "No"]);
          let a = m.toggleOption({}, c1, 1);
          a = m.toggleOption(a, c2, 0); a = m.toggleOption(a, c2, 1); a = m.toggleOther(a, c2); a = m.setOtherText(a, c2, "also look at the logs");
          return { anon: m.buildMessage([c1, c2, c3], a, ""), stem: m.buildMessage([c1, c2, c3], a, "restart-plan") };
        """)
        body = ("1. Which node should I restart first?\n   web-2\n"
                "2. Which checks should I run?\n   disk; memory; other: also look at the logs\n"
                "3. Clear the cache on db?\n   (no answer)")
        self.assertEqual(r["anon"]["text"], "Answers to the questions in this widget (3):\n\n" + body)
        self.assertEqual(r["stem"]["text"], "Answers to the questions in widget `restart-plan` (3):\n\n" + body)
        self.assertFalse(r["anon"]["compat"])

    def test_only_the_compat_case_uses_the_em_dash_everything_else_is_ascii_punctuation(self):
        r = js("""
          const one = mk("Q?", ["a", "b"], true);   // multiple: the batch format even for one question
          const two = mk("R?", ["a"]);
          let a = m.toggleOption({}, one, 0);
          const multi = m.buildMessage([one], a, "w").text;
          const sameOne = mk("Q?", ["a", "b"]);
          let b = m.toggleOther({}, sameOne); b = m.setOtherText(b, sameOne, "mine");
          const other = m.buildMessage([sameOne], b, "w").text;
          let both = m.toggleOption({}, sameOne, 0); both = m.toggleOption(both, two, 0);
          return { multi, other, two: m.buildMessage([sameOne, two], both, "").text };
        """)
        self.assertEqual(r["multi"], "Answers to the questions in widget `w` (1):\n\n1. Q?\n   a")
        self.assertEqual(r["other"], "Answers to the questions in widget `w` (1):\n\n1. Q?\n   other: mine")
        self.assertNotIn("\u2014", r["two"])
        self.assertTrue(r["two"].startswith("Answers to the questions in this widget (2):"))

    def test_a_question_that_would_run_as_a_slash_command_uses_the_batch_format(self):
        # The one-question line starts with the agent's own words: "/new session? \u2014 yes" would run the app's /new when the user presses Send.
        table = ["/new", "/yolo x", "/new session?", "/", "//", "/usr/local", " /new", "/ ", "\u200b/new", "\u202e/yolo", "\t/new\n", "/new\nsession", "Say /new", "run /clean"]
        r = js("""
          const out = [];
          for (const q of %s) {
            const c = mk(q, ["yes", "no"]);
            const msg = m.buildMessage([c], m.toggleOption({}, c, 0), "stem");
            out.push({ q: c.question, naive: c.question + " \\u2014 " + c.options[0], text: msg.text, compat: msg.compat, runs: m.runsAsCommand(c.question + " \\u2014 " + c.options[0]) });
          }
          return out;
        """ % json.dumps(table))
        commands = []
        for x in r:
            naive = x["naive"].strip()
            hostile = bool(SLASH_COMMAND_RE.match(naive))
            self.assertEqual(x["runs"], hostile, x)  # the module and the app's pattern agree
            self.assertIsNone(SLASH_COMMAND_RE.match(x["text"].strip()), x)  # what is sent never runs as a command
            if hostile:
                commands.append(x["q"])
                self.assertFalse(x["compat"], x)
                self.assertTrue(x["text"].startswith("Answers to the questions in widget `stem` (1):\n\n1. "), x)
            else:
                self.assertTrue(x["compat"], x)  # not a command in the app: the line agents expect, unchanged
                self.assertEqual(x["text"], x["naive"])
        # the table is not vacuous: these really are commands for the app's pattern
        for q in ("/new", "/yolo x", "/new session?", "/"):
            self.assertIn(q, commands)
        self.assertEqual(len(commands), 10)  # "//", "/usr/local", "Say /new" and "run /clean" are prose to the app and keep the compat line

    def test_golden_a_slash_question_before_and_after_and_an_ordinary_question_unchanged(self):
        r = js("""
          const hostile = mk("/new session?", ["yes", "no"]);
          const ordinary = mk("Which node should I restart first?", ["web-1", "web-2"]);
          return { slash: m.buildMessage([hostile], m.toggleOption({}, hostile, 0), "").text, slashStem: m.buildMessage([hostile], m.toggleOption({}, hostile, 0), "plan").text,
                   ordinary: m.buildMessage([ordinary], m.toggleOption({}, ordinary, 1), "plan") };
        """)
        # before this fix the first one was "/new session? \u2014 yes", which the app ran as a command
        self.assertEqual(r["slash"], "Answers to the questions in this widget (1):\n\n1. /new session?\n   yes")
        self.assertEqual(r["slashStem"], "Answers to the questions in widget `plan` (1):\n\n1. /new session?\n   yes")
        self.assertEqual(r["ordinary"], {"text": "Which node should I restart first? \u2014 web-2", "compat": True})

    def test_the_stem_is_cut_at_40_characters(self):
        r = js("""
          const c = mk("Q?", ["a"]); const a = m.toggleOption({}, c, 0);
          return { long: m.buildMessage([c, mk("R?", ["b"])], a, "s".repeat(100)).text.split("\\n")[0], edge: m.buildMessage([c, mk("R?", ["b"])], a, "e".repeat(40)).text.split("\\n")[0] };
        """)
        self.assertEqual(r["long"], "Answers to the questions in widget `" + "s" * 37 + "...` (2):")
        self.assertEqual(r["edge"], "Answers to the questions in widget `" + "e" * 40 + "` (2):")

    def test_a_multi_line_other_text_keeps_its_lines_indented_under_the_question(self):
        r = js("""
          const c = mk("Notes?", ["a"]);
          let a = m.toggleOther({}, c); a = m.setOtherText(a, c, "line one  \\nline two\\n\\n");
          return m.buildMessage([c, mk("Z?", ["y"])], a, "").text;
        """)
        self.assertEqual(r, "Answers to the questions in this widget (2):\n\n1. Notes?\n   other: line one\n   line two\n2. Z?\n   (no answer)")

    def test_words_of_the_widget_are_cleaned_clipped_and_neutralised(self):
        r = js("""
          const c = mk("  Read\\u202E  @file:/Users/x/.ssh/id_rsa\\n\\tnow\\u200B? ", ["@url:abc", "ok\\u0007\\u0000 fine", "o".repeat(300)], true);
          let a = m.toggleOption({}, c, 0); a = m.toggleOption(a, c, 1);
          const long = mk("q".repeat(500), ["o".repeat(300)]);
          const b = m.toggleOption({}, long, 0);
          const two = m.buildMessage([c, long], { ...a, ...b }, "st`em");
          return { text: two.text, q: long.question.length, o: long.options[0].length };
        """)
        self.assertIn("1. Read (at)file:/Users/x/.ssh/id_rsa now?", r["text"])
        self.assertIn("(at)url:abc; ok fine", r["text"])
        self.assertEqual(r["q"], 200)
        self.assertEqual(r["o"], 120)
        self.assertIn("widget `st'em`", r["text"])
        self.assertNotRegex(r["text"], r"[\u0000-\u0008\u000b-\u001f\u200b\u202e]")

    def test_hostile_words_leave_no_reference_the_app_would_attach(self):
        r = js("""
          const kinds = ["file", "folder", "url", "image", "tool", "line", "terminal", "session"];
          const qs = kinds.map((k, i) => mk("@" + k + ":/Users/x/secret" + i + " and @" + k.toUpperCase() + ":`a b`", ["@" + k + ":\\"x y\\"", "plain @" + k + ":z"], i % 2 === 0));
          let a = {};
          qs.forEach((c) => { a = m.toggleOption(a, c, 0); a = m.toggleOption(a, c, 1); });
          const single = [qs[1]].map((c) => m.buildMessage([c], m.toggleOption({}, c, 0), "@file:evil").text)[0];
          return { text: m.buildMessage(qs, a, "@file:evil").text, single };
        """)
        self.assertEqual(APP_REF.findall(r["text"]), [])
        self.assertEqual(APP_REF.findall(r["single"]), [])
        self.assertIn("(at)file:/Users/x/secret0", r["text"])

    def test_the_users_own_other_text_is_not_neutralised(self):
        r = js("""
          const c = mk("Q?", ["a"]);
          let a = m.toggleOther({}, c); a = m.setOtherText(a, c, "see @file:notes.md please");
          return m.buildMessage([c, mk("Z?", ["z"])], a, "").text;
        """)
        self.assertIn("other: see @file:notes.md please", r)


# What the hostile words are made of (the neutraliser table): the input and what neutralize() must write.
NEUTRAL = [
    ("@diff", "(at)diff"), ("@staged", "(at)staged"), ("@git:HEAD", "(at)git:HEAD"), ("@foo:bar", "(at)foo:bar"), ("@Diff", "(at)Diff"), ("@STAGED", "(at)STAGED"),
    ("@file:'a b'", "(at)file:'a b'"), ("@url:`page one`", "(at)url:`page one`"), ("@FILE:\"/etc/hosts\":3-9", "(at)FILE:\"/etc/hosts\":3-9"),
    ("@folder:/x", "(at)folder:/x"), ("@GiT:main~2", "(at)GiT:main~2"), ("@my-provider:thing", "(at)my-provider:thing"), ("@a_b:c", "(at)a_b:c"),
    ("abc@diff", "abc(at)diff"), ("abc@file:/x", "abc(at)file:/x"), ("(@staged)", "((at)staged)"), ("see @diff, then @staged.", "see (at)diff, then (at)staged."),
    ("@@foo:bar", "@(at)foo:bar"), ("@diff@staged", "(at)diff(at)staged"),
    # not references: an e-mail address, an at-sign before a space, a word that only starts like diff or staged
    ("me@host.test", "me@host.test"), ("mail me@host.test or @ home", "mail me@host.test or @ home"), ("price @ 5", "price @ 5"), ("@diffs", "@diffs"),
    ("@stagedx", "@stagedx"), ("@", "@"), ("a @ b", "a @ b"), ("@1:2", "@1:2"), ("@ file:x", "@ file:x"),
]


class Neutraliser(unittest.TestCase):
    def test_the_table_of_hostile_words(self):
        out = js("return %s.map((t) => n.neutralize(t[0]));" % json.dumps(NEUTRAL))
        for (src, want), got in zip(NEUTRAL, out):
            self.assertEqual(got, want, src)
        for (_src, want), got in zip(NEUTRAL, out):
            if "(at)" in want:
                self.assertEqual(refs(got), [], got)  # not the app's pattern, not the gateway's either

    def test_a_zero_width_character_inside_the_token_is_removed_before_the_at_sign_is_judged(self):
        r = js("""
          const c = m.makeChoice({ question: "Open @fi\\u200Ble:/x and @di\\u2060ff and @\\u200Bstaged and @fo\\u00ADo:bar?", options: ["@gi\\u200Dt:HEAD", "ok"] });
          return { q: c.question, o: c.options[0] };
        """)
        self.assertEqual(r["q"], "Open (at)file:/x and (at)diff and (at)staged and (at)foo:bar?")
        self.assertEqual(r["o"], "(at)git:HEAD")

    def test_the_e_mail_address_and_the_loose_at_sign_are_left_alone_in_a_message(self):
        r = js("""
          const c = m.makeChoice({ question: "Mail ops@host.test or ask @ home", options: ["me@host.test", "@ later"] });
          return { q: c.question, o: c.options, text: m.buildMessage([c], m.toggleOption({}, c, 0), "").text };
        """)
        self.assertEqual(r["q"], "Mail ops@host.test or ask @ home")
        self.assertEqual(r["o"], ["me@host.test", "@ later"])
        self.assertEqual(r["text"], "Mail ops@host.test or ask @ home \u2014 me@host.test")

    def test_a_message_built_from_hostile_words_has_no_match_of_the_apps_or_the_gateways_pattern(self):
        words = [t for t, _ in NEUTRAL] + ["@fi\u200ble:/x", "x @file:/y", "@file:'a b' and @url:`c d`", "@git: HEAD"]
        r = js("""
          const words = %s;
          const qs = words.map((w, i) => m.makeChoice({ question: "Q" + i + " " + w + " tail", options: [w, "plain " + w, "@diff"], multiple: i %% 2 === 0 }));
          let a = {};
          qs.forEach((c) => { a = m.toggleOption(a, c, 0); a = m.toggleOption(a, c, 1); a = m.toggleOption(a, c, 2); });
          const single = qs.map((c) => m.buildMessage([c], m.toggleOption({}, c, 0), "@diff").text);
          return { text: m.buildMessage(qs, a, "@staged@git:x").text, single };
        """ % json.dumps(words))
        self.assertGreater(len(r["text"]), 1000)
        self.assertEqual(refs(r["text"]), [])
        for line in r["single"]:
            self.assertEqual(refs(line), [], line)
        # the patterns are real: the same words, un-neutralised, do match (a copy of a pattern that matches nothing would prove nothing)
        raw = " ".join(words)
        self.assertGreaterEqual(len(GATEWAY_REF.findall(raw)), 6)
        self.assertGreaterEqual(len(GATEWAY_PLUGIN_REF.findall(raw)), 4)
        self.assertGreaterEqual(len(APP_REF.findall(raw)), 3)

    def test_the_users_own_other_text_keeps_its_at_sign(self):
        r = js("""
          const c = m.makeChoice({ question: "Q?", options: ["a"] });
          let a = m.toggleOther({}, c); a = m.setOtherText(a, c, "see @diff and @git:HEAD and @foo:bar and @file:notes.md");
          return m.buildMessage([c, m.makeChoice({ question: "Z?", options: ["z"] })], a, "").text;
        """)
        self.assertIn("other: see @diff and @git:HEAD and @foo:bar and @file:notes.md", r)

    def test_notes_inherit_the_same_rule(self):
        out = js("""return [n.cleanQuote("click @diff or @git:HEAD"), n.cleanLabel("a@b.test"), n.cleanText("@staged", 50)];""")
        self.assertEqual(out, ["click (at)diff or (at)git:HEAD", "a@b.test", "(at)staged"])


class Fit(unittest.TestCase):
    """Preview users cannot shorten the agent's questions, so over 500 characters the message is built again with each question clipped."""

    def many(self, n, size, mode="preview", opts=("yes", "no")):
        return js("""
          const qs = []; let a = {};
          for (let i = 0; i < %d; i++) { const c = mk("Q" + (i + 1) + " " + "w".repeat(%d - 3 - String(i + 1).length), %s); qs.push(c); a = m.toggleOption(a, c, 0); }
          const r = m.fitMessage(qs, a, "", %s);
          return { r, full: m.buildMessage(qs, a, "").text.length };
        """ % (n, size, json.dumps(list(opts)), json.dumps(mode)))

    def test_five_questions_of_100_characters_are_sent_clipped_to_50_in_preview(self):
        o = self.many(5, 100)
        self.assertGreater(o["full"], 500)
        r = o["r"]
        self.assertTrue(r["ok"])
        self.assertTrue(r["clipped"])
        self.assertLessEqual(len(r["text"]), 500)
        lines = r["text"].split("\n")
        self.assertEqual(lines[0], "Answers to the questions in this widget (5):")
        qlines = [l for l in lines if re.match(r"^\d+\. Q\d", l)]
        self.assertEqual(len(qlines), 5)
        for i, l in enumerate(qlines, 1):
            self.assertTrue(l.startswith("%d. Q%d w" % (i, i)), l)  # the numbers stay: they keep the mapping
            self.assertEqual(len(l) - len("%d. " % i), 50)
            self.assertTrue(l.endswith("..."), l)
        self.assertEqual(lines.count("   yes"), 5)

    def test_eight_questions_of_60_characters_fit_after_a_tighter_clip(self):
        o = self.many(8, 60)
        self.assertGreater(o["full"], 500)
        r = o["r"]
        self.assertTrue(r["ok"] and r["clipped"])
        self.assertLessEqual(len(r["text"]), 500)
        qlines = [l for l in r["text"].split("\n") if re.match(r"^\d+\. Q\d", l)]
        self.assertEqual(len(qlines), 8)
        self.assertTrue(all(l.endswith("...") for l in qlines))
        self.assertTrue(r["text"].startswith("Answers to the questions in this widget (8):"))

    def test_a_message_that_fits_is_not_clipped_and_native_never_clips(self):
        small = self.many(3, 40)["r"]
        self.assertTrue(small["ok"])
        self.assertFalse(small["clipped"])
        self.assertNotIn("...", small["text"])
        native = self.many(5, 100, mode="native")["r"]
        self.assertTrue(native["ok"])
        self.assertFalse(native["clipped"])
        self.assertIn("w" * 90, native["text"])  # the full questions
        self.assertGreater(len(native["text"]), 500)

    def test_a_message_that_cannot_fit_even_clipped_is_refused_with_the_existing_sentence(self):
        r = js("""
          const long = "A " + "x".repeat(118);
          const c = mk("Which checks should I run?", [long, long + "b", long + "c", long + "d", long + "e"], true);
          let a = {}; for (let i = 0; i < 5; i++) a = m.toggleOption(a, c, i);
          return { fit: m.fitMessage([c], a, "", "preview"), native: m.fitMessage([c], a, "", "native") };
        """)
        f = r["fit"]
        self.assertFalse(f["ok"])
        self.assertGreater(f["length"], 500)
        self.assertRegex(f["error"], r"^This answer is [\d,]+ characters and this display mode sends at most 500\. Shorten the answers\.$")
        self.assertTrue(r["native"]["ok"])

    def test_one_question_never_changes_its_wire_format(self):
        r = js("""
          const c = mk("q".repeat(200), ["o".repeat(120)]);
          return m.fitMessage([c], m.toggleOption({}, c, 0), "", "preview");
        """)
        self.assertTrue(r["ok"] and r["compat"] and not r["clipped"])  # 200 + 3 + 120 characters: under the cap, the compat line, never clipped


class Revive(unittest.TestCase):
    """A saved board keeps its "sent" flag only for exactly the set of questions it was made for."""

    SETUP = """
      const a1 = mk("Which node?", ["web-1", "web-2"]), a2 = mk("Drain it?", ["Yes", "No"]), a3 = mk("Clear the cache?", ["Yes", "No"]);
      let ans = m.toggleOption({}, a1, 0); ans = m.toggleOption(ans, a2, 1);
      const saved = JSON.parse(JSON.stringify({ answers: ans, sent: true, keys: m.keysOf([a1, a2]) }));
      const view = (b) => ({ sent: b.sent, answered: Object.keys(b.answers).length, keys: b.keys.length });
    """

    def test_the_same_set_stays_sent_in_any_order(self):
        r = js(self.SETUP + "return { same: view(m.reviveBoard(saved, [a1, a2])), swapped: view(m.reviveBoard(saved, [a2, a1])) };")
        self.assertEqual(r["same"], {"sent": True, "answered": 2, "keys": 2})
        self.assertEqual(r["swapped"], {"sent": True, "answered": 2, "keys": 2})

    def test_a_new_question_unlocks_the_board_and_keeps_the_answers_that_still_fit(self):
        r = js(self.SETUP + "return { added: view(m.reviveBoard(saved, [a1, a2, a3])), replaced: view(m.reviveBoard(saved, [a1, a3])) };")
        self.assertEqual(r["added"], {"sent": False, "answered": 2, "keys": 3})
        self.assertEqual(r["replaced"], {"sent": False, "answered": 1, "keys": 2})

    def test_a_removed_question_unlocks_it_too(self):
        r = js(self.SETUP + "return { removed: view(m.reviveBoard(saved, [a1])) };")
        self.assertEqual(r["removed"], {"sent": False, "answered": 1, "keys": 1})

    def test_a_different_set_and_a_board_saved_without_keys_are_not_sent(self):
        r = js(self.SETUP + """
          const old = { answers: saved.answers, sent: true };   // written by a build that did not store the keys
          return { other: view(m.reviveBoard(saved, [a3])), old: view(m.reviveBoard(old, [a1, a2])), live: view(m.reviveBoard(m.reviveBoard(saved, [a1, a2]), [a1, a2, a3])) };
        """)
        self.assertEqual(r["other"], {"sent": False, "answered": 0, "keys": 1})
        self.assertEqual(r["old"], {"sent": False, "answered": 2, "keys": 2})
        self.assertEqual(r["live"], {"sent": False, "answered": 2, "keys": 3})  # the board in memory, redrawn with a new question


class Guards(unittest.TestCase):
    def test_an_other_row_that_is_not_there_cannot_be_toggled_or_typed_into(self):
        r = js("""
          const c = mk("Q?", ["a", "b"], false, false);
          const start = {};
          return { toggled: m.toggleOther(start, c) === start, typed: m.setOtherText(start, c, "x") === start, c: [c.other] };
        """)
        self.assertEqual(r, {"toggled": True, "typed": True, "c": [False]})


class Limits(unittest.TestCase):
    def test_boundaries_500_preview_and_4000_native(self):
        r = js("""
          const at = (n, mode) => m.checkSize("x".repeat(n), mode);
          return { p500: at(500, "preview"), p501: at(501, "preview"), n4000: at(4000, "native"), n4001: at(4001, "native"), n501: at(501, "native"),
                   limits: [m.CHOICE_LIMITS.preview, m.CHOICE_LIMITS.native, m.CHOICE_LIMITS.question, m.CHOICE_LIMITS.option, m.CHOICE_LIMITS.other] };
        """)
        self.assertTrue(r["p500"]["ok"])
        self.assertFalse(r["p501"]["ok"])
        self.assertEqual(r["p501"]["error"], "This answer is 501 characters and this display mode sends at most 500. Shorten the answers.")
        self.assertTrue(r["n4000"]["ok"])
        self.assertTrue(r["n501"]["ok"])
        self.assertFalse(r["n4001"]["ok"])
        self.assertIn("4,000", r["n4001"]["error"])
        self.assertEqual(r["limits"], [500, 4000, 200, 120, 500])


class Store(unittest.TestCase):
    def test_board_is_kept_in_memory_and_session_storage_and_survives_a_broken_one(self):
        r = js("""
          const d = {};
          const mkStore = () => ({ getItem: (k) => (k in d ? d[k] : null), setItem: (k, v) => { d[k] = String(v); }, removeItem: (k) => { delete d[k]; } });
          const s1 = mkStore();
          const c = mk("Q?", ["a", "b", "c"], true);
          const board = { answers: m.toggleOption(m.toggleOption({}, c, 2), c, 0), sent: true, keys: m.keysOf([c]) };
          const a = m.createBoardStore(() => s1); a.set("wid", board);
          const b = m.createBoardStore(() => s1);              // a new store: only the storage remembers
          const raw = b.get("wid");
          const revived = m.reviveBoard(raw, [c]);
          const keys = Object.keys(d);
          const broken = { getItem() { throw new Error("no"); }, setItem() { throw new Error("no"); }, removeItem() { throw new Error("no"); } };
          const x = m.createBoardStore(() => broken); x.set("w", board);
          const y = m.createBoardStore(() => { throw new Error("blocked"); }); y.set("w", board);
          // the source changed: another question, so nothing matches and nothing is sent
          const other = mk("Different?", ["a"]);
          const stale = m.reviveBoard(raw, [other]);
          // junk in the storage
          d["hermes-openui:answers:junk"] = "{not json";
          const junk = m.reviveBoard(m.createBoardStore(() => s1).get("junk"), [c]);
          const wild = m.reviveBoard({ answers: { [c.key]: { picks: [9, -1, 1.5, "x", 1, 1, 0], other: "yes", text: 5 } }, sent: "true" }, [c]);
          const a2 = m.createBoardStore(() => s1); a2.set("wid", { answers: {}, sent: false, keys: m.keysOf([c]) });
          const cleared = Object.keys(d);
          return { keys, cleared, revived, memory: x.get("w").sent, noStorage: y.get("w").sent, stale, junk, wild };
        """)
        self.assertEqual(r["keys"], ["hermes-openui:answers:wid"])
        self.assertNotIn("hermes-openui:answers:wid", r["cleared"])  # a board with nothing staged and nothing sent removes its storage key, it does not keep an empty one
        key = next(iter(r["revived"]["answers"]))
        self.assertEqual(r["revived"]["answers"][key]["picks"], [0, 2])
        self.assertTrue(r["revived"]["sent"])
        self.assertTrue(r["memory"])
        self.assertTrue(r["noStorage"])
        self.assertEqual((r["stale"]["answers"], r["stale"]["sent"]), ({}, False))
        self.assertEqual((r["junk"]["answers"], r["junk"]["sent"]), ({}, False))
        wk = next(iter(r["wild"]["answers"]))
        self.assertEqual(r["wild"]["answers"][wk], {"picks": [0, 1], "other": False, "text": ""})
        self.assertFalse(r["wild"]["sent"])


class Validator(unittest.TestCase):
    """The validator and the reference line say how to write the new optional arguments, and the docs examples are what the browser tests draw."""
    VALIDATOR = ROOT / "assets" / "validate.cjs"

    def check(self, line):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "w.oui"
            f.write_text("root = Stack([c])\nc = " + line + "\n", encoding="utf-8")
            r = subprocess.run(["node", str(self.VALIDATOR), str(f)], capture_output=True, text=True, timeout=60, env=ENV)
        return r.returncode, r.stdout + r.stderr

    def test_the_old_and_the_new_forms_validate(self):
        for line in ('Choice("Q?", ["a", "b"])', 'Choice("Q?", ["a", "b"], "hint")', 'Choice("Q?", ["a", "b"], null, true)', 'Choice("Q?", ["a"], null, null, false)',
                     'Choice("Q?", ["a"], "hint", true, false)'):
            with self.subTest(line=line):
                self.assertEqual(self.check(line)[0], 0, line)

    def test_a_skipped_argument_written_wrong_is_explained_with_an_example(self):
        code, out = self.check('Choice("Q?", ["a", "b"], true)')  # multiple in the place of the hint
        self.assertNotEqual(code, 0)
        self.assertIn("write `null` for each skipped optional argument", out)
        self.assertIn('Choice("Which checks?", ["disk", "memory"], null, true)', out)

    def test_the_reference_line_has_the_signature_and_the_null_rule(self):
        line = [ln for ln in (ROOT / "assets" / "components.md").read_text(encoding="utf-8").splitlines() if ln.startswith("Choice(")][0]
        self.assertTrue(line.startswith("Choice(question: string, options: string[], hint?: string, multiple?: boolean, other?: boolean) "))
        for word in ("together", "nothing", "multiple: true", "Other", "other is false", "null", 'Choice("Which?", ["a", "b"], null, true)'):
            self.assertIn(word, line)

    def test_the_reference_line_says_what_the_agent_receives(self):
        line = [ln for ln in (ROOT / "assets" / "components.md").read_text(encoding="utf-8").splitlines() if ln.startswith("Choice(")][0]
        self.assertIn('as your next turn (numbered; "(no answer)" if skipped; "other: ..." if typed).', line)

    def test_the_skill_and_the_readme_do_not_say_a_choice_sends_by_itself(self):
        skill = (ROOT / "skills" / "openui-render" / "SKILL.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(skill), 5000)
        self.assertNotIn("and `Choice` send text back", skill)
        self.assertIn("A `Choice` sends nothing alone: put all questions in one widget, one Send button sends them.", skill)
        self.assertIn("(500 characters max)", skill)  # the Button keeps its 500
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("Buttons and choices send their text back", readme)
        self.assertIn("nothing is sent until you press **Send answers**", readme)

    def test_the_choice_page_says_what_the_card_does(self):
        page = (ROOT / "docs" / "ui-components" / "Choice.md").read_text(encoding="utf-8")
        self.assertNotIn("as in the app's own question card", page)
        self.assertIn("no letter shortcut", page)  # selecting needs no letter, and none is bound
        self.assertIn("bar reading 2 of 3 answered](images/choice-tabs.png)", page)  # the picture shows two answers
        for name in ("choice-basic", "choice-multiple", "choice-single-vs-multiple"):  # the tag says Choose one / Choose all that apply: the hint does not say it again
            self.assertNotRegex((ROOT / "docs" / "ui-components" / "examples" / (name + ".oui")).read_text(encoding="utf-8"), r"(?i)(choose|pick) (one|any|all)")
        for old in ("Pick one", "Pick any", "letter badge", "badges", "aria-pressed"):  # the old look and markup are not described any more
            self.assertNotIn(old, page)
        for new in ("Choose one", "Choose all that apply", "Single and multiple", "images/choice-single-vs-multiple.png", "../images/choice-single-vs-multiple-light.png"):
            self.assertIn(new, page)

    def test_the_documentation_examples_are_the_sources_the_browser_tests_draw(self):
        import choice_probe as CP
        ex = ROOT / "docs" / "ui-components" / "examples"
        self.assertEqual((ex / "choice-card-questions.oui").read_text(encoding="utf-8"), CP.SOURCES["cq"])
        self.assertEqual((ex / "choice-tabs.oui").read_text(encoding="utf-8"), CP.SOURCES["tabs"])


if __name__ == "__main__":
    unittest.main()
