// Pure helpers for the Choice batch card (answers are staged on a board shared by every Choice of a widget and sent with ONE button). No React, no
// DOM, and one import (the text rules of notes-core.js, which has none): Node tests load this file directly, like notes-core.js. The board itself (context,
// bar, persistence) is components/choice-board.jsx and the question view is components/qa.jsx.
// The message built here is the contract with the agent. The ONE-question, single-mode, no-Other-text case keeps the wire format agents already
// expect (`<question> \u2014 <option>`, a spaced em dash); everything else is a numbered list written in ASCII punctuation. The words of the widget
// (question, options) come from the agent and the message is SENT without a review step, so they are cleaned like Notes cleans a quote (control and
// invisible characters gone, whitespace collapsed, clipped, `@file:`-style references broken with "(at)"). The user's own Other text is only cleaned
// of control and invisible characters: their "@" stays.
import { strip, collapse, clip, neutralize, hashText } from "./notes-core.js"; // the one copy of the sanitizer: Notes' (notes-core.js pins "no imports", so it is the source, not a consumer)

export const CHOICE_LIMITS = { question: 200, option: 120, other: 500, stem: 40, preview: 500, native: 4000 };
export const NO_ANSWER = "(no answer)";
export const STORAGE_PREFIX = "hermes-openui:answers:";

const word = (raw, max) => clip(neutralize(collapse(raw)), max);

// The user's own text: newlines stay (trailing blanks go), control and invisible characters go, at most 500 characters. NOT neutralised.
export function cleanOther(raw) {
  const text = strip(raw, true).split("\n").map((l) => l.replace(/[ \t]+$/g, "")).join("\n").trim();
  return Array.from(text).slice(0, CHOICE_LIMITS.other).join("");
}
// What the text box holds while the user types: the raw text, cut at 500 characters (cleaned when the message is built).
export const limitOther = (raw) => Array.from(raw == null ? "" : String(raw)).slice(0, CHOICE_LIMITS.other).join("");

/* ------------------------------ questions ------------------------------ */
// A question as the board knows it: { question, options (cleaned words, the ones the message uses), multiple, other, key }. The key is a fingerprint
// of the words and the two flags: two Choices with the same key are ONE question (they share their answer and count once).
export function makeChoice(p) {
  const props = p || {};
  const options = (Array.isArray(props.options) ? props.options : []).map((o) => word(o, CHOICE_LIMITS.option));
  const question = word(props.question, CHOICE_LIMITS.question);
  const multiple = props.multiple === true;
  const other = props.other !== false;
  return { question, options, multiple, other, key: hashText(JSON.stringify([question, options, multiple, other])) };
}
export function uniqueChoices(list) {
  const seen = new Set();
  return list.filter((c) => (seen.has(c.key) ? false : (seen.add(c.key), true)));
}
// Every Choice of a parsed widget, in document order, whether or not its tab was ever shown (the parse result holds the whole tree).
export function collectChoices(root) {
  const out = [], seen = new Set();
  const walk = (x, depth) => {
    if (!x || typeof x !== "object" || seen.has(x) || depth > 300) return;
    seen.add(x);
    if (Array.isArray(x)) { x.forEach((v) => walk(v, depth + 1)); return; }
    if (x.type === "element" && x.typeName === "Choice" && x.props && typeof x.props.question === "string") { out.push(makeChoice(x.props)); return; }
    Object.keys(x).forEach((k) => walk(x[k], depth + 1));
  };
  walk(root, 0);
  return uniqueChoices(out);
}

