"""Choice batch card in real Chrome: the real desktop/plugin.js in the native harness (stub SDK, the app's stylesheet inlined), driven through
tools/shoot.py --steps with REAL mouse and key events. Opt in: OPENUI_TEST_CHROME=1 python3 -m unittest tests.test_choice_native

ONE page and ONE Chrome launch run every case in a row (program() below); the tests then assert on the values it recorded. The stub composer records
what host.composer.submit was given; the page replays the app's own rules for the double-click heart (isTapbackDoubleClick) and the composer's
type-to-focus. Not covered: the real app, touch, screen readers, a real IME.
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
from choice_probe import HELPERS, OTHER500, Prog  # noqa: E402

CHROME = os.environ.get("OPENUI_TEST_CHROME") == "1"

CQ_MESSAGE = ("Answers to the questions in widget `cq` (3):\n\n1. Which node should I restart first?\n   other: mine\n   again\n"
              "2. Which checks should I run?\n   Disk; Network\n3. Clear the cache on db?\n   (no answer)")
ONE_MESSAGE = "Which node should I restart first? \u2014 web-2"
# (the marker on the chat surface around the widget, the runtime id of the session the main chat shows) -> the address the message is sent to
ROUTES = [("tile:stored-7", "ignored"), ("main", "run-42"), ("main", None), (None, None)]


def program():
    p = Prog()
    names = CP.NAMES
    idx = lambda n: names.index(n)  # noqa: E731
    p.js(HELPERS)
    for w in ("cq", "tabs", "tabs2", "one", "plain"):
        p.st("idle_" + w, w)
    p.ev("look_idle", "__C.look('cq')").ev("look_mo_idle", "__C.look('mo')")
    # --- a click stages, it does not send; a second click unselects; another option moves the pick (single mode)
    p.opt("cq", 0, 1).st("pick", "cq").ev("calls_after_pick", "__C.calls()")
    p.opt("cq", 0, 1).st("unpick", "cq")
    p.opt("cq", 0, 0).opt("cq", 0, 1).st("moved", "cq")
    # --- multiple: options toggle independently
    p.opt("cq", 1, 0).opt("cq", 1, 2).st("multi", "cq").ev("look_multi", "__C.look('cq')")
    # --- keyboard: one tab stop per question (Tab from the first question lands on the second), arrows, the badge letters, Space and Enter
    p.focus("cq", 0, '[data-oui-opt="1"]').key("Tab").st("tab_next", "cq")
    # no letter shortcut: the app's type-to-focus is a CAPTURE-phase listener on window, so a letter on a row would both toggle it and be typed into the composer
    p.focus("cq", 1, '[data-oui-opt="0"]').ev("steal0", "__C.steal()").ev("bubbled0", "__C.bubbled().length")
    p.key("a").st("key_a", "cq")
    p.ev("steal_a", "__C.steal()")
    p.key("ArrowDown").st("key_down", "cq")
    p.key("Space").st("key_space", "cq")
    p.key("Enter").st("key_enter", "cq")
    p.ev("steal_activate", "__C.steal()")  # arrows, Space and Enter on a button: not the composer's either
    p.key("c").st("key_c1", "cq").key("c").st("key_c2", "cq")
    p.ev("steal_handled", "__C.steal()").ev("bubbled1", "__C.bubbled().slice(-6)").keys("keys_handled", 9)
    p.key("Escape").keys("esc_on_option")  # nothing to close here: left alone
    # --- Other (single question): opens a text box, focuses it, replaces the option; empty is not an answer
    p.opt("cq", 0, 2).st("other_open", "cq").ev("look_other", "__C.look('cq')")
    p.ev("steal1", "__C.steal()").type("mine").ev("steal2", "__C.steal()").st("other_typed", "cq")
    p.key("Shift+Enter").type("again").st("other_lines", "cq")
    p.ev("dbl_before", "[__C.hearts(), __C.dbl()]")
    p.dblclick("cq", 0, "textarea").ev("dbl_textarea", "[__C.hearts(), __C.dbl()]")
    p.dblclick("cq", 2, '[data-oui-opt="0"]').ev("dbl_option", "[__C.hearts(), __C.dbl()]").st("after_dbl_option", "cq")
    p.dblclick("cq", 2, "div[id]").ev("dbl_question", "[__C.hearts(), __C.dbl()]")  # the question text: the app's heart (a control for the recorder)
    p.js("document.getSelection().removeAllRanges()")
    p.click("cq", 0, "textarea").key("Escape").keys("esc_in_ta").ev("focus_after_esc", "document.activeElement.tagName")
    p.click("cq", 0, "textarea").key("Enter").st("enter_next", "cq").keys("enter_key")
    p.click("cq", 0, "textarea").key("Tab").st("tab_from_ta", "cq")
    # --- the app's stylesheet: controls are user-select:none, the question and the text box are selectable and typeable
    p.ev("select", """(function () {
      var c = __C.cards('cq')[0], q = c.querySelector('div[id]'), ta = c.querySelector('textarea'), b = c.querySelector('[data-oui-opt]');
      var sel = getSelection(), r = document.createRange(); sel.removeAllRanges(); r.selectNodeContents(q); sel.addRange(r); var picked = String(sel); sel.removeAllRanges();
      ta.focus(); ta.select(); var tsel = ta.value.substring(ta.selectionStart, ta.selectionEnd); ta.setSelectionRange(0, 0);
      return { button: getComputedStyle(b).userSelect, question: getComputedStyle(q).userSelect, ta: getComputedStyle(ta).userSelect, picked: picked, qtext: q.textContent, tsel: tsel, taValue: ta.value };
    })()""")
    # --- send (a partial answer: the third question is not answered); a double-click sends once
    p.st("before_send", "cq")
    p.dblclick("cq", -1, "[data-oui-send]").ev("calls_cq", "__C.calls()").st("sent_cq", "cq").ev("look_sent", "__C.look('cq')")
    p.opt("cq", 1, 1).st("after_locked_click", "cq")
    p.ev("clear_none", "!!__C.root('cq').querySelector('[data-oui-send],[data-oui-clear]')")
    # --- a multiple question: its Other row is a checkbox too
    p.opt("mo", 0, 0).opt("mo", 0, 2).type("another").ev("look_mo", "__C.look('mo')").send("mo").ev("look_mo_sent", "__C.look('mo')")
    # --- the transcript unmounts and remounts the widget: the answers and the sent flag are kept (memory and sessionStorage)
    p.js("__unmount(%d)" % idx("cq")).js("__mount(%d)" % idx("cq")).wait().wait().st("remounted_cq", "cq")
    # --- tabs: an answer survives a tab switch; a question on a tab never shown counts
    p.opt("tabs", 0, 0).st("tabs_one", "tabs")
    p.click_text("tabs", "Cleanup").opt("tabs", 0, 1).st("tabs_second", "tabs")
    p.click_text("tabs", "Restart").st("tabs_back", "tabs")
    p.js("__unmount(%d)" % idx("tabs")).js("__mount(%d)" % idx("tabs")).wait().wait().st("tabs_remounted", "tabs")
    p.opt("tabs2", 0, 0).st("tabs2_one", "tabs2").send("tabs2").ev("calls_tabs2", "__C.calls().slice(-1)[0]").st("tabs2_sent", "tabs2")
    # --- the one-question wire format
    p.opt("one", 0, 1)
    p.st("one_staged", "one").send("one").ev("calls_one", "__C.calls().slice(-1)[0]").st("one_sent", "one")
    # --- caps: over 500 sends in native (4,000); over 4,000 is refused and says so; a Button stays at 500
    for o in range(5):
        p.opt("long", 0, o)
    p.st("long_staged", "long").send("long").ev("calls_long", "[__C.calls().slice(-1)[0].length, __C.calls().length]").st("long_sent", "long")
    for q in range(8):
        p.opt("huge", q, 2).type(OTHER500)
    p.st("huge_staged", "huge").send("huge").st("huge_refused", "huge").ev("calls_after_huge", "__C.calls().length")
    p.click("huge", -1, "[data-oui-clear]").st("huge_cleared", "huge")
    for b, label in enumerate(("Long", "Edge", "Over", "Ok")):
        p.click_text("btn", label).ev("btn%d" % b, "__C.calls().map(function (t) { return t.length; })")
    # --- notes mode: the Choice, its box and the bar are inert; a neighbouring Table can still be noted
    p.opt("nt", 0, 0).st("nt_staged", "nt")
    p.click("nt", -1, "[data-oui-chip]").st("nt_mode", "nt")
    p.ev("nt_mode_attr", "__C.root('nt').hasAttribute('data-oui-mode')")
    p.opt("nt", 0, 1).click("nt", -1, "[data-oui-send]").st("nt_inert", "nt")
    p.click("nt", -1, "td").ev("nt_editor", "!!__C.root('nt').querySelector('[data-oui-editor]')").ev("calls_nt", "__C.calls().length")
    p.key("Escape").key("Escape").ev("nt_mode_off", "__C.root('nt').hasAttribute('data-oui-mode')")
    p.opt("nt", 0, 1).st("nt_after", "nt")
    # --- which chat: the bar and a Button name the chat that HOLDS the widget (data-composer-target on an ancestor, set by the app on every chat surface)
    def route(w, target, active):
        attr = "c.removeAttribute('data-composer-target');" if target is None else "c.setAttribute('data-composer-target'," + json.dumps(target) + ");"
        p.js("(function(){var c=document.querySelector('[data-widget=\"%s\"]');%s window.__activeSessionId=%s;})()" % (w, attr, json.dumps(active)))
    for i, (target, active) in enumerate(ROUTES, 1):
        route("r%d" % i, target, active)
        p.opt("r%d" % i, 0, 0).send("r%d" % i)
        if i == 1:
            p.st("r1_sent", "r1")
    p.ev("route_args", "__C.args().slice(-4)")
    p.ev("route_sent", "[1, 2, 3, 4].map(function (i) { return __C.st('r' + i).count; })")
    for i, (target, active) in enumerate(ROUTES, 1):
        route("brt", target, active)
        p.click_text("brt", ("Web", "Api", "Db", "Cache")[i - 1])
    p.ev("route_btn_args", "__C.args().slice(-4)")
    # --- the host refuses (no chat input took the message): today's sentence, nothing locked, and the next try goes through
    p.js("window.__submitResult = false")
    p.opt("rf", 0, 0).send("rf").st("rf_refused", "rf").ev("rf_args", "__C.args().slice(-1)")
    p.js("window.__submitResult = true")
    # the focus is on an option of ANOTHER widget when the answers go out (a programmatic click on Send): it must stay there
    p.focus("nt", 0, '[data-oui-opt="0"]')
    p.js("__C.root('rf').querySelector('[data-oui-send]').click()").wait().st("rf_ok", "rf").ev("rf_args2", "__C.args().slice(-1)")
    # --- a widget redrawn under the same name with another set of questions arrives unlocked, with the answer that still fits
    p.opt("st", 0, 0).send("st").st("st_sent", "st")
    p.js("__sources.st = %s" % json.dumps(CP.ST_REDRAWN)).js("__unmount(%d)" % idx("st")).js("__mount(%d)" % idx("st")).wait().wait().st("st_redrawn", "st")
    p.ev("marks_final", "__C.rects('cq')")  # where the indicators of the card are in the picture this run ends with
    return p.steps


@unittest.skipUnless(CHROME, "set OPENUI_TEST_CHROME=1 (needs Chrome and Node)")
class NativeChoice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import shoot
        try:
            shoot.find_chrome(None)
        except SystemExit:
            raise unittest.SkipTest("no Chrome found (set $CHROME)")
        cls.td = tempfile.mkdtemp()
        page = CP.build_page(cls.td, [640], CP.NAMES, app_css=CP.app_css())
        cls.png = Path(cls.td) / "choice.png"
        cls.r, cls.out = CP.run(page, cls.png, 640 + 24, program(), scale=1)
        Path(os.environ.get("CHOICE_RECORD", os.path.join(cls.td, "record.json"))).write_text(json.dumps(cls.r, indent=1), encoding="utf-8")
        cls.j = {k: json.loads(v) if isinstance(v, str) else v for k, v in cls.r.items()}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.td, ignore_errors=True)

    def test_the_run_has_no_console_errors(self):
        self.assertIn("console errors: 0", self.out)
        self.assertIn("failed requests: 0", self.out)

    def test_idle_every_question_is_counted_even_on_a_tab_never_shown(self):
        j = self.j
        self.assertEqual(j["idle_cq"]["count"], "0 of 3 answered")
        self.assertEqual(j["idle_tabs"]["count"], "0 of 3 answered")  # two on the first tab, one on a tab nobody opened
        self.assertEqual(len(j["idle_tabs"]["q"]), 2)  # only the shown tab is mounted: the count came from the parsed tree
        self.assertEqual(j["idle_one"]["count"], "0 of 1 answered")
        self.assertTrue(j["idle_cq"]["send"]["dis"])
        self.assertIsNone(j["idle_plain"]["count"])  # a widget with no Choice has no bar
        self.assertEqual(j["idle_cq"]["bars"], 1)

    def test_a_click_selects_without_sending_and_a_second_click_unselects(self):
        j = self.j
        self.assertEqual(j["pick"]["q"][0]["checked"], "010")
        self.assertEqual(j["pick"]["count"], "1 of 3 answered")
        self.assertEqual(j["calls_after_pick"], [])
        self.assertEqual(j["unpick"]["q"][0]["checked"], "000")  # the Other row is a third button: nothing is pressed
        self.assertEqual(j["moved"]["q"][0]["checked"], "010")  # single mode: picking another moves the selection
        self.assertEqual(j["multi"]["q"][1]["checked"], "1010")  # multiple: independent toggles (three options and Other)
        self.assertEqual([q["tag"] for q in j["multi"]["q"]], ["Choose one", "Choose all that apply", "Choose one"])

    def test_the_markup_names_the_group_and_the_roles(self):
        q = self.j["idle_cq"]["q"]
        self.assertEqual([x["group"] for x in q], ["radiogroup:Which node should I restart first?", "group:Which checks should I run?", "radiogroup:Clear the cache on db?"])
        self.assertEqual([x["roles"] for x in q], ["radio,radio,radio", "checkbox,checkbox,checkbox,checkbox", "radio,radio"])  # the Other row has its question's role; other:false has none
        self.assertEqual([x["pressedAttr"] for x in q], [0, 0, 0])  # aria-pressed is gone
        self.assertEqual([x["marktext"] for x in q], ["", "", ""])  # no letters: the indicator holds no text
        self.assertEqual(self.j["idle_cq"]["shortcuts"], 0)  # and nothing is advertised as a keyboard shortcut
        self.assertEqual([x["tabstops"] for x in q], [1, 1, 1])  # one tab stop per question

    def test_the_keyboard(self):
        j = self.j
        self.assertEqual(j["tab_next"]["focus"], "BUTTON#opt2:1")  # Tab goes to the next question (its last used row)
        # No letter shortcut. The app's type-to-focus (a capture-phase listener on window, which the stand-in in tests/choice_probe.py copies) takes every letter
        # before the card could stop it, so the card must not ALSO act on one: the row does not change, and the key is neither prevented nor stopped.
        self.assertEqual(j["key_a"]["q"][1]["checked"], "1010")
        self.assertEqual(j["steal_a"], j["steal0"] + 1)  # the stand-in saw the letter in the capture phase (it would go to the composer), as it must
        self.assertEqual(j["key_down"]["focus"], "BUTTON#opt1:1")  # the arrows move between the options
        self.assertEqual(j["key_space"]["q"][1]["checked"], "1110")  # Space toggles
        self.assertEqual(j["key_enter"]["q"][1]["checked"], "1010")  # Enter toggles
        self.assertEqual(j["steal_activate"], j["steal_a"])  # arrows, Space and Enter on a button are not the composer's (isActivateOnEnterTarget)
        self.assertEqual((j["key_c1"]["q"][1]["checked"], j["key_c2"]["q"][1]["checked"]), ("1010", "1010"))
        self.assertEqual(j["steal_handled"], j["steal_activate"] + 2)
        letters = [k for k in j["keys_handled"] if k["k"] in ("a", "c")]
        self.assertEqual(len(letters), 3)
        self.assertTrue(all(k["dp"] is False for k in letters), letters)  # a letter is left alone: not prevented
        self.assertEqual([k for k in j["bubbled1"] if k in ("a", "c")], ["a", "c", "c"])  # and not stopped: a bubble-phase listener on document still gets every letter
        self.assertEqual(j["esc_on_option"], [{"k": "Escape", "dp": False, "t": "BUTTON"}])  # Escape that closes nothing is left alone

    def test_other_opens_a_focused_text_box_and_empty_is_not_an_answer(self):
        j = self.j
        q = j["other_open"]["q"][0]
        self.assertEqual(q["checked"], "001")  # single mode: Other replaced the option
        self.assertEqual((q["ta"]["ph"], q["ta"]["max"], q["ta"]["focused"], q["ta"]["value"]), ("Type your own answer", 500, True, ""))
        self.assertIn("Empty, so this question counts as not answered.", q["ta"]["note"])
        self.assertEqual(j["other_open"]["count"], "1 of 3 answered")  # the multiple question has answers, the open empty Other has none
        self.assertEqual(j["other_typed"]["count"], "2 of 3 answered")
        self.assertEqual(j["other_typed"]["q"][0]["ta"]["value"], "mine")
        self.assertEqual(j["steal2"], j["steal1"])  # typing in the box leaks nothing to the composer's type-to-focus
        self.assertEqual(j["other_lines"]["q"][0]["ta"]["value"], "mine\nagain")  # Shift+Enter is a new line
        self.assertGreater(j["other_lines"]["q"][0]["ta"]["h"], j["other_typed"]["q"][0]["ta"]["h"])  # and the box grows
        self.assertEqual(j["esc_in_ta"], [{"k": "Escape", "dp": True, "t": "TEXTAREA"}])  # Escape blurs the box and says it handled it
        self.assertEqual(j["focus_after_esc"], "BODY")
        self.assertEqual(j["enter_next"]["focus"], "BUTTON#opt1:1")  # Enter moves to the next question (the row last used there: Space and Enter toggled the second) and does not send
        self.assertEqual(j["enter_key"][0]["dp"], True)
        self.assertEqual(j["calls_after_pick"], [])
        self.assertEqual(j["tab_from_ta"]["focus"], "BUTTON#opt1:1")

    def test_double_click_on_a_control_does_not_heart_the_message(self):
        j = self.j
        self.assertEqual(j["dbl_before"], [0, 0])
        self.assertEqual(j["dbl_textarea"][0], 0)
        self.assertEqual(j["dbl_option"][0], 0)
        self.assertGreater(j["dbl_option"][1], j["dbl_before"][1])  # the recorder saw the double-click events (a button is exempt, not invisible)
        self.assertEqual(j["after_dbl_option"]["q"][2]["checked"], "00")  # two clicks: on, off
        self.assertEqual(j["dbl_question"][0], 1)  # a control sample: the question text is not exempt, in the app too

    def test_the_apps_stylesheet_leaves_the_question_and_the_box_selectable(self):
        s = self.j["select"]
        self.assertEqual(s["button"], "none")  # the app's rule for buttons stands
        self.assertEqual(s["picked"], s["qtext"])
        self.assertEqual(s["tsel"], s["taValue"])
        self.assertIn(s["ta"], ("text", "auto", "contain"))

    def test_send_is_one_message_listing_the_unanswered_and_a_double_click_sends_once(self):
        j = self.j
        self.assertEqual(j["before_send"]["count"], "2 of 3 answered")
        self.assertEqual(j["calls_cq"], [CQ_MESSAGE])
        s = j["sent_cq"]
        self.assertEqual(s["count"], "Sent to the agent.")
        self.assertIsNone(s["send"])
        self.assertEqual([q["disabled"] for q in s["q"]], ["111", "1111", "11"])
        self.assertEqual(s["q"][0]["ta"]["ro"], True)
        self.assertEqual(s["q"][0]["ta"]["value"], "mine\nagain")
        self.assertEqual(s["focus"], "SPAN#count:-")  # the Send button had the focus and is gone: the status line (tabindex -1) takes it, nobody is dropped on the page
        self.assertEqual(j["after_locked_click"]["q"][1]["checked"], s["q"][1]["checked"])  # nothing can be changed
        self.assertFalse(j["clear_none"])
        self.assertIn('"sent":true', s["store"])

    def test_the_board_survives_the_widget_unmounting(self):
        j = self.j
        r = j["remounted_cq"]
        self.assertEqual(r["count"], "Sent to the agent.")
        self.assertEqual([q["checked"] for q in r["q"]], [q["checked"] for q in j["sent_cq"]["q"]])
        self.assertEqual(r["q"][0]["ta"]["value"], "mine\nagain")
        self.assertEqual(r["q"][0]["disabled"], "111")

    def test_tabs_keep_answers_across_a_switch_and_a_remount(self):
        j = self.j
        self.assertEqual(j["tabs_one"]["count"], "1 of 3 answered")
        self.assertEqual(len(j["tabs_second"]["q"]), 1)  # the second tab shows one question
        self.assertEqual(j["tabs_second"]["count"], "2 of 3 answered")  # the bar is outside the tabs and counts both
        self.assertEqual(j["tabs_back"]["q"][0]["checked"], "100")  # the first tab remembers
        self.assertEqual(j["tabs_back"]["count"], "2 of 3 answered")
        self.assertEqual(j["tabs_remounted"]["count"], "2 of 3 answered")
        self.assertEqual(j["tabs_remounted"]["q"][0]["checked"], "100")

    def test_a_question_on_a_tab_never_shown_is_listed_as_no_answer(self):
        j = self.j
        self.assertEqual(j["tabs2_one"]["count"], "1 of 3 answered")
        self.assertEqual(j["calls_tabs2"], "Answers to the questions in widget `tabs2` (3):\n\n1. Which node should I restart first?\n   web-1\n"
                                           "2. Drain the node first?\n   (no answer)\n3. Clear the cache on db?\n   (no answer)")
        self.assertEqual(j["tabs2_sent"]["count"], "Sent to the agent.")

    def test_one_question_keeps_the_wire_format_byte_for_byte(self):
        j = self.j
        self.assertEqual(j["one_staged"]["count"], "1 of 1 answered")
        self.assertEqual(j["calls_one"], ONE_MESSAGE)
        self.assertEqual(j["one_sent"]["count"], "Sent to the agent.")

    def test_native_sends_up_to_4000_and_refuses_more_and_says_so(self):
        j = self.j
        length, count = j["calls_long"]
        self.assertGreater(length, 500)
        self.assertLess(length, 4000)
        self.assertEqual(j["long_sent"]["count"], "Sent to the agent.")
        h = j["huge_refused"]
        self.assertRegex(h["alert"], r"^This answer is [\d,]+ characters and this display mode sends at most 4,000\. Shorten the answers\.$")
        self.assertEqual(h["count"], "8 of 8 answered")
        self.assertFalse(h["send"]["dis"])  # nothing locked: the user shortens and sends again
        self.assertEqual(j["calls_after_huge"], count)
        self.assertEqual(j["huge_cleared"]["count"], "0 of 8 answered")
        self.assertIsNone(j["huge_cleared"]["alert"])

    def test_a_button_still_stops_at_500_characters(self):
        lens = [self.j["btn%d" % i] for i in range(4)]
        base = len(lens[0])
        self.assertEqual(lens[0], lens[1][:base])  # the 600 character Button sent nothing
        self.assertEqual(lens[1][-1], 500)  # 500: sent
        self.assertEqual(len(lens[2]), len(lens[1]))  # 501: not sent
        self.assertEqual(len(lens[3]), len(lens[2]) + 1)  # a short one: sent

    def test_notes_mode_makes_the_choice_and_the_bar_inert_and_the_table_can_still_be_noted(self):
        j = self.j
        self.assertTrue(j["nt_mode_attr"])
        self.assertEqual(j["nt_staged"]["count"], "1 of 1 answered")
        self.assertEqual(j["nt_inert"]["q"][0]["checked"], "100")  # a click on the other option did nothing
        self.assertEqual(j["nt_inert"]["q"][0]["disabled"], "111")
        self.assertTrue(j["nt_inert"]["send"]["dis"])
        self.assertTrue(j["nt_editor"])  # a neighbouring Table is still noted
        self.assertFalse(j["nt_mode_off"])
        self.assertEqual(j["nt_after"]["q"][0]["checked"], "010")  # and the options work again once the mode is off
        self.assertEqual(j["nt_after"]["count"], "1 of 1 answered")

    def test_the_bar_sends_to_the_chat_that_holds_the_widget(self):
        j = self.j
        # submit(address, text): a tile passes its stored id, the main chat the session it shows ("new" for a fresh draft), and no marker passes null as before
        self.assertEqual([a[0] for a in j["route_args"]], ["stored-7", "run-42", "new", None])
        self.assertTrue(all(a[1] == "Restart the web service? \u2014 Yes" for a in j["route_args"]), j["route_args"])
        self.assertTrue(all(len(a) == 2 for a in j["route_args"]))
        self.assertEqual(j["route_sent"], ["Sent to the agent."] * 4)
        self.assertEqual(j["r1_sent"]["focus"], "SPAN#count:-")

    def test_a_button_sends_to_the_chat_that_holds_the_widget(self):
        j = self.j
        self.assertEqual(j["route_btn_args"], [["stored-7", "Restart the web service"], ["run-42", "Restart the api service"], ["new", "Restart the db service"], [None, "Restart the cache service"]])

    def test_a_host_that_refuses_the_message_leaves_the_board_unlocked(self):
        j = self.j
        r = j["rf_refused"]
        self.assertEqual(r["alert"], "No chat input accepted the answers. Click the message box and try again.")
        self.assertFalse(r["send"]["dis"])
        self.assertEqual(r["q"][0]["disabled"], "000")  # the options are still on
        self.assertEqual(j["rf_args"][0][1], "Restart the web service? \u2014 Yes")
        self.assertEqual(j["rf_ok"]["count"], "Sent to the agent.")
        self.assertEqual(j["rf_ok"]["focus"], "BUTTON#opt0:-1")  # the focus was elsewhere: left alone
        self.assertIsNone(j["rf_ok"]["alert"])
        self.assertEqual(j["rf_args2"][0][1], j["rf_args"][0][1])

    def test_a_widget_redrawn_with_other_questions_arrives_unlocked_and_keeps_the_answer_that_fits(self):
        j = self.j
        self.assertEqual(j["st_sent"]["count"], "Sent to the agent.")
        r = j["st_redrawn"]
        self.assertEqual(r["count"], "1 of 2 answered")  # the first question is still answered, the new one is not
        self.assertEqual(r["q"][0]["checked"], "100")  # web-1 (and the Other row, which is off)
        self.assertEqual([q["disabled"] for q in r["q"]], ["000", "000"])
        self.assertEqual(r["q"][1]["name"], "Clear the cache on db?")
        self.assertFalse(r["send"]["dis"])  # not locked, and not "Sent to the agent."

    # --- single and multiple look different: indicators, tag words, roles, contrast; dark here (the main run), light in a run of its own
    def test_single_and_multiple_questions_have_different_indicators_in_the_dark_theme(self):
        j = self.j
        kinds = ["single", "multiple", "single"]
        CP.check_indicators(self, j["look_idle"], kinds)
        for q in j["look_idle"]:
            self.assertEqual({r["checked"] for r in q["rows"]}, {"false"})
        self.assertEqual([[r["role"] for r in q["rows"]] for q in j["look_idle"]], [["radio"] * 3, ["checkbox"] * 4, ["radio"] * 2])
        CP.check_indicators(self, j["look_multi"], kinds)  # aria-checked flipped: web-2 (single) and Disk and Network (multiple)
        self.assertEqual([[r["checked"] for r in q["rows"]] for q in j["look_multi"]][:2], [["false", "true", "false"], ["true", "false", "true", "false"]])
        self.assertTrue(j["look_multi"][0]["rows"][1]["dot"])
        self.assertTrue(j["look_multi"][1]["rows"][0]["check"] and j["look_multi"][1]["rows"][2]["check"])
        CP.check_indicators(self, j["look_other"], kinds)  # the Other row of a single question is a radio and takes the dot
        o = j["look_other"][0]["rows"][2]
        self.assertEqual((o["other"], o["role"], o["kind"], o["checked"], o["dot"]), (True, "radio", "radio", "true", True))

    def test_the_other_row_of_a_multiple_question_is_a_checkbox_with_a_check(self):
        j = self.j
        CP.check_indicators(self, j["look_mo_idle"], ["multiple"])
        CP.check_indicators(self, j["look_mo"], ["multiple"])
        rows = j["look_mo"][0]["rows"]
        self.assertEqual([r["checked"] for r in rows], ["true", "false", "true"])
        self.assertEqual((rows[2]["other"], rows[2]["role"], rows[2]["kind"], bool(rows[2]["check"])), (True, "checkbox", "checkbox", True))
        CP.check_indicators(self, j["look_mo_sent"], ["multiple"], locked=True)

    def test_a_locked_card_keeps_its_filled_indicators_and_readable_text(self):
        j = self.j
        CP.check_indicators(self, j["look_sent"], ["single", "multiple", "single"], locked=True)
        q0, q1, q2 = j["look_sent"]
        self.assertEqual([r["checked"] for r in q0["rows"]], ["false", "false", "true"])  # the Other answer
        self.assertEqual([r["checked"] for r in q1["rows"]], ["true", "false", "true", "false"])
        self.assertTrue(all(r["opacity"] == 1 for q in (q0, q1) for r in q["rows"] if r["checked"] == "true"))
        self.assertTrue(all(r["opacity"] < 1 for q in (q0, q1, q2) for r in q["rows"] if r["checked"] == "false"))  # unanswered rows are dimmed, still readable

    def test_the_two_kinds_differ_in_the_picture_itself(self):
        CP.check_shapes_in_picture(self, self.png, [m for card in self.j["marks_final"] for m in card])



@unittest.skipUnless(CHROME, "set OPENUI_TEST_CHROME=1 (needs Chrome and Node)")
class NativeChoiceLight(unittest.TestCase):
    """The indicators in the light theme: one more launch, the question card only (CP.indicator_program)."""

    @classmethod
    def setUpClass(cls):
        import shoot
        try:
            shoot.find_chrome(None)
        except SystemExit:
            raise unittest.SkipTest("no Chrome found (set $CHROME)")
        cls.td = tempfile.mkdtemp()
        page = CP.build_page(cls.td, [640], ["cq"], theme="light", app_css=CP.app_css())
        cls.png = Path(cls.td) / "light.png"
        r, cls.out = CP.run(page, cls.png, 640 + 24, CP.indicator_program("cq"), scale=1, theme="light")
        Path(os.environ.get("CHOICE_RECORD_LIGHT", os.path.join(cls.td, "record-light.json"))).write_text(json.dumps(r, indent=1), encoding="utf-8")
        cls.j = {k: json.loads(v) if isinstance(v, str) else v for k, v in r.items()}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.td, ignore_errors=True)

    def test_the_light_theme_has_the_same_indicators_and_enough_contrast(self):
        j, kinds = self.j, ["single", "multiple", "single"]
        for k in ("look_idle", "look_multi", "look_other"):
            CP.check_indicators(self, j[k], kinds)
        self.assertEqual({r["checked"] for q in j["look_idle"] for r in q["rows"]}, {"false"})
        self.assertEqual([r["checked"] for r in j["look_other"][1]["rows"]], ["true", "false", "true", "true"])  # Disk, Network and Other
        self.assertTrue(j["look_other"][1]["rows"][3]["check"] and j["look_other"][0]["rows"][2]["dot"])
        CP.check_indicators(self, j["look_sent"], kinds, locked=True)  # locked: chosen rows keep their fill, the dimmed text is still readable
        self.assertTrue(all(r["opacity"] == 1 for q in j["look_sent"] for r in q["rows"] if r["checked"] == "true"))

    def test_the_two_kinds_differ_in_the_picture_itself(self):
        CP.check_shapes_in_picture(self, self.png, [m for card in self.j["marks_final"] for m in card])

    def test_the_run_has_no_console_errors(self):
        self.assertIn("console errors: 0", self.out)


if __name__ == "__main__":
    unittest.main()
