// Q&A components: collapsible FAQ and a clickable multiple-choice question.
import React, { useState } from "react";
import { useTriggerAction } from "@openuidev/react-lang";
import { C } from "../theme.js";
import { renderMarkdown } from "./markdown.jsx";

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

export function ChoiceView({ question, options, hint }) {
  const trigger = useTriggerAction();
  const [picked, setPicked] = useState(-1);
  return (
    <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ fontSize: 14.5, fontWeight: 600 }}>{question}</div>
      {hint ? <div style={{ fontSize: 12.5, color: C.muted, marginTop: -6 }}>{hint}</div> : null}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {options.map((o, i) => (
          <button
            key={i}
            disabled={picked >= 0}
            onClick={() => { setPicked(i); trigger(`${question} — ${o}`); }}
            style={{
              font: "inherit", fontSize: 13.5, textAlign: "left", color: C.fg, cursor: picked >= 0 ? "default" : "pointer",
              background: picked === i ? `color-mix(in srgb, ${C.accent} 16%, transparent)` : "transparent",
              border: `1px solid ${picked === i ? C.accent : C.border}`, borderRadius: 8, padding: "8px 12px",
              opacity: picked >= 0 && picked !== i ? 0.5 : 1,
            }}
          >
            {o}
          </button>
        ))}
      </div>
      {picked >= 0 ? <div style={{ fontSize: 12, color: C.muted }}>Sent to the agent.</div> : null}
    </div>
  );
}
