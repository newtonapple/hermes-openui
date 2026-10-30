"""Notes in real Chrome: the real desktop/plugin.js in the native harness (stub SDK, the app's stylesheet inlined), driven through
tools/shoot.py --steps with REAL mouse and key events. Opt in: OPENUI_TEST_CHROME=1 python3 -m unittest tests.test_notes_native

ONE page and ONE Chrome launch run every case in a row (the program below); the tests then assert on the values it recorded. A second
launch draws the widgets at four column widths and checks that the chip, the mode and the wrappers move nothing. Not covered: the real
app (its composer, its heart-on-double-click, its Escape handler are replaced by stand-ins that replay the app's rules), touch, screen readers.
"""
import json
import os
import platform
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import notes_probe as P  # noqa: E402

ROOT = P.ROOT
APP_CSS = None
for cand in sorted((Path.home() / ".hermes/hermes-agent/apps/desktop/dist/assets").glob("index-*.css")):
    APP_CSS = cand

NAMES = ["text", "hosts", "tabs", "buttons", "plain", "inline", "tip", "ux", "big", "stale", "more"]

HELPERS = r"""
window.__H = (function () {
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var root = function (w) { return document.querySelector('[data-widget="' + w + '"] .hermes-openui-root'); };
  var keys = [], steal = 0, dbl = 0, up = [];
  addEventListener('keydown', function (e) { keys.push({ k: e.key, dp: e.defaultPrevented }); });
  // what the app's composer type-to-focus would take (composer-focus-keys.ts: not prevented, not composing, no modifier, not an editable target, a printable key)
  addEventListener('keydown', function (e) { var t = e.target; var ed = t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)); if (!e.defaultPrevented && !e.isComposing && !e.metaKey && !e.ctrlKey && !e.altKey && !ed && e.key.length === 1) steal++; });
  document.querySelectorAll('[data-host]').forEach(function (h) { h.addEventListener('dblclick', function () { dbl++; }); });  // one level up from the widget root: the app's heart handler would sit here
  document.addEventListener('mouseup', function () { up.push(String(getSelection())); }, true);
  var after = function (f) { return new Promise(function (res) { var n = 0; var tick = function () { if (++n < 5) requestAnimationFrame(tick); else res(f()); }; requestAnimationFrame(tick); }); };  // five frames: a hover, a mutation observer and React's scheduler all get their turn
  var ws = function (s) { return String(s).replace(/\s+/g, ' ').trim(); };
  var desc = function (e) { return e ? e.tagName.toLowerCase() + (e.getAttribute('data-oui-chip') !== null ? '#chip' : '') + (e.getAttribute('data-oui-k') ? '[' + e.getAttribute('data-oui-k') + ']' : '') : null; };
  var st = function (w) {
    var r = root(w), chip = $('[data-oui-chip]', r), ed = $('[data-oui-editor]', r), hint = $('[data-oui-hint]', r), tray = $('[data-oui-tray]', r), rb = r.getBoundingClientRect();
    var lab = $('[data-oui-hover-label]', r), ta = ed && ed.querySelector('textarea'), rr = function (e) { var q = e.getBoundingClientRect(); return [Math.round((q.left - rb.left) * 10) / 10, Math.round((q.top - rb.top) * 10) / 10, Math.round(q.width * 10) / 10, Math.round(q.height * 10) / 10]; };
    var hlnames = function (n) { return (window.CSS && CSS.highlights && CSS.highlights.has(n)) ? Array.from(CSS.highlights.get(n)) : null; };
    return {
      mode: r.hasAttribute('data-oui-mode'), active: r.hasAttribute('data-oui-active'), pressed: chip.getAttribute('aria-pressed'), chipOpacity: getComputedStyle(chip).opacity,
      chipPos: [Math.round(chip.getBoundingClientRect().right - rb.right), Math.round(chip.getBoundingClientRect().top - rb.top)], hint: hint ? hint.textContent : null, hover: lab ? lab.textContent : null,
      editor: ed ? { role: ed.getAttribute('role'), label: ed.getAttribute('aria-label'), text: ws(ed.innerText), ph: ta.placeholder, value: ta.value, focused: document.activeElement === ta, max: ta.maxLength,
        inside: (function () { var q = ed.getBoundingClientRect(); return q.left >= rb.left - 0.5 && q.right <= rb.right + 0.5 && q.top >= rb.top - 0.5 && q.bottom <= rb.bottom + 0.5; })(), saveDisabled: ed.querySelector('[data-oui-save]').disabled,
        buttons: Array.prototype.map.call(ed.querySelectorAll('button'), function (b) { return b.textContent; }),
        err: (function () { var a = ed.querySelector('[role=alert]'); return a ? a.textContent : null; })(), pulse: ed.getAttribute('data-oui-pulse') } : null,
      removeMin: (function () { var b = r.querySelectorAll('[data-oui-remove]'); return b.length ? Math.min.apply(null, Array.prototype.map.call(b, function (x) { return x.getBoundingClientRect().height; })) : null; })(),
      rowOpacity: (function () { var rows = r.querySelectorAll('[data-oui-row]'); if (!rows.length) return null; return Math.min.apply(null, Array.prototype.map.call(rows, function (b) { var o = 1, e = b; while (e && e !== tray) { o *= parseFloat(getComputedStyle(e).opacity); e = e.parentNode; } return Math.round(o * 100) / 100; })); })(),
      states: Array.prototype.map.call(r.querySelectorAll('[data-oui-row]'), function (b) { var x = b.querySelector('[data-oui-state]'); return x ? x.textContent : ''; }),
      rowNums: Array.prototype.map.call(r.querySelectorAll('[data-oui-row]'), function (b) { return b.getAttribute('data-oui-row'); }), removeNums: Array.prototype.map.call(r.querySelectorAll('[data-oui-remove]'), function (b) { return b.getAttribute('data-oui-remove'); }),
      allin: (function () { var b = $('[data-oui-allin]', r); return b ? b.textContent : null; })(), trayButtons: tray ? Array.prototype.filter.call(tray.querySelectorAll('button'), function (b) { return !b.hasAttribute('data-oui-row') && !b.hasAttribute('data-oui-remove') && !b.hasAttribute('data-oui-keep') && !b.hasAttribute('data-oui-drop'); }).map(function (b) { return b.textContent; }) : null,
      pinNums: Array.prototype.map.call(r.querySelectorAll('[data-oui-pin]'), function (b) { return b.getAttribute('data-oui-pin'); }), focusClear: document.activeElement.hasAttribute('data-oui-clear-done'),
      chipText: chip.textContent, chip: rr(chip), labelBox: lab ? rr(lab) : null, staleText: (function () { var b = $('[data-oui-stale]', r); return b ? ws(b.innerText) : null; })(),
      pending: (function () { var h = hlnames('oui-note-pending'); return h ? h.map(function (x) { return ws(x.toString()); }) : null; })(),
      hlr: (function () { var h = hlnames('oui-note'); return h ? h.map(function (x) { var q = x.getClientRects()[0] || x.getBoundingClientRect(); return [Math.round((q.left - rb.left) * 10) / 10, Math.round((q.top - rb.top) * 10) / 10, Math.round(q.width), Math.round(q.height), ws(x.toString())]; }) : null; })(),
      pins: Array.prototype.map.call(r.querySelectorAll('[data-oui-pin]'), function (p) { var q = p.getBoundingClientRect(); return { n: p.textContent, label: p.getAttribute('aria-label'), w: Math.round(q.width), h: Math.round(q.height), inside: q.left >= rb.left - 0.5 && q.right <= rb.right + 0.5 && q.top >= rb.top - 0.5 && q.bottom <= rb.bottom + 0.5, x: Math.round(q.left - rb.left), y: Math.round(q.top - rb.top) }; }),
      rows: Array.prototype.map.call(r.querySelectorAll('[data-oui-row]'), function (x) { return ws(x.innerText); }),
      tray: tray ? ws(tray.innerText) : null, trayInFlow: tray ? getComputedStyle(tray).position : null, draftBtn: (function () { var b = $('[data-oui-draft]', r); return b ? b.textContent : null; })(),
      fail: (function () { var b = $('[data-oui-fail]', r); return b ? { text: ws(b.innerText), select: getComputedStyle(b.querySelector('pre')).userSelect, pre: b.querySelector('pre').textContent } : null; })(),
      done: (function () { var b = $('[data-oui-done]', r); return b ? b.textContent : null; })(), info: (function () { var b = $('[data-oui-info]', r); return b ? b.textContent : null; })(),
      clearDone: !!$('[data-oui-clear-done]', r), live: $('[aria-live]', r).textContent, focus: desc(document.activeElement), flash: !!$('[data-oui-flash]', r),
      tipShown: !!$('[role=tooltip]', r), stops: r.querySelectorAll('[data-oui-stop]').length,
      hl: (window.CSS && CSS.highlights && CSS.highlights.has('oui-note')) ? Array.from(CSS.highlights.get('oui-note')).map(function (x) { return ws(x.toString()); }) : null,
      store: sessionStorage.getItem('hermes-openui:notes:' + w), meta: sessionStorage.getItem('hermes-openui:notes-meta:' + w), h: Math.round(rb.height), w: Math.round(rb.width),
    };
  };
  var all = function () { var o = {}; document.querySelectorAll('.cell').forEach(function (c) { var r = c.querySelector('.hermes-openui-root'); o[c.dataset.widget + '@' + c.querySelector('.slot').style.width] = r ? Math.round(r.getBoundingClientRect().height) : -1; }); o.body = Math.round(document.body.getBoundingClientRect().height); return o; };
  // does the hover label overlap any line of text of the element `sel` inside widget `w`?
  var labelHits = function (w, sel) { var l = $('[data-oui-hover-label]', root(w)); if (!l) return 'no label'; var lb = l.getBoundingClientRect(), rg = document.createRange(); rg.selectNodeContents($(sel, root(w))); return Array.prototype.some.call(rg.getClientRects(), function (q) { return !(q.right <= lb.left || q.left >= lb.right || q.bottom <= lb.top || q.top >= lb.bottom); }); };
  var cardOverItem = function (w, sel) { var c = $('[data-oui-editor]', root(w)), it = $(sel, root(w)); if (!c || !it) return 'missing'; var a = c.getBoundingClientRect(), b = it.getBoundingClientRect(); return !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom); };
  return { cardOverItem: cardOverItem, labelHits: labelHits, root: root, st: st, after: after, keys: keys, all: all, calls: function () { return JSON.parse(JSON.stringify(window.__hostCalls)); }, steal: function () { return steal; }, dbl: function () { return dbl; }, up: function () { return up.slice(); }, ws: ws };
})();
"""


