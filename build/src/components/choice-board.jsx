// The Choice board: the one place where the answers to every Choice of a widget are staged, and the bar that sends them together.
// Why it is not state of the Choice component: Tabs unmounts a hidden tab, so a question on it would lose its answer on a tab switch, and a widget with
// several Choices needs ONE count and ONE Send button outside Tabs and Cards. The board is provided at the widget root (core.jsx for the preview page,
// plugin/plugin.jsx for the native renderer) and reads the PARSED tree (Renderer's onParseResult), so a question on a tab that was never shown counts.
// Nothing is sent by a click on an option. The pure rules (state, message, limits, storage) are choice-core.js.
// Shared with the packs through window.__HM.mods["hermes-openui/choice-board"] (build.mjs SHARED_FILES): the Choice view lives in the text pack and must
// read the SAME context object as the board the core provides.
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { C, TONES } from "../theme.js";
import {
  collectChoices, fitMessage, createBoardStore, progress, reviveBoard, setOtherText, toggleOption, toggleOther,
} from "./choice-core.js";

// What the Choice view (in the text pack) needs of the pure module comes through here, so the pack takes ONE copy of it from the core (SHARED_FILES).
export { makeChoice, cleanOther } from "./choice-core.js";

const STORE = createBoardStore(() => window.sessionStorage); // native only (preview keeps the board for the life of the page)

const NONE = { choices: [], answers: {}, sent: false, busy: false, inert: false, toggle() {}, toggleOther() {}, setText() {}, locked: true };
const Ctx = createContext(NONE);
export const useBoard = () => useContext(Ctx);

const sameKeys = (a, b) => a.length === b.length && a.every((c, i) => c.key === b[i].key);

// The nearest ancestor that also holds the bar: the scope of "the next question" and of "the bar" for the keyboard, when a page holds several widgets.
export function boardScope(el) {
  for (let n = el && el.parentElement; n; n = n.parentElement) if (n.querySelector("[data-oui-bar]")) return n;
  return null;
}

/**
 * props: stem (the widget file stem, native only), mode ("preview" | "native"), send(text) -> Promise<{ok, error?}> | {ok, error?} (the host path of this
 * mode; a module-level function of the core or the plugin, never an action an agent can write), canSend (false on an exported page: no chat to send to),
 * rootRef (native: the widget root, to follow notes mode), children(onParseResult) -> the Renderer.
 */