/* ------------------------------ the answers ------------------------------ */
// answers: { [question key]: { picks: number[] (option indexes, ascending), other: boolean (the Other row is selected), text: string } }. Immutable.
const BLANK = { picks: [], other: false, text: "" };
const cur = (answers, c) => (answers && answers[c.key]) || BLANK;
export function toggleOption(answers, c, i) {
  if (!Number.isInteger(i) || i < 0 || i >= c.options.length) return answers;
  const a = cur(answers, c);
  let next;
  if (c.multiple) {
    const picks = a.picks.includes(i) ? a.picks.filter((x) => x !== i) : a.picks.concat([i]).sort((x, y) => x - y);
    next = { ...a, picks };
  } else {
    next = a.picks.length === 1 && a.picks[0] === i ? { ...a, picks: [] } : { ...a, picks: [i], other: false }; // a second click unselects; another option moves the pick
  }
  return { ...answers, [c.key]: next };
}
export function toggleOther(answers, c) {
  if (!c.other) return answers;
  const a = cur(answers, c);
  const next = c.multiple ? { ...a, other: !a.other } : a.other ? { ...a, other: false } : { ...a, other: true, picks: [] }; // single mode: Other replaces the option
  return { ...answers, [c.key]: next };
}
export function setOtherText(answers, c, text) {
  if (!c.other) return answers;
  return { ...answers, [c.key]: { ...cur(answers, c), text: limitOther(text) } };
}
const otherOf = (c, a) => (c.other && a.other ? cleanOther(a.text) : "");
// An Other row that is selected but empty is NOT an answer.
export function isAnswered(c, answers) {
  const a = cur(answers, c);
  return a.picks.some((i) => i >= 0 && i < c.options.length) || otherOf(c, a) !== "";
}
export function progress(choices, answers) {
  return { answered: choices.filter((c) => isAnswered(c, answers)).length, total: choices.length };
}
// "disk; memory; other: also look at the logs" ("" when not answered). A multi-line Other text keeps its lines, indented under the question.
export function answerWords(c, answers) {
  const a = cur(answers, c);
  const parts = a.picks.filter((i) => i >= 0 && i < c.options.length).map((i) => c.options[i]);
  const text = otherOf(c, a);
  if (text) parts.push("other: " + text.split("\n").join("\n   "));
  return parts.join("; ");
}

