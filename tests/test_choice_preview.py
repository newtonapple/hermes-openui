"""Choice batch card in real Chrome, PREVIEW mode: the page render_widget writes, driven through tools/shoot.py --steps with real mouse and key
events; window.hermes.send is a stub that records (the app's hidden turn). Plus an exported page, which has no chat to send to.
Opt in: OPENUI_TEST_CHROME=1 python3 -m unittest tests.test_choice_preview. One Chrome launch per page: seven in all (the question card has a light run of its own).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import choice_probe as CP  # noqa: E402
from choice_probe import PREVIEW_HELPERS, Prog  # noqa: E402

CHROME = os.environ.get("OPENUI_TEST_CHROME") == "1"
ONLY = {n for n in os.environ.get("CHOICE_PREVIEW_ONLY", "").split(",") if n}  # debugging: draw only these pages (cq, tabs, one, long, fit, light, export); the other tests skip


class Pages(dict):
    def __missing__(self, key):
        raise unittest.SkipTest("the page %r was not drawn in this run (CHOICE_PREVIEW_ONLY)" % key)


def card_program():
    p = Prog()
    p.js(PREVIEW_HELPERS).st("idle", "x").ev("look_idle", "__C.look('x')")
    p.opt("x", 0, 1).st("pick", "x").ev("sent0", "__C.calls()")
    p.opt("x", 0, 1).opt("x", 0, 0).opt("x", 0, 1).st("moved", "x")  # on, off, on another: single mode
    p.opt("x", 1, 0).opt("x", 1, 2).st("multi", "x").ev("look_multi", "__C.look('x')")
    p.opt("x", 0, 2).st("other_open", "x")  # Other opens a focused box and replaces the option
    p.type("mine").st("other_typed", "x")
    p.opt("x", 1, 3).ev("look_other", "__C.look('x')")  # the Other row of the multiple question too (empty: it adds nothing to the message)
    p.js("window.__log = []; document.addEventListener('dblclick', function (e) { window.__log.push(e.target.tagName); })")
    p.dblclick("x", -1, "[data-oui-send]").ev("sent1", "__C.calls()").st("sent", "x")
    p.opt("x", 1, 1).st("locked_click", "x").ev("look_sent", "__C.look('x')").ev("marks_final", "__C.rects('x')")
    return p.steps


def tabs_program():
    p = Prog()
    p.js(PREVIEW_HELPERS).st("idle", "x")
    p.opt("x", 0, 0).click_text("x", "Cleanup").opt("x", 0, 1).st("second", "x")
    p.click_text("x", "Restart").st("back", "x")
    p.send("x").ev("sent", "__C.calls()").st("after", "x")
    return p.steps


def one_program():
    p = Prog()
    p.js(PREVIEW_HELPERS).st("idle", "x").opt("x", 0, 1).st("staged", "x").send("x").ev("sent", "__C.calls()").st("after", "x")
    return p.steps


def long_program():
    p = Prog()
    p.js(PREVIEW_HELPERS)
    for o in range(5):
        p.opt("x", 0, o)
    p.st("staged", "x").send("x").st("refused", "x").ev("sent", "__C.calls()")
    p.opt("x", 0, 4).opt("x", 0, 3).opt("x", 0, 2).st("shorter", "x").send("x").st("ok", "x").ev("sent2", "__C.calls()")
    return p.steps


def fit_program():
    p = Prog()
    p.js(PREVIEW_HELPERS).st("idle", "x")
    for q in range(5):
        p.opt("x", q, 0)
    p.st("staged", "x").send("x").ev("sent", "__C.calls()").st("after", "x")
    return p.steps


def export_program():
    p = Prog()
    p.js(PREVIEW_HELPERS).st("idle", "x").opt("x", 0, 1).st("staged", "x").send("x").st("clicked", "x")
    p.ev("note_hidden", "document.getElementById('oui-note').hidden")
    return p.steps


@unittest.skipUnless(CHROME, "set OPENUI_TEST_CHROME=1 (needs Chrome and Node)")
class PreviewChoice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import shoot
        try:
            shoot.find_chrome(None)
        except SystemExit:
            raise unittest.SkipTest("no Chrome found (set $CHROME)")
        cls.td = Path(tempfile.mkdtemp())
        cls.r = Pages()
        for name, prog in (("cq", card_program), ("tabs", tabs_program), ("one", one_program), ("long", long_program), ("fit", fit_program)):
            if ONLY and name not in ONLY:
                continue
            f = cls.td / (name + ".oui")
            f.write_text(CP.PREVIEW_FIT if name == "fit" else CP.SOURCES[name], encoding="utf-8")
            got, out = CP.shoot_oui(f, cls.td / (name + ".png"), prog())
            cls.r[name] = {k: json.loads(v) if isinstance(v, str) else v for k, v in got.items()}
        if not ONLY or "light" in ONLY:  # the same question card in the light theme: the indicators walk of tests/choice_probe.py
            f = cls.td / "light.oui"
            f.write_text(CP.SOURCES["cq"], encoding="utf-8")
            got, out = CP.shoot_oui(f, cls.td / "light.png", CP.indicator_program("x"), theme="light")
            cls.r["light"] = {k: json.loads(v) if isinstance(v, str) else v for k, v in got.items()}
        if ONLY and "export" not in ONLY:
            return
        page, _lint, _b, _p = shoot.load_modules()
        html, _ = page.build_export_page([{"title": "Questions", "source": CP.SOURCES["one"]}], theme="dark")
        (cls.td / "export.html").write_text(html, encoding="utf-8")
        got, out = CP.NP.shoot_page(cls.td / "export.html", cls.td / "export.png", 700, export_program(), scale=1)
        cls.r["export"] = {k: json.loads(v) if isinstance(v, str) else v for k, v in got.items()}
        cls.export_out = out

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.td, ignore_errors=True)

    def test_a_click_stages_and_does_not_send_and_the_bar_counts(self):
        r = self.r["cq"]
        self.assertEqual(r["idle"]["count"], "0 of 3 answered")
        self.assertEqual(r["pick"]["q"][0]["checked"], "010")
        self.assertEqual(r["pick"]["count"], "1 of 3 answered")
        self.assertEqual(r["sent0"], [])
        self.assertEqual(r["moved"]["q"][0]["checked"], "010")
        self.assertEqual(r["multi"]["q"][1]["checked"], "1010")
        self.assertEqual(r["multi"]["count"], "2 of 3 answered")
        self.assertIsNone(r["idle"]["store"])  # a preview page keeps the board for the life of the page only

    def test_single_and_multiple_questions_have_different_indicators_in_the_dark_theme(self):
        r = self.r["cq"]
        kinds = ["single", "multiple", "single"]
        for k in ("look_idle", "look_multi", "look_other"):
            CP.check_indicators(self, r[k], kinds)
        CP.check_indicators(self, r["look_sent"], kinds, locked=True)
        dimmed = [(i, x["label"]) for i, q in enumerate(r["look_sent"]) for x in q["rows"] if x["checked"] == "true" and x["opacity"] < 1]
        self.assertEqual(dimmed, [(1, "Other...")])  # the empty Other row of the multiple question: checked, still filled, but not an answer so dimmed like the unchosen rows
        self.assertEqual([[x["role"] for x in q["rows"]] for q in r["look_idle"]], [["radio"] * 3, ["checkbox"] * 4, ["radio"] * 2])
        self.assertEqual({x["checked"] for q in r["look_idle"] for x in q["rows"]}, {"false"})
        self.assertEqual([[x["checked"] for x in q["rows"]] for q in r["look_other"]][:2], [["false", "false", "true"], ["true", "false", "true", "true"]])
        self.assertTrue(r["look_other"][0]["rows"][2]["dot"] and r["look_other"][1]["rows"][3]["check"])  # both Other rows match their mode
        CP.check_shapes_in_picture(self, self.td / "cq.png", [m for card in r["marks_final"] for m in card])

    def test_the_light_theme_has_the_same_indicators_and_enough_contrast(self):
        r = self.r["light"]
        kinds = ["single", "multiple", "single"]
        for k in ("look_idle", "look_multi", "look_other"):
            CP.check_indicators(self, r[k], kinds)
        CP.check_indicators(self, r["look_sent"], kinds, locked=True)
        CP.check_shapes_in_picture(self, self.td / "light.png", [m for card in r["marks_final"] for m in card])

    def test_other_opens_a_focused_box_and_empty_is_not_an_answer(self):
        r = self.r["cq"]
        q = r["other_open"]["q"][0]
        self.assertEqual((q["checked"], q["ta"]["focused"], q["ta"]["ph"]), ("001", True, "Type your own answer"))
        self.assertEqual(r["other_open"]["count"], "1 of 3 answered")
        self.assertEqual(r["other_typed"]["count"], "2 of 3 answered")

    def test_send_is_one_hidden_turn_and_a_double_click_sends_once_then_everything_locks(self):
        r = self.r["cq"]
        self.assertEqual(r["sent1"], ["Answers to the questions in this widget (3):\n\n1. Which node should I restart first?\n   other: mine\n"
                                      "2. Which checks should I run?\n   Disk; Network\n3. Clear the cache on db?\n   (no answer)"])
        s = r["sent"]
        self.assertEqual(s["count"], "Sent to the agent.")
        self.assertEqual([q["disabled"] for q in s["q"]], ["111", "1111", "11"])
        self.assertEqual(r["locked_click"]["q"][1]["checked"], s["q"][1]["checked"])

    def test_tabs_keep_answers_and_a_tab_never_shown_is_counted_and_listed(self):
        r = self.r["tabs"]
        self.assertEqual(r["idle"]["count"], "0 of 3 answered")
        self.assertEqual(r["second"]["count"], "2 of 3 answered")
        self.assertEqual(r["back"]["q"][0]["checked"], "100")
        self.assertEqual(r["sent"], ["Answers to the questions in this widget (3):\n\n1. Which node should I restart first?\n   web-1\n"
                                     "2. Drain the node first?\n   (no answer)\n3. Clear the cache on db?\n   No"])
        self.assertEqual(r["after"]["count"], "Sent to the agent.")

    def test_one_question_keeps_the_wire_format_byte_for_byte(self):
        r = self.r["one"]
        self.assertEqual(r["idle"]["count"], "0 of 1 answered")
        self.assertEqual(r["sent"], ["Which node should I restart first? \u2014 web-2"])
        self.assertEqual(r["after"]["count"], "Sent to the agent.")

    def test_preview_stops_at_500_characters_says_so_and_sends_again_when_shorter(self):
        r = self.r["long"]
        self.assertRegex(r["refused"]["alert"], r"^This answer is \d+ characters and this display mode sends at most 500\. Shorten the answers\.$")
        self.assertEqual(r["sent"], [])
        self.assertFalse(r["refused"]["send"]["dis"])  # nothing locked
        self.assertIsNone(r["ok"]["alert"])
        self.assertEqual(len(r["sent2"]), 1)
        self.assertLessEqual(len(r["sent2"][0]), 500)
        self.assertEqual(r["ok"]["count"], "Sent to the agent.")

    def test_five_long_questions_are_sent_clipped_in_preview_instead_of_refused(self):
        r = self.r["fit"]
        self.assertEqual(r["staged"]["count"], "5 of 5 answered")
        self.assertEqual(len(r["sent"]), 1)
        text = r["sent"][0]
        self.assertLessEqual(len(text), 500)
        lines = text.split("\n")
        self.assertEqual(lines[0], "Answers to the questions in this widget (5):")
        qlines = [l for l in lines if l[:1].isdigit()]
        self.assertEqual([l.split(".")[0] for l in qlines], ["1", "2", "3", "4", "5"])  # the numbers keep the mapping
        self.assertTrue(all(l.endswith("...") and len(l) - 3 == 50 for l in qlines), qlines)  # "N. " plus 50 characters, ending in "..."
        self.assertEqual(lines.count("   yes"), 5)
        self.assertIsNone(r["staged"]["alert"])
        self.assertEqual(r["after"]["count"], "Sent to the agent.")

    def test_an_exported_page_can_look_but_not_send(self):
        r = self.r["export"]
        self.assertEqual(r["staged"]["q"][0]["checked"], "0100")  # options are usable for looking
        self.assertTrue(r["staged"]["send"]["dis"])
        self.assertIn("Interactive buttons work inside Hermes only", r["staged"]["barText"])
        self.assertEqual(r["clicked"]["count"], "1 of 1 answered")  # a click on the disabled button did nothing
        self.assertTrue(r["note_hidden"])  # the shim's toast was not raised: nothing tried to send
        self.assertEqual(r["clicked"]["bars"], 1)


if __name__ == "__main__":
    unittest.main()