def program():
    """The whole walk, as shoot.py steps. Names of eval steps are what the tests read."""
    S = []

    def ev(name, js):
        S.append({"eval": "__H.after(function(){return (" + js + ");})", "name": name})

    def sel(widget, inner):
        return '[data-widget="%s"] %s' % (widget, inner)

    def click(widget, inner, at=None):
        S.append({"click": sel(widget, inner), **({"at": at} if at else {})})

    def move(widget, inner, at=None):
        S.append({"move": sel(widget, inner), **({"at": at} if at else {})})

    def note(text):
        S.append({"type": text})
        S.append({"key": "Enter"})

    S.append({"js": HELPERS})
    S.append({"js": P.LAYOUT_JS})
    ev("h_off", "__H.all()")
    ev("st_off", "__H.st('text')")
    # 1. the chip: hidden, then visible on hover, and nothing moves
    move("text", '[data-oui-id="intro"] p')
    ev("chip_hover", "__H.st('text')")
    ev("h_hover", "__H.all()")
    # 2. notes mode
    click("text", "[data-oui-chip]")
    ev("mode_on", "__H.st('text')")
    ev("h_mode", "__H.all()")
    move("text", 'td[data-oui-k="cell:2.status"]')
    ev("hover_cell", "__H.st('text')")
    ev("label_vs_item", "__H.labelHits('text', 'td[data-oui-k=\"cell:2.status\"]')")
    ev("cursors", "getComputedStyle(document.querySelector('[data-widget=\"text\"] td[data-oui-k=\"cell:2.status\"]')).cursor")
    # 3. click an item -> editor (IME flag first: Enter while composing must not save)
    click("text", 'td[data-oui-k="cell:2.status"]')
    ev("editor_open", "__H.st('text')")
    S.append({"key": "Enter"})  # empty note: cannot be saved
    ev("empty_enter", "__H.st('text')")
    S.append({"type": "Is this expected?"})
    # TEXT FIRST, then Enter while an IME is composing: with an empty editor the "empty note" rule would hide a missing guard
    S.append({"js": "(function(){var t=document.querySelector('[data-oui-editor] textarea');t.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true,isComposing:true}));})()"})
    ev("ime", "{open: __H.st('text').editor !== null, value: (__H.st('text').editor || {}).value, pins: __H.st('text').pins.length}")
    S.append({"key": "Enter"})
    ev("saved1", "__H.st('text')")
    ev("calls_1", "__H.calls()")
    ev("steal_1", "__H.steal()")
    # 4. select text in Markdown (real drag), cancel with Escape, then again and save with two lines
    S.append({"drag": sel("text", '[data-oui-id="intro"] p'), "from": [0.06, 0.3], "to": [0.4, 0.3]})
    ev("md_editor", "__H.st('text')")
    ev("md_selection", "__H.up().slice(-1)[0]")
    S.append({"key": "Escape"})
    ev("esc_editor", "{st: __H.st('text'), key: __H.keys.slice(-1)[0]}")
    S.append({"drag": sel("text", '[data-oui-id="intro"] p'), "from": [0.06, 0.3], "to": [0.4, 0.3]})
    S.append({"type": "Which restart is this?"})
    S.append({"key": "Shift+Enter"})
    S.append({"type": "Second line"})
    ev("two_lines", "__H.st('text').editor")
    S.append({"key": "Enter"})
    ev("saved2", "__H.st('text')")
    # 5. double-click a word in Text: the editor opens with that word; the dblclick stops at the root
    S.append({"dblclick": sel("text", '[data-oui-id="para"] > div'), "at": [0.12, 0.5]})
    ev("dbl_editor", "__H.st('text')")
    ev("dbl_selection", "__H.up().slice(-1)[0]")
    ev("dbl_count", "__H.dbl()")
    note("Check this word")
    # 6. Callout, Faq, CodeBlock (line numbers), Table cell
    S.append({"drag": sel("text", '[data-oui-id="note"] > *'), "from": [0.1, 0.5], "to": [0.5, 0.5]})
    ev("callout_editor", "__H.st('text').editor")
    ev("callout_selection", "__H.up().slice(-1)[0]")
    note("Callout note")
    S.append({"drag": sel("text", '[data-oui-id="faq"] button'), "from": [0.1, 0.5], "to": [0.5, 0.5]})
    ev("faq_editor", "__H.st('text').editor")
    ev("faq_selection", "__H.up().slice(-1)[0]")
    note("Faq note")
    S.append({"drag": sel("text", '[data-oui-id="code"] pre code'), "from": [0.02, 0.1], "to": [0.5, 0.6]})
    ev("code_editor", "__H.st('text').editor")
    ev("code_selection", "__H.up().slice(-1)[0]")
    note("Code note")
    S.append({"drag": sel("text", 'td[data-oui-k="cell:2.status"]'), "from": [0.06, 0.5], "to": [0.94, 0.5]})
    ev("cell_editor", "__H.st('text').editor")
    ev("cell_selection", "__H.up().slice(-1)[0]")
    note("Cell note")
    ev("saved_all", "__H.st('text')")
    # 7. the tray: flash a row, remove one (numbers move up), edit one by its pin, delete it
    click("text", "[data-oui-row=\"2\"]")
    ev("flash", "__H.st('text').flash")
    click("text", "[data-oui-remove=\"3\"]")
    ev("removed", "__H.st('text')")
    click("text", "[data-oui-pin=\"1\"]")
    ev("edit_open", "__H.st('text').editor")
    S.append({"key": "Escape"})
    ev("edit_esc", "__H.st('text').editor === null")
    # 8. leave the mode with Escape (focus is on the chip): the Escape is handled; and a second Escape is left alone
    S.append({"js": "document.querySelector('[data-widget=\"text\"] [data-oui-chip]').focus()"})
    S.append({"key": "Escape"})
    ev("left_mode", "{st: __H.st('text'), key: __H.keys.slice(-1)[0]}")
    S.append({"key": "Escape"})
    ev("esc_idle", "__H.keys.slice(-1)[0]")
    S.append({"dblclick": sel("text", "[data-oui-tray]"), "at": [0.9, 0.05]})
    ev("dbl_tray", "__H.dbl()")
    # 9. drafting: true path
    ev("tray_off", "__H.st('text')")
    click("text", "[data-oui-draft]")
    ev("drafted_ok", "__H.st('text')")
    ev("calls_2", "__H.calls()")
    # 10. changing a note after drafting re-enables the primary button ("Add again"); false path
    click("text", "[data-oui-pin=\"1\"]")
    S.append({"type": " more"})
    S.append({"key": "Enter"})
    ev("add_again", "__H.st('text').draftBtn")
    S.append({"js": "window.__insertResult = false"})
    click("text", "[data-oui-draft]")
    ev("drafted_fail", "__H.st('text')")
    S.append({"js": "window.__insertResult = 'throw'"})
    click("text", "[data-oui-draft]")
    ev("drafted_throw", "__H.st('text').fail !== null")
    ev("calls_3", "__H.calls()")
    # 11. persistence: unmount and remount the widget
    ev("before_remount", "{n: __H.st('text').pins.length, store: __H.st('text').store}")
    ev("widget_index", "Array.from(document.querySelectorAll('.cell')).findIndex(function(c){return c.dataset.widget==='text'})")
    S.append({"js": "window.__unmount(0)"})
    ev("unmounted", "document.querySelector('[data-widget=\"text\"] .hermes-openui-root') === null")
    S.append({"js": "window.__mount(0)"})
    ev("remounted", "new Promise(function(r){var f=function(){return document.querySelector('[data-widget=\"text\"] [data-oui-pin]')};if(f())return r(1);new MutationObserver(function(_,o){if(f()){o.disconnect();r(1)}}).observe(document.body,{childList:true,subtree:true})}).then(function(){return __H.st('text')})")
    # 12. hosts: click one item of each of the nine hosts, plus a whole chart
    click("hosts", "[data-oui-chip]")
    ev("hits_mode", "__hits()")  # in the mode the transparent hit shapes catch the pointer on a thin line
    # select text in an SVG diagram label and in a library chart (the app's sheet says svg{user-select:none})
    S.append({"drag": sel("hosts", '[data-oui-id="dag"] svg text'), "from": [0.02, 0.5], "to": [0.98, 0.5]})
    ev("svg_editor", "__H.st('hosts').editor")
    ev("svg_selection", "__H.up().slice(-1)[0]")
    S.append({"key": "Escape"})
    S.append({"drag": sel("hosts", '[data-oui-id="line"] svg text'), "from": [0.02, 0.5], "to": [0.98, 0.5]})
    ev("chart_editor", "__H.st('hosts').editor")
    ev("chart_selection", "__H.up().slice(-1)[0]")
    S.append({"key": "Escape"})
    hosts = [
        ("dag", '[data-oui-id="dag"] [data-oui-k="build"]'),
        ("erd", '[data-oui-id="erd"] [data-oui-k="orders.user_id"]'),
        ("infra", '[data-oui-id="infra"] [data-oui-k="api"]'),
        ("seq", '[data-oui-id="seq"] [data-oui-k="m2"]'),
        ("metric", '[data-oui-id="m1"] [data-oui-k]'),
        ("bar", '[data-oui-id="bars"] [data-oui-k="api"]'),
        ("geo", '[data-oui-id="map"] [data-oui-k="web"]'),
        ("image", '[data-oui-id="img"] [data-oui-k="image"]'),
        ("line", '[data-oui-id="line"] svg'),
    ]
    for name, inner in hosts:
        move("hosts", inner)
        ev("hh_" + name, "__H.st('hosts').hover")
        click("hosts", inner)
        ev("he_" + name, "__H.st('hosts').editor && __H.st('hosts').editor.text")
        note("note on " + name)
    ev("hosts_saved", "__H.st('hosts')")
    click("hosts", "[data-oui-draft]")
    ev("hosts_after_draft", "__H.st('hosts')")
    ev("hosts_calls", "__H.calls().filter(function(c){return c.insertText}).slice(-1)[0]")
    # a participant of the sequence diagram (the same key as an InfraMap node, told apart by the component)
    click("hosts", '[data-oui-id="seq"] [data-oui-k="client"]')
    ev("he_participant", "__H.st('hosts').editor.label")
    S.append({"key": "Escape"})
    # Stack, Card, Tabs are never targets; Button and Choice are inert and not noted
    click("buttons", "[data-oui-chip]")
    click("buttons", '[data-oui-id="a"] button')
    click("buttons", '[data-oui-id="ask"] button')
    ev("buttons", "{st: __H.st('buttons'), calls: __H.calls().filter(function(c){return c.submit}).length, cursor: getComputedStyle(document.querySelector('[data-widget=\"buttons\"] [data-oui-id=\"a\"] button')).cursor}")
    # 13. Tabs: the tab bar works in the mode; a note under a tab is kept in the tray when the tab is not shown
    click("tabs", "[data-oui-chip]")
    click("tabs", "[data-oui-tabbar] button:nth-child(2)")
    click("tabs", 'td[data-oui-k="cell:2.jobs"]')
    ev("tab_editor", "__H.st('tabs').editor")
    note("Why is w2 busy?")
    ev("tab_saved", "__H.st('tabs')")
    click("tabs", "[data-oui-tabbar] button:nth-child(1)")
    ev("tab_hidden", "__H.st('tabs')")
    click("tabs", "[data-oui-tabbar] button:nth-child(2)")
    ev("tab_back", "__H.st('tabs')")
    click("tabs", "[data-oui-draft]")
    ev("tabs_calls", "__H.calls().filter(function(c){return c.insertText}).slice(-1)[0]")
    # 14. Tooltip: shows on hover, is suspended in the mode, and comes back exactly when the mode ends
    move("tip", 'td[data-oui-k="cell:2.status"]')
    ev("tip_before", "__H.st('tip').tipShown")
    click("tip", "[data-oui-chip]")
    move("tip", 'td[data-oui-k="cell:1.status"]')
    move("tip", 'td[data-oui-k="cell:2.status"]')
    ev("tip_in_mode", "__H.st('tip')")
    click("tip", "[data-oui-chip]")
    move("tip", 'td[data-oui-k="cell:1.status"]')
    move("tip", 'td[data-oui-k="cell:2.status"]')
    ev("tip_after", "__H.st('tip').tipShown")
    # 15. keyboard: Tab reaches the items in notes mode, Enter opens the editor
    click("plain", "[data-oui-chip]")
    S.append({"js": "document.querySelector('[data-widget=\"plain\"] [data-oui-chip]').focus()"})
    S.append({"key": "Tab"})
    ev("tab_focus", "{f: __H.st('plain').focus, stops: __H.st('plain').stops, hover: __H.st('plain').hover}")
    S.append({"key": "Enter"})
    ev("tab_enter", "__H.st('plain').editor && __H.st('plain').editor.text")
    S.append({"key": "Escape"})
    ev("tab_back_focus", "__H.st('plain').focus")
    S.append({"key": "Escape"})
    # a click on the hint bar (not an item) leaves the focus inside the widget, so Esc still finishes the mode
    click("plain", "[data-oui-chip]")
    click("plain", "[data-oui-hint]")
    ev("blank_focus", "__H.st('plain').focus")
    S.append({"key": "Escape"})
    ev("blank_esc", "{mode: __H.st('plain').mode, key: __H.keys.slice(-1)[0]}")
    # 16. the other widget is untouched while 'text' is in mode, and the layout with everything closed
    click("text", "[data-oui-chip]")
    ev("h_text_mode", "__H.all()")
    S.append({"key": "Escape"})
    ev("end_state", "{plain: __H.st('plain'), inline: __H.st('inline').h}")
    # 17. which composer: the widget names the chat that HOLDS it (data-composer-target on an ancestor, set by the app on every chat surface)
    def route(name, widget, target, active, item):
        attr = "c.removeAttribute('data-composer-target');" if target is None else "c.setAttribute('data-composer-target'," + json.dumps(target) + ");"
        S.append({"js": "(function(){var c=document.querySelector('[data-widget=\"%s\"]');%s window.__activeSessionId=%s;})()" % (widget, attr, json.dumps(active))})
        click(widget, "[data-oui-chip]")
        click(widget, item)
        note("route " + name)
        click(widget, "[data-oui-draft]")
        ev("route_" + name, "__H.calls().filter(function(c){return c.insertText||c.focus}).slice(-2)")
        ev("after_" + name, "__H.st('%s')" % widget)  # a draft that went through ends the mode
    S.append({"js": "window.__insertResult = true"})  # an earlier case made the composer throw
    route("tile", "plain", "tile:stored-7", "ignored", '[data-oui-id="p"] p')
    route("main", "inline", "main", "run-42", '[data-oui-type="Text"] > *')
    route("main_new", "tip", "main", None, 'td[data-oui-k="cell:1.status"]')
    # 18. a click on another item does not throw away a half typed note; an empty editor just moves
    click("ux", "[data-oui-chip]")
    click("ux", 'td[data-oui-k="cell:2.status"]')
    S.append({"type": "half typed"})
    click("ux", 'td[data-oui-k="cell:1.status"]')
    ev("half_blocked", "__H.st('ux').editor")
    click("ux", 'td[data-oui-k="cell:1.service"]')
    ev("half_blocked_2", "__H.st('ux').editor")
    ev("half_card_clear", "__H.cardOverItem('ux', 'td[data-oui-k=\"cell:2.status\"]')")   # the card sits below its item, not on it
    S.append({"key": "Escape"})
    click("ux", 'td[data-oui-k="cell:1.status"]')
    click("ux", 'td[data-oui-k="cell:1.service"]')
    ev("empty_moves", "__H.st('ux').editor")
    S.append({"key": "Escape"})
    # words that span two cells cannot be found again: the note keeps a pin at the top left of the component, away from the chip
    S.append({"drag": sel("ux", 'tr[data-oui-k="row:1"]'), "from": [0.005, 0.5], "to": [0.53, 0.5]})
    ev("span_editor", "__H.st('ux').editor")
    note("across two cells")
    ev("span_saved", "__H.st('ux')")
    # a selection that ends right after a line break stops at the line before it: lines 1-2, not 1-3
    S.append({"drag": sel("ux", '[data-oui-id="code"] pre code'), "from": [0.02, 0.1], "to": [0.0, 0.6]})
    ev("code_span", "__H.st('ux').editor.text")
    note("code lines")
    ev("code_lines", "JSON.parse(sessionStorage.getItem('hermes-openui:notes:ux')).filter(function(n){return n.ctype==='CodeBlock'}).map(function(n){return [n.lines, n.quote]})")
    # the chip ends the mode and closes an open editor with it
    click("ux", 'td[data-oui-k="cell:3.status"]')
    click("ux", "[data-oui-chip]")
    ev("chip_closes", "{mode: __H.st('ux').mode, editor: __H.st('ux').editor}")
    # 19. the 21st note: the message is where the user is looking (hint bar, hover label) and in the tray
    click("big", "[data-oui-chip]")
    # one tab stop per component (a 100 row table is one stop); the arrows move between its items
    ev("big_stops", "{tab0: document.querySelectorAll('[data-widget=\"big\"] [data-oui-stop][tabindex=\"0\"]').length, all: document.querySelectorAll('[data-widget=\"big\"] [data-oui-stop]').length, comps: document.querySelectorAll('[data-widget=\"big\"] [data-oui-type]').length}")
    S.append({"js": "document.querySelector('[data-widget=\"big\"] [data-oui-chip]').focus()"})
    S.append({"key": "Tab"})
    ev("tab_1", "__H.st('big').focus")
    S.append({"key": "Tab"})
    ev("tab_2", "__H.st('big').focus")
    S.append({"key": "ArrowRight"})
    ev("arrow_right", "__H.st('big').focus")
    S.append({"key": "ArrowDown"})
    ev("arrow_down", "__H.st('big').focus")
    S.append({"key": "ArrowLeft"})
    ev("arrow_left", "{f: __H.st('big').focus, dp: __H.keys.slice(-1)[0]}")
    S.append({"key": "Shift+Tab"})
    ev("shift_tab", "__H.st('big').focus")
    S.append({"key": "Tab"})
    ev("tab_return", "__H.st('big').focus")
    for r in range(1, 21):
        click("big", 'td[data-oui-k="cell:%d.a"]' % r)
        note("n%d" % r)
    ev("limit_20", "__H.st('big').pins.length")
    click("big", 'td[data-oui-k="cell:21.a"]')
    ev("limit_21", "(function(){var s=__H.st('big');return {hint:s.hint,hover:s.hover,info:s.info,editor:s.editor,pins:s.pins.length}})()")
    move("big", '[data-oui-id="intro"] p')
    ev("limit_moved", "{hint: __H.st('big').hint, hover: __H.st('big').hover}")
    S.append({"key": "Escape"})
    # 20. the agent redraws the widget (same file, other content): the old notes are set aside, not sent without a word
    click("stale", "[data-oui-chip]")
    click("stale", 'td[data-oui-k="cell:2.status"]')
    note("about the cell")
    click("stale", '[data-oui-id="title"] p')
    note("about the title")
    ev("stale_before", "__H.st('stale')")
    click("stale", "[data-oui-chip]")
    S.append({"js": "window.__idx = Array.from(document.querySelectorAll('.cell')).findIndex(function(c){return c.dataset.widget==='stale'}); window.__unmount(window.__idx); window.__sources.stale = " + json.dumps(P.STALE_V2) + "; window.__mount(window.__idx);"})
    ev("stale_state", "new Promise(function(r){var f=function(){return document.querySelector('[data-widget=\"stale\"] [data-oui-stale]')};if(f())return r(1);new MutationObserver(function(_,o){if(f()){o.disconnect();r(1)}}).observe(document.body,{childList:true,subtree:true})}).then(function(){return __H.st('stale')})")
    click("stale", "[data-oui-chip]")
    click("stale", 'td[data-oui-k="cell:1.status"]')
    note("new note")
    click("stale", "[data-oui-draft]")
    ev("stale_draft", "__H.calls().filter(function(c){return c.insertText}).slice(-1)[0]")
    click("stale", "[data-oui-keep]")
    ev("stale_kept", "__H.st('stale')")
    click("stale", "[data-oui-draft]")
    ev("stale_draft2", "__H.calls().filter(function(c){return c.insertText}).slice(-1)[0]")
    # 21. a second draft carries only the notes that are not in the message box yet (the owner's case: notes 1 and 2 were repeated)
    S.append({"js": "window.__insertResult = true"})
    last_insert = "__H.calls().filter(function(c){return c.insertText}).slice(-1)[0]"
    all_inserts = "__H.calls().filter(function(c){return c.insertText}).length"
    ev("m_n0", all_inserts)
    click("more", "[data-oui-chip]")
    click("more", 'td[data-oui-k="cell:1.status"]')
    note("first one")
    click("more", 'td[data-oui-k="cell:2.status"]')
    note("second one")
    ev("m_two", "__H.st('more')")
    click("more", "[data-oui-draft]")
    ev("m_d1", last_insert)
    ev("m_after1", "__H.st('more')")
    click("more", "[data-oui-chip]")
    click("more", 'td[data-oui-k="cell:3.status"]')
    note("third one")
    ev("m_live3", "__H.st('more').live")
    ev("m_added", "__H.st('more')")
    S.append({"js": "window.__copied = []; document.addEventListener('copy', function () { window.__copied.push(document.activeElement && document.activeElement.value); }, true)"})
    click("more", "[data-oui-copy]")
    ev("m_copied", "window.__copied.slice()")
    click("more", "[data-oui-draft]")
    ev("m_d2", last_insert)
    ev("m_after2", "__H.st('more')")
    click("more", "[data-oui-copy]")
    ev("m_copied2", "window.__copied.slice()")
    ev("m_n2", all_inserts)
    # edit note 1: the button counts it and the next message carries it, marked, with its number
    click("more", '[data-oui-pin="1"]')
    S.append({"type": "Edited: "})            # the editor opens with the caret at the start
    S.append({"key": "Enter"})
    ev("m_edited", "__H.st('more')")
    S.append({"js": "window.__insertResult = false"})
    click("more", "[data-oui-draft]")
    ev("m_fail", "__H.st('more')")
    S.append({"js": "window.__insertResult = true"})
    click("more", "[data-oui-draft]")
    ev("m_d3", last_insert)
    ev("m_after3", "__H.st('more')")
    click("more", "[data-oui-again]")
    ev("m_d4", last_insert)
    ev("m_after4", "__H.st('more')")
    # remove note 2 after drafting, then add a note: 1, 3 and 4 everywhere
    click("more", '[data-oui-remove="2"]')
    ev("m_rm", "__H.st('more')")
    click("more", "[data-oui-chip]")
    click("more", 'td[data-oui-k="cell:1.service"]')
    note("fourth one")
    ev("m_live4", "__H.st('more').live")
    ev("m_four", "__H.st('more')")
    click("more", "[data-oui-draft]")
    ev("m_d5", last_insert)
    # unmount and remount: flags and numbers stay; the next note takes 5
    ev("m_idx", "Array.from(document.querySelectorAll('.cell')).findIndex(function(c){return c.dataset.widget==='more'})")
    S.append({"js": "window.__unmount(Array.from(document.querySelectorAll('.cell')).findIndex(function(c){return c.dataset.widget==='more'}))"})
    S.append({"js": "window.__mount(Array.from(document.querySelectorAll('.cell')).findIndex(function(c){return c.dataset.widget==='more'}))"})
    ev("m_remount", "new Promise(function(r){var f=function(){return document.querySelector('[data-widget=\"more\"] [data-oui-pin]')};if(f())return r(1);new MutationObserver(function(_,o){if(f()){o.disconnect();r(1)}}).observe(document.body,{childList:true,subtree:true})}).then(function(){return __H.st('more')})")
    click("more", "[data-oui-chip]")
    click("more", 'td[data-oui-k="cell:3.service"]')
    note("fifth one")
    ev("m_five", "__H.st('more')")
    # Clear notes starts again at 1
    click("more", "[data-oui-clear]")
    ev("m_cleared", "__H.st('more')")
    click("more", 'td[data-oui-k="cell:1.status"]')          # the mode is still on
    note("after the clear")
    ev("m_restart", "__H.st('more')")
    ev("m_calls_all", "__H.calls()")
    return S