/* ------------------------------ the message ------------------------------ */
// The app runs a text as a SLASH COMMAND when it matches this (apps/shared/src/slash.ts SLASH_COMMAND_RE, used by isSlashCommandText), also for a message that a
// plugin submits. The one-question line starts with the agent's own question, so a question like "/new session?" would run a command when the user presses Send.
const SLASH_COMMAND = /^\/[^\s/]*(?:\s|$)/;
export const runsAsCommand = (text) => SLASH_COMMAND.test(String(text).trim());
// Returns { text, compat }. compat: the one-question wire format. questionMax (optional): clip each question to that many characters (the numbers stay, they keep
// the mapping); the compat line is never clipped. The caller checks the size (checkSize / fitMessage) and sends.
export function buildMessage(choices, answers, stem, questionMax) {
  const list = choices || [];
  if (list.length === 1 && !list[0].multiple) {
    const c = list[0], a = cur(answers, c);
    if (a.picks.length === 1 && c.options[a.picks[0]] !== undefined && !otherOf(c, a)) {
      const line = c.question + " \u2014 " + c.options[a.picks[0]];
      if (!runsAsCommand(line)) return { text: line, compat: true }; // else the batch format below, which starts with "Answers to"
    }
  }
  const name = stem ? word(String(stem).replace(/`/g, "'"), CHOICE_LIMITS.stem) : "";
  const head = name ? "Answers to the questions in widget `" + name + "` (" + list.length + "):" : "Answers to the questions in this widget (" + list.length + "):";
  const lines = list.map((c, i) => (i + 1) + ". " + (questionMax ? clip(c.question, questionMax) : c.question) + "\n   " + (answerWords(c, answers) || NO_ANSWER));
  return { text: head + "\n\n" + lines.join("\n"), compat: false };
}
// mode "preview" (the app caps a widget's message at 500) or "native" (the plugin's own cap for a message from the board).
export function checkSize(text, mode) {
  const limit = mode === "native" ? CHOICE_LIMITS.native : CHOICE_LIMITS.preview;
  const length = String(text).length;
  if (length <= limit) return { ok: true, length, limit };
  return { ok: false, length, limit, error: "This answer is " + length.toLocaleString("en-US") + " characters and this display mode sends at most " + limit.toLocaleString("en-US") + ". Shorten the answers." };
}
// The message to send, or the reason it cannot be. In preview the user cannot shorten the agent's questions, so when the full message is over the 500 the app
// allows it is built again with each question clipped (50 characters, then 30, then 20, with "..."), and only when even that is over is it refused (with the
// length of the shortest try: that is the one nothing can improve). Native has its own, larger cap and never clips.
export const PREVIEW_CLIPS = [50, 30, 20];
export function fitMessage(choices, answers, stem, mode) {
  const full = buildMessage(choices, answers, stem);
  const size = checkSize(full.text, mode);
  if (size.ok || mode === "native") return { ...size, text: full.text, compat: full.compat, clipped: false };
  let last = { ...size, text: full.text, compat: full.compat, clipped: false };
  for (const n of PREVIEW_CLIPS) {
    const m = buildMessage(choices, answers, stem, n);
    const sz = checkSize(m.text, mode);
    last = { ...sz, text: m.text, compat: m.compat, clipped: true };
    if (sz.ok) return last;
  }
  return last;
}

/* ------------------------------ keeping the board ------------------------------ */
// Reads whatever the storage held (an object or its JSON text) back into a board that fits THESE questions: answers for a question that is gone
// are dropped, picks outside the option range too. "sent" is kept only when the saved board was for EXACTLY this set of questions (board.keys, the sorted
// question keys it was made for): a widget redrawn under the same name with a new question must not arrive locked, with its new question "sent".
export const keysOf = (choices) => choices.map((c) => c.key).sort();
const sameSet = (a, b) => Array.isArray(a) && a.length === b.length && a.every((k, i) => k === b[i]);
export function reviveBoard(raw, choices) {
  const keys = keysOf(choices);
  let d = raw;
  if (typeof raw === "string") {
    try { d = JSON.parse(raw); } catch (e) { return { answers: {}, sent: false, keys }; }
  }
  if (!d || typeof d !== "object") return { answers: {}, sent: false, keys };
  const src = d.answers && typeof d.answers === "object" ? d.answers : {};
  const answers = {};
  for (const c of choices) {
    const x = src[c.key];
    if (!x || typeof x !== "object") continue;
    let picks = Array.isArray(x.picks) ? Array.from(new Set(x.picks.filter((i) => Number.isInteger(i) && i >= 0 && i < c.options.length))).sort((p, q) => p - q) : [];
    if (!c.multiple) picks = picks.slice(0, 1);
    const other = c.other && x.other === true && !(!c.multiple && picks.length);
    answers[c.key] = { picks, other, text: typeof x.text === "string" ? limitOther(strip(x.text, true)) : "" };
  }
  return { answers, sent: d.sent === true && sameSet(d.keys, keys) && choices.some((c) => isAnswered(c, answers)), keys };
}
// One board per widget file stem, in memory for the life of the page and mirrored in sessionStorage (gone when the app quits). Every storage call is guarded.
export function createBoardStore(getStorage) {
  const mem = new Map();
  const storage = () => { try { return getStorage(); } catch (e) { return null; } };
  return {
    get(stem) {
      if (mem.has(stem)) return mem.get(stem);
      let raw = null;
      try { const s = storage(); raw = s ? s.getItem(STORAGE_PREFIX + stem) : null; } catch (e) {}
      if (typeof raw === "string") {
        try { raw = JSON.parse(raw); } catch (e) { raw = null; }
      }
      return raw && typeof raw === "object" ? raw : null;
    },
    set(stem, board) {
      mem.set(stem, board);
      try {
        const s = storage();
        if (!s) return;
        if (board && (board.sent || Object.keys(board.answers || {}).length)) s.setItem(STORAGE_PREFIX + stem, JSON.stringify(board));
        else s.removeItem(STORAGE_PREFIX + stem);
      } catch (e) {}
    },
    forget(stem) { mem.delete(stem); }, // the memory only (a test remounts from storage)
  };
}
