// Code block with a small generic highlighter (comments, strings, numbers, keywords, JSON keys).
import React, { useState } from "react";
import { C, MONO } from "../theme.js";

const KW = {
  python: "def class return if elif else for while in not and or is import from as with try except finally raise yield lambda None True False async await pass break continue global nonlocal",
  js: "const let var function return if else for while of in new class extends import from export default async await try catch finally throw null undefined true false typeof this switch case break continue interface type enum implements",
  bash: "if then else elif fi for while do done in case esac function export local echo cd set unset source exit return",
  sql: "select from where join left right inner outer on group by order having limit insert into values update set delete create table index primary key foreign references not null default and or as distinct union with",
  yaml: "true false null yes no",
  go: "func package import return if else for range var const type struct interface map chan go defer select switch case default nil true false",
  rust: "fn let mut pub struct enum impl trait use mod match if else for while loop return self Self true false Some None Ok Err",
};
const ALIAS = { py: "python", python3: "python", javascript: "js", jsx: "js", ts: "js", tsx: "js", typescript: "js", node: "js", sh: "bash", shell: "bash", zsh: "bash", yml: "yaml", golang: "go", rs: "rust", postgres: "sql", postgresql: "sql", pgsql: "sql" };
const HASH = new Set(["python", "bash", "yaml"]);
const SLASH = new Set(["js", "go", "rust"]);

function tokenize(code, lang) {
  const words = new Set((KW[lang] || "").split(" "));
  const ci = lang === "sql";
  const lineC = HASH.has(lang) ? "#.*" : SLASH.has(lang) ? "\\/\\/.*" : lang === "sql" ? "--.*" : null;
  const parts = [];
  if (lineC) parts.push(`(?<c>${lineC})`);
  if (SLASH.has(lang) || lang === "sql") parts.push("(?<c2>\\/\\*[\\s\\S]*?\\*\\/)");
  parts.push("(?<s>\"(?:[^\"\\\\\\n]|\\\\.)*\"|'(?:[^'\\\\\\n]|\\\\.)*'|`(?:[^`\\\\]|\\\\.)*`)");
  parts.push("(?<n>\\b\\d[\\d_.]*(?:e[+-]?\\d+)?\\b)");
  parts.push("(?<w>[A-Za-z_$][\\w$]*)");
  const re = new RegExp(parts.join("|"), "gi");
  const out = [];
  let last = 0, m;
  while ((m = re.exec(code))) {
    if (m.index > last) out.push([code.slice(last, m.index), null]);
    const g = m.groups;
    let kind = null;
    if (g.c || g.c2) kind = "c";
    else if (g.s) kind = lang === "json" && /^\s*:/.test(code.slice(re.lastIndex)) ? "k" : "s";
    else if (g.n) kind = "n";
    else if (g.w && words.has(ci ? m[0].toLowerCase() : m[0])) kind = "w";
    else if (g.w && lang === "yaml" && /^\s*:/.test(code.slice(re.lastIndex))) kind = "k";
    else if (g.w && /^\s*\(/.test(code.slice(re.lastIndex)) && lang !== "json") kind = "f";
    out.push([m[0], kind]);
    last = m.index + m[0].length;
  }
  if (last < code.length) out.push([code.slice(last), null]);
  return out;
}
const COLORS = { c: C.muted, s: "#7ee787", n: "#79c0ff", w: "#ff7b72", k: "#79c0ff", f: "#d2a8ff" };

// Copy through a hidden textarea: the sandboxed preview frame has no clipboard API permission. Returns whether it worked.
export function copyText(text) {
  let ok = false;
  const before = document.activeElement; // the textarea takes focus; give it back, or a key press after a copy goes nowhere
  try {
    const ta = document.createElement("textarea");
    ta.value = String(text);
    ta.style.cssText = "position:fixed;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    ok = document.execCommand("copy");
    ta.remove();
  } catch (e) {}
  try {
    if (before && before !== document.body && typeof before.focus === "function") before.focus({ preventScroll: true });
  } catch (e) {}
  return ok;
}

export function CodeView({ code, language = "", title }) {
  const raw = String(language || "").toLowerCase();
  const lang = ALIAS[raw] || raw;
  const [copied, setCopied] = useState("");
  const toks = tokenize(String(code), lang);
  const copy = () => {
    setCopied(copyText(code) ? "Copied" : "Copy blocked");
    setTimeout(() => setCopied(""), 1500);
  };
  return (
    <div style={{ border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden", background: C.soft, minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 10px", borderBottom: `1px solid ${C.border}`, fontSize: 11.5, color: C.muted }}>
        <span>{title || raw || "code"}</span>
        <button onClick={copy} style={{ font: "inherit", fontSize: 11.5, color: C.muted, background: "transparent", border: 0, cursor: "pointer", padding: 0 }}>{copied || "Copy"}</button>
      </div>
      <pre style={{ margin: 0, padding: "10px 12px", overflowX: "auto", fontFamily: MONO, fontSize: 12.5, lineHeight: 1.55, color: C.fg, tabSize: 2 }}>
        <code>{toks.map(([t, k], i) => (k ? <span key={i} style={{ color: COLORS[k] }}>{t}</span> : t))}</code>
      </pre>
    </div>
  );
}
