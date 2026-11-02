// Q&A components: collapsible FAQ and the Choice question card.
// Choice stages its answers on the widget's board (components/choice-board.jsx) and sends nothing by itself: one Send answers bar sends them all.
import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { C } from "../theme.js";
import { renderMarkdown } from "./markdown.jsx";
import { boardScope, cleanOther, makeChoice, useBoard } from "./choice-board.jsx";

export function FaqView({ items, firstOpen }) {
  const [open, setOpen] = useState(firstOpen ? 0 : -1);
  return (
    <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden" }}>
      {items.map((it, i) => {
        const isOpen = open === i;
        return (
          <div key={i} style={{ borderTop: i ? `1px solid ${C.border}` : 0 }}>
            <button
              onClick={() => setOpen(isOpen ? -1 : i)}
              style={{ all: "unset", boxSizing: "border-box", width: "100%", cursor: "pointer", padding: "10px 14px", display: "flex", gap: 10, alignItems: "center", fontSize: 14, fontWeight: 550 }}
            >
              <span style={{ color: C.accent, fontWeight: 700, width: 14 }}>{isOpen ? "–" : "+"}</span>
              <span style={{ flex: 1 }}>{it.props.question}</span>
            </button>
            {isOpen ? (
              <div style={{ padding: "0 14px 12px 38px", display: "flex", flexDirection: "column", gap: 8, fontSize: 13.5 }}>{renderMarkdown(it.props.answer)}</div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

// Focus ring, hover and the Other box (the text pack's stylesheet; inline styles cannot say :focus-visible or :hover).
export const CHOICE_CSS = [
  "[data-oui-opt]:focus-visible,[data-oui-send]:focus-visible,[data-oui-clear]:focus-visible{outline:2px solid var(--accent,#5B9CF6);outline-offset:2px}",
  "[data-oui-opt][aria-checked=false]:not(:disabled):hover{background:color-mix(in srgb,var(--foreground,CanvasText) 7%,transparent)!important}",
  "[data-oui-other]::placeholder{color:var(--muted-foreground,GrayText);opacity:1}",
  "[data-oui-other]:focus{outline:none;border-color:var(--accent,#5B9CF6)!important}",
].join("\n");

// The selection indicator: a ROUND radio for a single question and a SQUARE checkbox for a multiple one, so the two kinds read differently at a glance.
// The unselected outline uses the muted text colour (the theme border is far under the 3:1 non-text contrast); a selected one is filled with the accent.
// Both are drawn with CSS and one inline svg path: no icon font and nothing to load. The button around it carries the role and aria-checked.
function Mark({ multiple, on }) {
  return (
    <span aria-hidden="true" data-oui-mark={multiple ? "checkbox" : "radio"} style={{ flex: "none", width: 18, height: 18, marginTop: 1, boxSizing: "border-box", display: "inline-flex", alignItems: "center", justifyContent: "center", borderRadius: multiple ? 4 : "50%", border: `2px solid ${on ? C.accent : C.muted}`, background: on ? C.accent : "transparent" }}>
      {on ? (multiple ? (
        <svg data-oui-check="" viewBox="0 0 12 12" width="12" height="12" aria-hidden="true" focusable="false" style={{ display: "block" }}>
          <path d="M2.2 6.3 L4.8 8.9 L9.8 3.3" fill="none" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : <span data-oui-dot="" style={{ display: "block", width: 6, height: 6, borderRadius: "50%", background: "#fff" }} />) : null}
    </span>
  );
}

function Row({ i, on, dim, disabled, tab, multiple, onPick, onFocus, children, other }) {
  return (
    <button
      type="button"
      role={multiple ? "checkbox" : "radio"}
      data-oui-opt={i}
      data-oui-other-row={other ? "" : undefined}
      aria-checked={on}
      disabled={disabled}
      tabIndex={tab ? 0 : -1}
      onClick={onPick}
      onFocus={onFocus}
      style={{
        font: "inherit", fontSize: 13.5, textAlign: "left", color: C.fg, width: "100%", boxSizing: "border-box", display: "flex", gap: 10, alignItems: "flex-start",
        cursor: disabled ? "default" : "pointer", background: on ? `color-mix(in srgb, ${C.accent} 16%, transparent)` : "transparent",
        border: `1px solid ${on ? C.accent : C.border}`, borderRadius: 8, padding: "8px 12px", opacity: dim ? 0.65 : 1,
      }}
    >
      <Mark multiple={multiple} on={on} />
      <span style={{ flex: 1, minWidth: 0, overflowWrap: "anywhere", lineHeight: "20px" }}>{children}</span>
    </button>
  );
}

export function ChoiceView({ question, options, hint, multiple, other }) {
  const board = useBoard();
  const qid = useId();
  const opts = Array.isArray(options) ? options : [];
  const choice = useMemo(() => makeChoice({ question, options: opts, multiple, other }), [question, options, multiple, other]);
  const a = board.answers[choice.key] || { picks: [], other: false, text: "" };
  const rows = opts.length + (choice.other ? 1 : 0);
  const [rover, setRover] = useState(0);
  const tabAt = Math.min(rover, Math.max(rows - 1, 0));
  const taRef = useRef(null);
  const openedByUser = useRef(false);
  const locked = board.locked;
  const empty = cleanOther(a.text) === "";
  const boxShown = choice.other && a.other && (!board.sent || !empty);

  useEffect(() => { // focus the text box when the user opened it (not when a remount restored it)
    if (a.other && openedByUser.current && taRef.current) { openedByUser.current = false; taRef.current.focus({ preventScroll: true }); }
  }, [a.other]);
  useEffect(() => { // grow with the text, up to a few lines
    const t = taRef.current;
    if (!t) return;
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight + 2, 120) + "px";
  }, [a.text, boxShown]);

  const pick = (i) => board.toggle(choice, i);
  const pickOther = () => { if (!a.other) openedByUser.current = true; board.toggleOther(choice); };

  const onGroupKey = (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const list = Array.from(e.currentTarget.querySelectorAll("[data-oui-opt]"));
    const at = list.indexOf(e.target.closest("[data-oui-opt]"));
    if (at < 0 || e.target.disabled) return;
    const k = e.key;
    const step = k === "ArrowDown" || k === "ArrowRight" ? 1 : k === "ArrowUp" || k === "ArrowLeft" ? -1 : 0;
    if (step) { // arrows move between the options of THIS question
      e.preventDefault(); e.stopPropagation();
      const to = list[(at + step + list.length) % list.length];
      setRover(list.indexOf(to));
      to.focus({ preventScroll: true });
    } else if (k === " " || k === "Enter") e.stopPropagation(); // the button's own click toggles; the composer's type-to-focus must not take the key. No letter shortcut: that rule listens on window in the CAPTURE phase, which a card cannot stop, so a letter would toggle a row AND be typed into the composer
  };
  const onTextKey = (e) => {
    const t = e.currentTarget;
    if (e.key === "Escape") { // a text field swallows Escape; blur it, and say so only when that is what happened
      if (document.activeElement === t) { t.blur(); e.preventDefault(); e.stopPropagation(); }
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey && !e.nativeEvent.isComposing && e.keyCode !== 229) {
      e.preventDefault(); e.stopPropagation(); // Enter never sends; it moves on (Shift+Enter is a new line)
      const card = t.closest("[data-oui-choice]");
      const scope = boardScope(card);
      if (!scope) return;
      const cards = Array.from(scope.querySelectorAll("[data-oui-choice]"));
      for (let k = cards.indexOf(card) + 1; k < cards.length; k++) {
        const b = cards[k].querySelector('[data-oui-opt][tabindex="0"]:not(:disabled)') || cards[k].querySelector("[data-oui-opt]:not(:disabled)");
        if (b) { b.focus({ preventScroll: true }); return; }
      }
      const bar = scope.querySelector("[data-oui-send]:not(:disabled)") || scope.querySelector("[data-oui-clear]:not(:disabled)");
      if (bar) bar.focus({ preventScroll: true });
      return;
    }
    if (!e.metaKey && !e.ctrlKey) e.stopPropagation(); // typing is the text box's: not the composer's type-to-focus, not a global shortcut
  };

  return (
    <div data-oui-choice="" style={{ border: `1px solid ${C.border}`, borderRadius: 10, padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
      <div id={qid} style={{ fontSize: 14.5, fontWeight: 600, overflowWrap: "anywhere" }}>{question}</div>
      <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap", marginTop: -6 }}>
        <span data-oui-pick="" style={{ flex: "none", fontSize: 11, color: C.muted, border: `1px solid ${C.border}`, borderRadius: 5, padding: "1px 6px" }}>{choice.multiple ? "Choose all that apply" : "Choose one"}</span>
        {hint ? <span style={{ fontSize: 12.5, color: C.muted, minWidth: 0, overflowWrap: "anywhere" }}>{hint}</span> : null}
      </div>
      <div role={choice.multiple ? "group" : "radiogroup"} aria-labelledby={qid} onKeyDown={onGroupKey} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {opts.map((o, i) => (
          <Row key={i} i={i} multiple={choice.multiple} on={a.picks.includes(i)} dim={board.sent && !a.picks.includes(i)} disabled={locked} tab={i === tabAt} onPick={() => pick(i)} onFocus={() => setRover(i)}>{o}</Row>
        ))}
        {choice.other ? (
          <Row i={opts.length} other multiple={choice.multiple} on={a.other} dim={board.sent && !(a.other && !empty)} disabled={locked} tab={opts.length === tabAt} onPick={pickOther} onFocus={() => setRover(opts.length)}>Other...</Row>
        ) : null}
      </div>
      {boxShown ? (
        <div style={{ marginTop: -2 }}>
          <textarea
            ref={taRef}
            data-oui-other=""
            rows={1}
            maxLength={500}
            value={a.text}
            readOnly={locked}
            placeholder="Type your own answer"
            aria-label={"Your own answer to: " + question}
            onChange={(e) => board.setText(choice, e.target.value)}
            onKeyDown={onTextKey}
            style={{ font: "inherit", fontSize: 13.5, color: C.fg, background: "transparent", border: `1px solid ${C.border}`, borderRadius: 8, padding: "7px 10px", width: "100%", boxSizing: "border-box", resize: "none", overflowY: "auto", minHeight: 36, display: "block" }}
          />
          {empty && !board.sent ? <div style={{ fontSize: 12, color: C.muted, marginTop: 4 }}>Empty, so this question counts as not answered.</div> : null}
        </div>
      ) : null}
    </div>
  );
}