@unittest.skipUnless(os.environ.get("OPENUI_TEST_CHROME") == "1", "opt in with OPENUI_TEST_CHROME=1: it launches Chrome")
@unittest.skipUnless(shutil.which("node") and (ROOT / "build" / "node_modules" / "esbuild").exists(), "needs Node and `npm ci` in build/")
class NotesInChrome(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import shoot
        try:
            shoot.find_chrome(None)
        except SystemExit:
            raise unittest.SkipTest("no Chrome found (set $CHROME)")
        cls.td = tempfile.mkdtemp()
        page = P.build_page(cls.td, [1000], NAMES, app_css=APP_CSS)
        steps = program()
        upto = os.environ.get("NOTES_UPTO")  # debugging: stop after the eval step of this name
        if upto:
            steps = steps[: next(i for i, st in enumerate(steps) if st.get("name") == upto) + 1]
        cls.r, cls.out = P.shoot_page(page, Path(cls.td) / "notes.png", 1000, steps, scale=1)
        Path(os.environ.get("NOTES_RECORD", os.path.join(cls.td, "record.json"))).write_text(json.dumps(cls.r, indent=1), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.td, ignore_errors=True)

    def ws(self, t):
        return "".join(str(t).split())

    def test_the_run_has_no_console_errors(self):
        self.assertIn("console errors: 0", self.out)
        self.assertIn("failed requests: 0", self.out)

    def test_the_chip_is_hidden_then_shown_on_hover_and_moves_nothing(self):
        r = self.r
        self.assertEqual(r["st_off"]["chipOpacity"], "0")
        self.assertNotEqual(r["chip_hover"]["chipOpacity"], "0")
        self.assertEqual(r["h_off"], r["h_hover"])  # every widget and the body: the same height with the chip showing
        self.assertEqual(r["mode_on"]["chipPos"], [-4, 4])  # an overlay in the top right corner

    def test_the_mode_hint_hover_label_and_inert_controls(self):
        r = self.r
        self.assertEqual((r["mode_on"]["pressed"], r["mode_on"]["mode"]), ("true", True))
        self.assertEqual(r["mode_on"]["hint"], "Click anything or select text to add a note. Shift+click picks the parent. Esc to finish.")
        self.assertGreater(r["mode_on"]["stops"], 5)
        self.assertEqual(r["hover_cell"]["hover"], "Table, row 2, status")  # plain words: the type and the place, not the variable name
        self.assertFalse(r["label_vs_item"])  # the label does not sit on the words of the cell it names
        self.assertEqual(r["buttons"]["calls"], 0)  # a Button and a Choice were clicked: nothing was sent
        self.assertEqual(r["buttons"]["st"]["pins"], [])
        self.assertIsNone(r["buttons"]["st"]["editor"])

    def test_the_editor_and_its_keys(self):
        r = self.r
        e = r["editor_open"]["editor"]
        self.assertEqual((e["role"], e["ph"], e["focused"], e["inside"], e["saveDisabled"], e["max"]), ("dialog", "What should the agent look at or answer?", True, True, True, 1000))
        self.assertEqual(e["label"], "Note on Table, row 2, status")
        self.assertEqual(r["ime"], {"open": True, "value": "Is this expected?", "pins": 0})  # Enter while composing saves nothing and keeps the text
        self.assertIsNotNone(r["empty_enter"]["editor"])  # an empty note cannot be saved
        s = r["saved1"]
        self.assertEqual([p["n"] for p in s["pins"]], ["1"])
        self.assertEqual(s["live"], "Note 1 added")
        self.assertEqual(s["focus"], "button#chip")  # focus returns to what opened it
        self.assertEqual(r["two_lines"]["value"], "Which restart is this?\nSecond line")  # Shift+Enter is a new line
        self.assertEqual(r["steal_1"], 0)  # typing in the editor reaches no type-to-focus rule

    def test_escape_is_prevented_only_when_it_closed_something(self):
        r = self.r
        self.assertTrue(r["esc_editor"]["key"]["dp"])
        self.assertIsNone(r["esc_editor"]["st"]["editor"])
        self.assertTrue(r["esc_editor"]["st"]["mode"])  # the first Escape closed the editor only
        self.assertTrue(r["left_mode"]["key"]["dp"])
        self.assertFalse(r["left_mode"]["st"]["mode"])  # the next one left the mode
        self.assertFalse(r["esc_idle"]["dp"])  # nothing to close: the app's Escape (stop a turn) is left alone

    def test_text_notes_quote_exactly_what_was_selected(self):
        r = self.r
        for sel, ed in (("md_selection", "md_editor"), ("dbl_selection", "dbl_editor"), ("callout_selection", "callout_editor"), ("faq_selection", "faq_editor"), ("code_selection", "code_editor"), ("cell_selection", "cell_editor")):
            quote = self.ws(r[sel])
            self.assertTrue(quote, sel)
            text = r[ed]["text"] if "text" in r[ed] else r[ed]["editor"]["text"]
            self.assertIn(quote, self.ws(text), sel)
        self.assertEqual(r["dbl_selection"], "across")
        self.assertEqual(r["dbl_count"], 0)  # the double-click stopped at the widget root
        self.assertEqual(r["dbl_tray"], 0)  # and one on the tray stops there with the mode off
        for sel, ed in (("svg_selection", "svg_editor"), ("chart_selection", "chart_editor")):  # SVG labels select with the app's stylesheet inlined
            self.assertTrue(self.ws(r[sel]), sel)
            self.assertIn(self.ws(r[sel]), self.ws(r[ed]["text"]), sel)
        self.assertRegex(r["code_editor"]["label"], r"CodeBlock, lines \d")
        notes = json.loads(r["before_remount"]["store"])
        code = [n for n in notes if n["ctype"] == "CodeBlock"][0]
        self.assertRegex(code["lines"], r"^\d+(-\d+)?$")  # a code note carries its line numbers
        self.assertTrue(all(n["quote"] for n in notes if n["ctype"] in ("Markdown", "Callout", "Faq", "CodeBlock")))

    def test_pins_highlights_the_tray_and_numbering(self):
        r = self.r
        a = r["saved_all"]
        self.assertEqual([p["n"] for p in a["pins"]], ["1", "2", "3", "4", "5", "6", "7"])
        self.assertTrue(all(p["inside"] for p in a["pins"]))
        self.assertGreaterEqual(len(a["hl"]), 5)  # one highlight per quoted note
        self.assertIn(self.ws(r["md_selection"]), [self.ws(h) for h in a["hl"]])
        self.assertTrue(r["flash"])  # a click on a row flashes its target
        self.assertEqual([p["n"] for p in r["removed"]["pins"]], ["1", "2", "3", "4", "5", "6"])  # numbers move up after a removal
        self.assertIn("Delete", r["edit_open"]["buttons"])  # a pin opens the editor on its note (edit or delete)
        self.assertEqual(r["edit_open"]["value"], "Is this expected?")
        self.assertTrue(r["edit_esc"])
        self.assertEqual(r["left_mode"]["st"]["trayInFlow"], "static")  # the tray is part of the widget, in the flow
        self.assertGreaterEqual(len(r["tray_off"]["rows"]), 6)  # and works with the mode off

    def test_drafting_calls_only_insert_text_and_focus(self):
        r = self.r
        calls = r["calls_2"]
        self.assertEqual([list(c)[0] for c in calls], ["insertText", "focus"])
        args = calls[0]["insertText"]
        self.assertIsNone(args[0])  # no data-composer-target around this widget: as before
        self.assertEqual(args[2], {"mode": "block"})
        self.assertTrue(args[1].startswith("Notes on widget `text` (6). Please answer each note by its number."))
        self.assertTrue(all(ord(c) < 128 for c in args[1]))
        self.assertEqual(calls[1]["focus"], [None])
        self.assertEqual(r["drafted_ok"]["done"], "Added 6 notes to your message box. Edit it if you like, then send.")
        self.assertTrue(r["drafted_ok"]["clearDone"])
        self.assertIsNone(r["drafted_ok"]["draftBtn"])
        self.assertEqual(r["drafted_ok"]["allin"], "All 6 notes are in your message box.")
        self.assertEqual(r["add_again"], "Add 1 edited note to your message")        # an edited note is offered again; no other
        f = r["drafted_fail"]["fail"]
        self.assertIn("Could not reach the message box. Copy this and paste it into the chat.", f["text"])
        self.assertEqual(f["select"], "text")
        self.assertTrue(f["pre"].startswith("More notes on widget `text` (1 edited). These continue the numbering of the earlier message;"), f["pre"])
        self.assertIn("\n1. (edited) ", f["pre"])
        self.assertEqual(r["drafted_fail"]["states"][0], "edited")                    # a failed draft marks nothing: still edited, the others still in the box
        self.assertEqual(r["drafted_fail"]["draftBtn"], "Add 1 edited note to your message")
        self.assertTrue(r["drafted_throw"])  # a composer that throws takes the same path
        for c in r["calls_3"]:
            self.assertNotIn("submit", c)
            self.assertNotIn("setDraft", c)

    def test_notes_survive_an_unmount_and_remount(self):
        r = self.r
        self.assertTrue(r["unmounted"])
        self.assertEqual(len(r["remounted"]["pins"]), 6)
        self.assertEqual(r["remounted"]["pins"][1]["label"], r["before_remount"] and r["remounted"]["pins"][1]["label"])
        self.assertTrue(r["remounted"]["hl"])  # the quotes were found again
        self.assertTrue(json.loads(r["before_remount"]["store"]))  # mirrored in sessionStorage

    def test_one_item_of_each_of_the_nine_hosts_and_a_whole_chart(self):
        r = self.r
        want = {"dag": "Dag, node build", "erd": "Erd, orders, column user_id", "infra": "InfraMap, node api", "seq": "SequenceDiagram, message m2",
                "metric": "Metric, 1st of 2, Error rate", "bar": "BarChart, bar api", "geo": "GeoMap, pin web", "image": "Image", "line": "LineChart"}
        for name, text in want.items():
            self.assertTrue(r["he_" + name].startswith(text), (name, r["he_" + name]))
            self.assertTrue(r["hh_" + name], name)  # the hover label names the item
        self.assertEqual(len(r["hosts_saved"]["pins"]), 9)
        self.assertTrue(all(p["inside"] for p in r["hosts_saved"]["pins"]))
        self.assertEqual(r["he_participant"], "Note on SequenceDiagram, participant client")
        self.assertEqual((r["hosts_after_draft"]["draftBtn"], r["hosts_after_draft"]["states"]), ("Add 9 notes to your message", [""] * 9))   # a draft that failed marks nothing
        msg = r["hosts_calls"]["insertText"][1]
        self.assertIn("1. `dag` (Dag) > node `build`\n   note on dag", msg)
        self.assertIn("4. `seq` (SequenceDiagram) > message `m2`", msg)
        self.assertIn("9. `line` (LineChart) > whole chart", msg)

    def test_tabs(self):
        r = self.r
        self.assertIn("tab Details", r["tab_saved"]["rows"][0])
        self.assertIn("not visible now", r["tab_hidden"]["rows"][0])
        self.assertEqual(r["tab_hidden"]["pins"], [])
        self.assertEqual(len(r["tab_back"]["pins"]), 1)
        self.assertIn("1. `tb` (Table) [tab \"Details\"] > row 2, column `jobs`, cell \"9\"\n   Why is w2 busy?", r["tabs_calls"]["insertText"][1])

    def test_tooltips_are_suspended_in_the_mode_and_come_back(self):
        r = self.r
        self.assertTrue(r["tip_before"])
        self.assertFalse(r["tip_in_mode"]["tipShown"])
        self.assertTrue(r["tip_after"])

    def test_the_keyboard_reaches_items_and_enter_opens_the_editor(self):
        r = self.r
        self.assertEqual(r["cursors"], "pointer")  # an item is clickable in the mode
        self.assertEqual(r["blank_focus"], "div")  # a click on the hint bar put the focus on the widget root
        self.assertEqual(r["blank_esc"]["mode"], False)
        self.assertTrue(r["blank_esc"]["key"]["dp"])
        self.assertTrue(r["tab_focus"]["f"])
        self.assertTrue(r["tab_focus"]["hover"])
        self.assertIn("Markdown", r["tab_enter"])
        self.assertEqual(r["tab_back_focus"], r["tab_focus"]["f"])  # the editor gave the focus back

    def test_notes_mode_on_one_widget_changes_no_other_widget(self):
        r = self.r
        for k in ("plain@1000px", "inline@1000px", "tip@1000px"):
            self.assertEqual(r["h_text_mode"][k], r["h_off"][k], k)
        self.assertEqual(r["end_state"]["plain"]["h"], r["h_off"]["plain@1000px"])

    def test_the_pin_of_a_text_note_sits_at_its_words_and_the_words_stay_marked_while_typing(self):
        r = self.r
        self.assertEqual(r["md_editor"]["pending"], [" ".join(r["md_selection"].split())])   # the picked words are marked while the editor is open
        self.assertIsNone(r["esc_editor"]["st"]["pending"])                                  # and unmarked when it closes
        s = r["saved2"]
        words = s["hlr"][0]                       # the Markdown note's highlight: [x, y, w, h, text]
        pin = s["pins"][1]
        self.assertEqual(pin["n"], "2")
        self.assertTrue(pin["inside"])
        pb = (pin["x"], pin["y"], pin["x"] + pin["w"], pin["y"] + pin["h"])
        wb = (words[0], words[1], words[0] + words[2], words[1] + words[3])
        self.assertTrue(pb[2] <= wb[0] or pb[0] >= wb[2] or pb[3] <= wb[1] + 3.5 or pb[1] >= wb[3], (pb, wb))  # above the words (at most 3 px into the line box, over the leading), not on the first letter
        self.assertLess(abs(pb[2] - wb[0]) + abs(pb[1] - wb[1]), 40, (pb, wb))                           # and it sits right at the start of the words
        self.assertTrue(pin["x"] + pin["w"] < r["saved2"]["chip"][0] - 40)                               # not beside the Notes chip

    def test_one_tab_stop_per_component_and_arrows_between_the_items(self):
        r = self.r
        b = r["big_stops"]
        self.assertEqual(b["comps"], 2)
        self.assertLessEqual(b["tab0"], b["comps"])        # a 100 row, 3 column table is ONE stop (not 300)
        self.assertGreaterEqual(b["all"], 300)             # and every cell is still reachable by the arrows
        self.assertEqual(r["tab_1"], "div")                # Tab: the paragraph (a component with no items)
        self.assertEqual(r["tab_2"], "th[col:a]")          # Tab: the table, at its first item (the first column header)
        self.assertEqual(r["arrow_right"], "th[col:b]")
        self.assertEqual(r["arrow_down"], "th[col:c]")     # right and down: the next item in reading order
        self.assertEqual(r["arrow_left"]["f"], "th[col:b]")
        self.assertTrue(r["arrow_left"]["dp"]["dp"])       # the arrows do not scroll the page
        self.assertEqual(r["shift_tab"], "div")
        self.assertEqual(r["tab_return"], "th[col:b]")     # Tab comes back to the item you left on (roving)

    def test_a_selection_ending_after_a_line_break_stops_at_the_line_before(self):
        r = self.r
        self.assertEqual(r["code_lines"][0][0], "1-2")
        self.assertEqual(r["code_lines"][0][1], "first line second line")
        code = json.loads(r["before_remount"]["store"])
        self.assertEqual([n["lines"] for n in code if n["ctype"] == "CodeBlock"], ["1-2"])    # the same on the walk's own code note

    def test_the_chip_closes_the_editor_and_a_draft_ends_the_mode(self):
        r = self.r
        self.assertEqual(r["chip_closes"], {"mode": False, "editor": None})
        self.assertGreaterEqual(r["mode_on"]["chip"][3], 24)        # touch targets: at least 24 px
        self.assertGreaterEqual(r["saved_all"]["removeMin"], 24)
        d = r["after_tile"]
        self.assertFalse(d["mode"])                                  # the notes are in the message box: the mode is over
        self.assertTrue(d["focusClear"])                             # and the focus stays in the tray, on "Clear notes"
        self.assertGreaterEqual(d["rowOpacity"], 0.85)               # rows of drafted notes are not dimmed away: they carry a label instead
        self.assertEqual(d["states"], ["in your message"])
        self.assertTrue(r["hosts_after_draft"]["mode"])              # a draft that FAILED (the composer threw) leaves the mode on

    def test_a_note_whose_words_cannot_be_found_keeps_its_pin_away_from_the_chip(self):
        s = self.r["span_saved"]
        self.assertEqual(len(s["pins"]), 1)
        pin, chip = s["pins"][0], s["chip"]
        self.assertLess(pin["x"], 30)                   # the top left of the component
        self.assertLess(pin["x"] + pin["w"], chip[0])   # left of the chip, not beside it

    def test_a_half_typed_note_is_kept_and_an_empty_editor_moves(self):
        r = self.r
        e = r["half_blocked"]
        self.assertEqual(e["value"], "half typed")                                    # still there
        self.assertIn("row 2, status", e["text"])                                     # the editor did not move
        self.assertEqual(e["err"], "Save or cancel this note first.")                 # said inside the card
        self.assertEqual(e["pulse"], "1")                                             # and the card flashed once
        self.assertEqual(r["half_blocked_2"]["pulse"], "2")                           # every blocked click flashes again
        self.assertIs(r["half_card_clear"], False)                                    # the card did not cover the item it is about
        self.assertIn("row 1, service", r["empty_moves"]["text"])                     # an empty editor just moves to the new item
        self.assertEqual(r["empty_moves"]["value"], "")

    def test_the_21st_note_is_told_where_the_user_is_looking(self):
        r = self.r
        msg = "20 notes is the most per widget."
        self.assertEqual(r["limit_20"], 20)
        s = r["limit_21"]
        self.assertEqual((s["hint"], s["hover"], s["pins"]), (msg, msg, 20))          # hint bar and hover label
        self.assertIsNone(s["editor"])
        self.assertEqual(s["info"], msg)                                              # and the tray keeps it
        self.assertEqual(r["limit_moved"]["hint"], "Click anything or select text to add a note. Shift+click picks the parent. Esc to finish.")   # the next pointer move ends it

    def test_notes_for_another_version_of_the_source_are_set_aside_until_kept(self):
        r = self.r
        self.assertEqual(len(r["stale_before"]["pins"]), 2)
        st = r["stale_state"]                      # same file stem, other content, remounted
        self.assertIn("These notes were written for an earlier version of this widget.", st["staleText"])
        self.assertIn("Keep them", st["staleText"])
        self.assertIn("Clear them", st["staleText"])
        self.assertEqual((st["pins"], st["rows"], st["draftBtn"], st["chipText"]), ([], [], None, "Notes"))   # no pin, no row, nothing to draft
        first = r["stale_draft"]["insertText"][1]
        self.assertTrue(first.startswith("Notes on widget `stale` (1)."), first)       # only the note written for THIS version
        self.assertIn("new note", first)
        self.assertNotIn("about the cell", first)
        self.assertNotIn("about the title", first)
        k = r["stale_kept"]
        self.assertIsNone(k["staleText"])
        self.assertEqual(len(k["pins"]), 2)         # the cell note and the new one; the note on `title` is about a Markdown and `title` is a Text now
        self.assertEqual(len(k["rows"]), 3)
        self.assertIn("not in this widget now", k["rows"][1] + k["rows"][2])
        second = r["stale_draft2"]["insertText"][1]                  # the new note was drafted before: only the two kept notes go now, numbered after it
        self.assertTrue(second.startswith("More notes on widget `stale` (2 new)."), second)
        self.assertIn("\n2. `tbl` (Table) > row 2, column `status`, cell \"CrashLoop\"\n   about the cell", second)
        self.assertIn("\n3. `title` (Markdown) > whole component\n   about the title", second)
        self.assertNotIn("new note", second.split("\n\n", 1)[1])
        self.assertEqual(k["states"][0], "in your message")

    def test_a_second_draft_carries_only_the_new_notes_the_owners_case(self):
        r = self.r
        first = r["m_d1"]["insertText"]
        self.assertTrue(first[1].startswith("Notes on widget `more` (2). Please answer each note by its number."), first[1])
        self.assertIn("1. `tbl` (Table) > row 1, column `status`, cell \"up\"\n   first one", first[1])
        self.assertIn("2. `tbl` (Table) > row 2, column `status`, cell \"CrashLoop\"\n   second one", first[1])
        t = r["m_two"]
        self.assertEqual(t["draftBtn"], "Add 2 notes to your message")                     # nothing drafted yet: as before
        self.assertEqual(r["m_after1"]["allin"], "All 2 notes are in your message box.")
        self.assertEqual(r["m_after1"]["states"], ["in your message", "in your message"])
        a = r["m_added"]                                                                 # a third note
        self.assertEqual(a["draftBtn"], "Add 1 new note to your message")
        self.assertEqual(a["states"], ["in your message", "in your message", ""])        # new rows look normal
        self.assertEqual(a["pinNums"], ["1", "2", "3"])
        self.assertEqual(r["m_live3"], "Note 3 added")
        self.assertGreaterEqual(a["rowOpacity"], 0.85)
        second = r["m_d2"]["insertText"][1]
        self.assertTrue(second.startswith("More notes on widget `more` (1 new). These continue the numbering of the earlier message. Please answer each note by its number."), second)
        self.assertIn("\n3. `tbl` (Table) > row 3, column `status`, cell \"up\"\n   third one", second)
        for gone in ("first one", "second one", "\n1. ", "\n2. "):                         # none of the earlier notes comes again
            self.assertNotIn(gone, second)
        self.assertEqual(r["m_copied"], [second])                                        # Copy puts exactly the message the button drafts on the clipboard
        self.assertTrue(r["m_copied2"][1].startswith("Notes on widget `more` (3)."))     # with nothing new: what "Add all again" would draft
        self.assertIn("first one", r["m_copied2"][1])
        a2 = r["m_after2"]
        self.assertIsNone(a2["draftBtn"])                                                # nothing new: no primary button
        self.assertEqual(a2["allin"], "All 3 notes are in your message box.")
        self.assertEqual(a2["trayButtons"], ["Add all again", "Clear notes", "Copy"])
        self.assertEqual(a2["done"], "Added 1 new note to your message box. Edit it if you like, then send.")
        self.assertEqual(r["m_n2"] - r["m_n0"], 2)                                            # two drafts so far on this widget

    def test_an_edited_note_goes_again_with_its_number_and_a_failed_draft_marks_nothing(self):
        r = self.r
        e = r["m_edited"]
        self.assertEqual(e["draftBtn"], "Add 1 edited note to your message")
        self.assertEqual(e["states"], ["edited", "in your message", "in your message"])
        self.assertEqual(r["m_fail"]["draftBtn"], "Add 1 edited note to your message")  # insertText said false: nothing was marked
        self.assertEqual(r["m_fail"]["states"], ["edited", "in your message", "in your message"])
        self.assertIn("More notes on widget `more` (1 edited).", r["m_fail"]["fail"]["pre"])
        third = r["m_d3"]["insertText"][1]
        self.assertTrue(third.startswith("More notes on widget `more` (1 edited). These continue the numbering of the earlier message; an edited note replaces the earlier note with the same number."), third)
        self.assertIn("\n1. (edited) `tbl` (Table) > row 1, column `status`, cell \"up\"\n   Edited: first one", third)
        self.assertNotIn("second one", third)
        self.assertNotIn("third one", third)
        self.assertEqual(r["m_after3"]["allin"], "All 3 notes are in your message box.")

    def test_add_all_again_sends_every_note_with_the_original_header_and_the_same_numbers(self):
        r = self.r
        t = r["m_d4"]["insertText"][1]
        self.assertTrue(t.startswith("Notes on widget `more` (3). Please answer each note by its number."), t)
        self.assertNotIn("More notes", t)
        self.assertNotIn("(edited)", t)
        for want in ("\n1. `tbl`", "\n2. `tbl`", "\n3. `tbl`", "Edited: first one", "second one", "third one"):
            self.assertIn(want, t)

    def test_numbers_stay_once_a_draft_went_through_and_start_over_with_clear(self):
        r = self.r
        rm = r["m_rm"]                                                                    # note 2 removed after the draft: a gap, no renumbering
        self.assertEqual((rm["pinNums"], rm["rowNums"], rm["removeNums"]), (["1", "3"], ["1", "3"], ["1", "3"]))
        self.assertEqual(r["m_live4"], "Note 4 added")
        f = r["m_four"]                                                                   # the new note: 4 on the pin, the row, the remove button
        self.assertEqual((f["pinNums"], f["rowNums"], f["removeNums"]), (["1", "3", "4"], ["1", "3", "4"], ["1", "3", "4"]))
        self.assertEqual(f["pins"][2]["label"].split(" on ")[0], "Note 4")
        self.assertEqual(f["draftBtn"], "Add 1 new note to your message")
        fifth = r["m_d5"]["insertText"][1]
        self.assertTrue(fifth.startswith("More notes on widget `more` (1 new)."), fifth)
        self.assertIn("\n4. `tbl` (Table) > row 1, column `service`, cell \"web\"\n   fourth one", fifth)
        self.assertNotIn("\n3. ", fifth)
        self.assertEqual(json.loads(r["m_remount"]["meta"]), {"frozen": True, "top": 4})  # the counter is stored with the list
        m = r["m_remount"]                                                                # unmount and remount: flags and numbers stay
        self.assertEqual((m["pinNums"], m["states"], m["draftBtn"]), (["1", "3", "4"], ["in your message"] * 3, None))
        self.assertEqual(m["allin"], "All 3 notes are in your message box.")
        self.assertEqual(r["m_five"]["pinNums"], ["1", "3", "4", "5"])                    # and the next note takes 5
        c = r["m_cleared"]
        self.assertIsNone(c["tray"])
        self.assertIsNone(c["meta"])                                                      # Clear forgets the counter
        self.assertEqual(r["m_restart"]["pinNums"], ["1"])                                # and the next note is 1 again
        self.assertEqual(r["m_restart"]["draftBtn"], "Add 1 note to your message")
        for c in r["m_calls_all"]:
            self.assertNotIn("submit", c)
            self.assertNotIn("setDraft", c)

    def test_the_composer_of_the_chat_that_holds_the_widget_is_addressed(self):
        r = self.r
        def check(key, addr, widget):
            ins, foc = r[key]
            a = ins["insertText"]
            self.assertEqual((a[0], a[2]), (addr, {"mode": "block"}), key)  # exactly these arguments, in this order
            self.assertTrue(a[1].startswith("Notes on widget `%s` (1)." % widget), key)
            self.assertEqual(foc, {"focus": [addr]}, key)
        check("route_tile", "stored-7", "plain")        # tile:stored-7 -> the tile's id
        check("route_main", "run-42", "inline")         # main -> the runtime id the primary chat shows
        check("route_main_new", "new", "tip")           # main, fresh draft with no session id -> "new"
        self.assertEqual((r["calls_2"][0]["insertText"][0], r["calls_2"][1]), (None, {"focus": [None]}))  # no marker -> null, as before
        for c in r["calls_3"]:
            self.assertNotIn("submit", c)
            self.assertNotIn("setDraft", c)

    def test_in_the_mode_a_thin_line_is_caught_by_its_hit_shape(self):
        h = self.r["hits_mode"]
        self.assertTrue(h["seq_m2"]["hit_shape"], h)       # off, the pointer reaches the visible line (see LayoutWithNotesOff)
        self.assertTrue(h["infra_web_api"]["hit_shape"], h)


@unittest.skipUnless(os.environ.get("OPENUI_TEST_CHROME") == "1", "opt in with OPENUI_TEST_CHROME=1: it launches Chrome")
@unittest.skipUnless(shutil.which("node") and (ROOT / "build" / "node_modules" / "esbuild").exists(), "needs Node and `npm ci` in build/")
class LayoutWithNotesOff(unittest.TestCase):
    """The wrappers, the chip, the hit shapes and the mode move nothing: the same widgets at four column widths, drawn by the plugin of
    this checkout, compared with a stored baseline (tests/fixtures/notes-layout-baseline.json) that was measured once from the release
    before Notes. No git history is read. The baseline is bound to the machine that measured it (fonts, Chrome): the test skips on
    another platform or with another app stylesheet; regenerate it with tests/notes_probe.py --baseline."""
    FIXTURE = HERE / "fixtures" / "notes-layout-baseline.json"
    TOL = 0.5

    def close(self, a, b, path):
        if isinstance(a, dict):
            self.assertEqual(sorted(a), sorted(b), path)
            for k in a:
                self.close(a[k], b[k], path + "." + k)
        elif isinstance(a, list):
            self.assertEqual(len(a), len(b), path)
            for i, (x, y) in enumerate(zip(a, b)):
                self.close(x, y, "%s[%d]" % (path, i))
        elif isinstance(a, (int, float)) and not isinstance(a, bool):
            self.assertLessEqual(abs(a - b), self.TOL, "%s: %s against the release before Notes %s" % (path, a, b))
        else:
            self.assertEqual(a, b, path)

    def test_layout_matches_the_release_before_notes_at_360_700_1000_and_1800(self):
        import shoot
        try:
            shoot.find_chrome(None)
        except SystemExit:
            self.skipTest("no Chrome found (set $CHROME)")
        base = json.loads(self.FIXTURE.read_text(encoding="utf-8"))
        if base["platform"] != platform.system() or base["app_css"] != (APP_CSS.name if APP_CSS else None):
            self.skipTest("the baseline was measured on %s with %s" % (base["platform"], base["app_css"]))
        names, widths = base["names"], base["widths"]
        steps = [{"js": P.LAYOUT_JS}, {"eval": "JSON.stringify(__lay())", "name": "off"}, {"eval": "JSON.stringify(__all())", "name": "off_all"}, {"eval": "JSON.stringify(__hits())", "name": "hits"}]
        for c in range(1, len(widths) + 1):  # the chip shows on every widget, at every width, one hover at a time
            for n in range(1, len(names) + 1):
                steps.append({"move": "#page > section:nth-child(%d) .cell:nth-of-type(%d) .hermes-openui-root" % (c, n), "at": [0.5, 0.1]})
                steps.append({"eval": "getComputedStyle(document.querySelector('#page > section:nth-child(%d) .cell:nth-of-type(%d) [data-oui-chip]')).opacity" % (c, n), "name": "chip_%d_%d" % (c, n)})
                steps.append({"eval": "JSON.stringify(__all())", "name": "hov_%d_%d" % (c, n)})
        steps.append({"eval": "JSON.stringify(__lay())", "name": "again"})
        with tempfile.TemporaryDirectory() as td:
            page = P.build_page(td, widths, names, app_css=APP_CSS)
            new, _ = P.shoot_page(page, Path(td) / "n.png", sum(widths) + 24 * 4, steps)
        off = json.loads(new["off"])
        self.assertEqual(len(off), len(names) * len(widths) + 1)
        self.close(off, base["layout"], "layout")  # every widget box, its structural elements and the body height
        # with Notes off the pointer reaches the same thing at the middle of a thin diagram line as before: the visible line, under its <title>
        self.assertEqual(json.loads(new["hits"]), base["hits"])
        for k, v in new.items():
            if k.startswith("hov_"):
                self.assertEqual(json.loads(v), json.loads(new["off_all"]), k)  # the chip showing moves nothing, body height included
            if k.startswith("chip_"):
                self.assertNotEqual(v, "0", k)
        self.assertEqual(json.loads(new["again"]), off)


def program_360():
    S = [{"js": HELPERS}]

    def ev(name, js):
        S.append({"eval": "__H.after(function(){return (" + js + ");})", "name": name})

    # the hover label next to the Table cell that the review found it on (row 2, status: CrashLoop)
    S.append({"click": '[data-widget="text"] [data-oui-chip]'})
    S.append({"move": '[data-widget="text"] td[data-oui-k="cell:2.status"]'})
    ev("label_360", "{text: __H.st('text').hover, hits: __H.labelHits('text', 'td[data-oui-k=\"cell:2.status\"]'), box: __H.st('text').labelBox, root: __H.st('text').w}")
    S.append({"key": "Escape"})
    # a Tooltip panel that is open when the mode starts: still there after Escape?
    panel = "!!document.querySelector('[data-widget=\"tip\"] [data-tip-panel]')"
    S.append({"move": '[data-widget="tip"] td[data-oui-k="cell:2.status"]'})
    ev("tip_hover", "__H.st('tip').tipShown")
    S.append({"click": '[data-widget="tip"] td[data-oui-k="cell:2.status"]'})
    ev("tip_open", "{panel: %s, mode: __H.st('tip').mode}" % panel)
    S.append({"click": '[data-widget="tip"] [data-oui-chip]'})
    ev("tip_in_mode", "{panel: %s, mode: __H.st('tip').mode, tipShown: __H.st('tip').tipShown}" % panel)
    S.append({"key": "Escape"})
    ev("tip_after_esc", "{panel: %s, mode: __H.st('tip').mode, tipShown: __H.st('tip').tipShown, focus: __H.st('tip').focus}" % panel)
    return S


@unittest.skipUnless(os.environ.get("OPENUI_TEST_CHROME") == "1", "opt in with OPENUI_TEST_CHROME=1: it launches Chrome")
@unittest.skipUnless(shutil.which("node") and (ROOT / "build" / "node_modules" / "esbuild").exists(), "needs Node and `npm ci` in build/")
class NotesAt360(unittest.TestCase):
    """The narrowest column (360 px), one Chrome launch: the hover label does not cover the cell it names, and the Tooltip panel that
    was open when the mode started is still open after Escape."""

    @classmethod
    def setUpClass(cls):
        import shoot
        try:
            shoot.find_chrome(None)
        except SystemExit:
            raise unittest.SkipTest("no Chrome found (set $CHROME)")
        cls.td = tempfile.mkdtemp()
        page = P.build_page(cls.td, [360], ["text", "tip"], app_css=APP_CSS)
        cls.r, cls.out = P.shoot_page(page, Path(cls.td) / "n360.png", 360 + 24, program_360(), scale=1)
        Path(os.environ.get("NOTES_RECORD", os.path.join(cls.td, "record360.json"))).write_text(json.dumps(cls.r, indent=1), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.td, ignore_errors=True)

    def test_the_hover_label_does_not_cover_the_cell_it_names(self):
        l = self.r["label_360"]
        self.assertEqual(l["text"], "Table, row 2, status")
        self.assertIs(l["hits"], False)                              # no overlap with any line of the cell's text
        self.assertGreaterEqual(l["box"][0], 0)                      # and the label stays inside the widget
        self.assertLessEqual(l["box"][0] + l["box"][2], l["root"] + 0.5)

    def test_a_tooltip_panel_open_when_the_mode_starts_is_still_open_after_escape(self):
        r = self.r
        self.assertTrue(r["tip_hover"])
        self.assertTrue(r["tip_open"]["panel"])
        self.assertTrue(r["tip_in_mode"]["mode"])
        self.assertFalse(r["tip_after_esc"]["mode"])
        self.assertTrue(r["tip_after_esc"]["panel"], r["tip_after_esc"])