export function ChoiceBoard({ stem, mode, send, canSend = true, rootRef, children }) {
  const persist = mode === "native" && !!stem;
  const [choices, setChoices] = useState([]);
  const [board, setBoard] = useState({ answers: {}, sent: false });
  const [status, setStatus] = useState({ busy: false, error: "" });
  const [inert, setInert] = useState(false);
  const busy = useRef(false);
  const hydrated = useRef(false);
  const refocus = useRef(false); // the Send button had the focus when the answers went out: the status line takes it (the button is gone), else the focus stays where it is

  const onParse = useCallback((result) => {
    const next = collectChoices(result && result.root);
    setChoices((prev) => (sameKeys(prev, next) ? prev : next));
    if (!hydrated.current) {
      hydrated.current = true;
      setBoard(persist ? reviveBoard(STORE.get(stem), next) : { answers: {}, sent: false });
    } else {
      setBoard((prev) => reviveBoard(prev, next)); // the source changed: keep what still fits
    }
  }, [persist, stem]);

  useEffect(() => { if (persist && hydrated.current) STORE.set(stem, board); }, [board, persist, stem]);

  // Notes mode (native): every control of a widget is inert, this one too.
  useEffect(() => {
    const el = rootRef && rootRef.current;
    if (!el || typeof MutationObserver === "undefined") return undefined;
    const read = () => setInert(el.hasAttribute("data-oui-mode"));
    read();
    const obs = new MutationObserver(read);
    obs.observe(el, { attributes: true, attributeFilter: ["data-oui-mode"] });
    return () => obs.disconnect();
  }, [rootRef]);

  const locked = board.sent || status.busy || inert;
  const edit = useCallback((fn) => {
    setBoard((b) => (b.sent ? b : { ...b, answers: fn(b.answers) }));
    setStatus((s) => (s.error ? { ...s, error: "" } : s)); // an old "too long" message is not true of the new answers
  }, []);
  const ctx = useMemo(() => ({
    choices, answers: board.answers, sent: board.sent, busy: status.busy, inert, locked,
    toggle: (c, i) => edit((a) => toggleOption(a, c, i)),
    toggleOther: (c) => edit((a) => toggleOther(a, c)),
    setText: (c, t) => edit((a) => setOtherText(a, c, t)),
  }), [choices, board, status.busy, inert, locked, edit]);

  const clear = () => { if (!locked) { setBoard((b) => ({ ...b, answers: {} })); setStatus({ busy: false, error: "" }); } };
  const doSend = async () => {
    if (busy.current || board.sent || inert || !canSend) return; // a second click or a double-click finds the flag already set
    if (!progress(choices, board.answers).answered) return;
    const msg = fitMessage(choices, board.answers, mode === "native" ? stem : "", mode === "native" ? "native" : "preview");
    if (!msg.ok) { setStatus({ busy: false, error: msg.error }); return; }
    busy.current = true;
    refocus.current = !!(document.activeElement && document.activeElement.hasAttribute && document.activeElement.hasAttribute("data-oui-send"));
    setStatus({ busy: true, error: "" });
    let ack;
    try { ack = await send(msg.text); } catch (e) { ack = { ok: false }; }
    busy.current = false;
    if (ack && ack.ok !== false) {
      setBoard((b) => ({ ...b, sent: true }));
      setStatus({ busy: false, error: "" });
    } else {
      refocus.current = false;
      setStatus({ busy: false, error: (ack && ack.error) || "The answers were not sent. Try again." });
    }
  };

  return (
    <Ctx.Provider value={ctx}>
      {children(onParse)}
      {choices.length ? <SendBar choices={choices} answers={board.answers} sent={board.sent} busy={status.busy} error={status.error} inert={inert} canSend={canSend} refocus={refocus} onSend={doSend} onClear={clear} /> : null}
    </Ctx.Provider>
  );
}

const btn = { font: "inherit", fontSize: 13, fontWeight: 550, borderRadius: 8, padding: "6px 14px", cursor: "pointer", border: `1px solid ${C.accent}` };

function SendBar({ choices, answers, sent, busy, error, inert, canSend, refocus, onSend, onClear }) {
  const line = useRef(null);
  useEffect(() => {
    if (sent && refocus.current && line.current) { refocus.current = false; line.current.focus({ preventScroll: true }); }
  }, [sent, refocus]);
  const { answered, total } = progress(choices, answers);
  const staged = answered > 0 || Object.values(answers).some((a) => a && (a.picks.length || a.other));
  const off = inert || busy || !canSend;
  return (
    <div data-oui-bar="" role="group" aria-label="Send answers" style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "6px 10px", marginTop: 12, padding: "10px 14px", border: `1px solid ${C.border}`, borderRadius: 10 }}>
      <span ref={line} tabIndex={-1} data-oui-count="" aria-live="polite" style={{ fontSize: 13, color: sent ? C.fg : C.muted, flex: "1 1 auto" }}>
        {sent ? "Sent to the agent." : `${answered} of ${total} answered`}
      </span>
      {error ? <span role="alert" style={{ fontSize: 12.5, color: TONES.bad, flexBasis: "100%", order: 3 }}>{error}</span> : null}
      {!canSend && !sent ? <span style={{ fontSize: 12.5, color: C.muted, flexBasis: "100%", order: 3 }}>Interactive buttons work inside Hermes only</span> : null}
      {sent ? null : (
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginLeft: "auto" }}>
          <button type="button" data-oui-clear="" disabled={off || !staged} onClick={onClear} style={{ ...btn, border: "1px solid transparent", background: "transparent", color: C.muted, padding: "6px 10px", opacity: off || !staged ? 0.45 : 1, cursor: off || !staged ? "not-allowed" : "pointer" }}>
            Clear
          </button>
          <button type="button" data-oui-send="" disabled={off || !answered} onClick={onSend} style={{ ...btn, background: C.accent, color: "#fff", opacity: off || !answered ? 0.45 : 1, cursor: off || !answered ? "not-allowed" : "pointer" }}>
            Send answers
          </button>
        </div>
      )}
    </div>
  );
}
