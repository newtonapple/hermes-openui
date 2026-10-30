// Pure helpers for Notes (the user leaves notes on a widget and drafts them into the chat). No imports, no React, no DOM: Node tests
// load this file directly, like tooltips-core.js. The controller that uses it lives in the desktop bundle only (plugin/notes.jsx).
// Native mode only. The message built here is the contract with the agent: ASCII punctuation in what this file writes, the
// words of the widget (quotes, labels) cleaned of control and invisible characters because the user is about to send them as their own message.

export const NOTE_LIMITS = { note: 1000, notes: 20, quote: 200, label: 40, message: 6000, cell: 60 };
// Components that are never noted, and the ones that are only containers (hover passes through them to the item under them).
export const NOT_NOTED = ["Button", "Choice", "Stack", "Card", "Tabs", "TabItem", "Tooltip"];
// Types whose whole component reads "chart" in the message.
const CHARTS = ["LineChart", "AreaChart", "PieChart", "RadarChart", "BarChart"];

// Control characters (C0, DEL, C1), line and paragraph separators and the Unicode format characters (zero-width, bidi marks and
// overrides, the soft hyphen): none of them may reach a message the user sends. keepNewline leaves \n alone (the user's own note).
export function strip(value, keepNewline) {
  const s = value == null ? "" : String(value);
  return s.replace(/\r\n?/g, "\n").replace(/[\p{Cc}\p{Cf}\u2028\u2029]/gu, (ch) => (keepNewline && ch === "\n" ? ch : ""));
}
// Whitespace (any run, tabs and newlines too) becomes one space; the ends are trimmed. Invisible characters are removed first.
export function collapse(value) {
  const s = value == null ? "" : String(value);
  return s.replace(/\p{Cf}/gu, "").replace(/[^\P{Cc}\t\n\r]/gu, "").replace(/\s+/g, " ").trim();
}
// At most max characters in all; a cut text ends in "...".
export function clip(s, max) {
  const chars = Array.from(s);
  return chars.length <= max ? s : chars.slice(0, Math.max(0, max - 3)).join("").trimEnd() + "...";
}
// The kinds of reference the app turns into an attached reference chip when a draft holds "@kind:value" (reference-kinds.ts, WIRE_REFERENCE_KINDS).
// Words of the widget are written by an agent: "@file:/x" in a quote or in an id would attach a file the user never chose. The "@" is
// replaced by "(at)" (ASCII, still readable). The user's OWN note text is not touched.
const REF_KINDS = "file|folder|url|image|tool|line|terminal|session";
const REF_START = new RegExp("@(?=(?:" + REF_KINDS + "):)", "gi");
export const neutralize = (s) => String(s).replace(REF_START, "(at)");
// A word of the widget that goes inside backticks or double quotes of the message: one line, no backtick or double quote of its own,
// and no reference token (see above).
const quiet = (s) => neutralize(s.replace(/`/g, "'").replace(/"/g, "'"));
export function cleanQuote(raw) {
  return clip(quiet(collapse(raw)), NOTE_LIMITS.quote);
}
export function cleanLabel(raw) {
  return clip(quiet(collapse(raw)), NOTE_LIMITS.label);
}
// Any widget text with a limit of its own (the text of a table cell): sanitized like a quote.
export function cleanText(raw, max) {
  return clip(quiet(collapse(raw)), max);
}
// The user's own text: newlines stay (trailing blanks go), the rest as strip() says. Not cut here: the editor refuses over-long text and says so.
export function cleanNote(raw) {
  return strip(raw, true).split("\n").map((l) => l.replace(/[ \t]+$/g, "")).join("\n").trim();
}

export const isNoteable = (type) => !NOT_NOTED.includes(type);
export const isContainer = (type) => type === "Stack" || type === "Card" || type === "Tabs" || type === "TabItem";

/* ------------------------------ items ------------------------------ */
// An item is { type (the component), key (the Tooltip vocabulary: "row:3", "web>api", ...) or "" for the whole component, what (participant|message|... only
// where the key does not say it), label (the drawn name) }. The keys are the ones tooltips-core.js targetEntries() lists; they are read from the page.
export function itemKind(type, key, what) {
  const k = String(key || "");
  if (!k) return "";
  if (type === "Table") return /^row:/.test(k) ? "row" : /^col:/.test(k) ? "column" : /^cell:/.test(k) ? "cell" : "item";
  if (type === "Dag") return "node";
  if (type === "Erd") return k.indexOf(".") > 0 ? "column" : "entity";
  if (type === "InfraMap") return /^zone:/.test(k) ? "zone" : k.indexOf(">") > 0 ? "link" : "node";
  if (type === "SequenceDiagram") return what === "message" ? "message" : "participant";
  if (type === "Metric") return "tile";
  if (type === "BarChart") return "bar";
  if (type === "GeoMap") return k.indexOf(">") > 0 ? "link" : "pin";
  if (type === "Image") return "image";
  return what || "item";
}
const tick = (s) => "`" + cleanLabel(s) + "`";
// "row 3, column `status`" for the message (the key is shown in backticks because it is a name the agent can match against its source).
// quoted: the note is about selected words, so a note with no item says nothing about "the whole component".
export function describeWhere(type, key, what, quoted, cell) {
  const k = String(key || "");
  const kind = itemKind(type, k, what);
  if (!k) return quoted ? "" : CHARTS.includes(type) ? "whole chart" : "whole component";
  if (kind === "row") return "row " + cleanLabel(k.slice(4));
  if (kind === "column" && type === "Table") return "column " + tick(k.slice(4));
  if (kind === "cell") {
    const i = k.indexOf(".");
    // an item note on a cell (no selected words) says what the cell holds, so the row number is not the only handle on it
    const held = !quoted && cell ? ", cell \"" + cleanText(cell, NOTE_LIMITS.cell) + "\"" : "";
    return "row " + cleanLabel(k.slice(5, i)) + ", column " + tick(k.slice(i + 1)) + held;
  }
  if (kind === "column") {
    const i = k.indexOf(".");
    return "entity " + tick(k.slice(0, i)) + ", column " + tick(k.slice(i + 1));
  }
  if (kind === "zone") return "zone " + tick(k.slice(5));
  if (kind === "link") {
    const i = k.indexOf(">");
    return "link " + tick(k.slice(0, i)) + " > " + tick(k.slice(i + 1));
  }
  if (kind === "image") return "the image";
  return kind + " " + tick(k);
}
// Plain words for the user (the hover label, the editor header, the tray): the component type and the place, no source variable name:
// "Table, row 2, status", "Metric, Error rate", "Dag, node build", "Text". pos is "2/3" when the widget holds three components of this type and
// this is the second ("Text, 2nd of 3"); it is empty when the type occurs once. The id belongs in the drafted message only.
const ordinal = (n) => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10 < 4 ? n % 10 : 0]);
export function plainOrd(pos) {
  const m = /^(\d+)\/(\d+)$/.exec(String(pos || ""));
  return m && Number(m[2]) > 1 ? ordinal(Number(m[1])) + " of " + m[2] : "";
}
export function plainWhere(note) {
  const type = cleanLabel(note.ctype || "");
  const k = String(note.key || "");
  const kind = itemKind(note.ctype, k, note.what);
  let at = "";
  if (kind === "row") at = "row " + cleanLabel(k.slice(4));
  else if (kind === "column" && note.ctype === "Table") at = "column " + cleanLabel(k.slice(4));
  else if (kind === "cell") { const i = k.indexOf("."); at = "row " + cleanLabel(k.slice(5, i)) + ", " + cleanLabel(k.slice(i + 1)); }
  else if (kind === "column") { const i = k.indexOf("."); at = cleanLabel(k.slice(0, i)) + ", column " + cleanLabel(k.slice(i + 1)); }
  else if (kind === "zone") at = "zone " + cleanLabel(k.slice(5));
  else if (kind === "link") { const i = k.indexOf(">"); at = "link " + cleanLabel(k.slice(0, i)) + " > " + cleanLabel(k.slice(i + 1)); }
  else if (kind === "image") at = "";
  else if (kind === "tile") at = cleanLabel(k);
  else if (kind) at = kind + " " + cleanLabel(k);
  const ord = plainOrd(note.pos);
  return [type, ord, at].filter(Boolean).join(", ") + (note.lines ? ", lines " + cleanLabel(note.lines) : "");
}
// The hover label (before a note exists) and the tray say the same words.
export const hoverName = (type, key, what, label, pos) => plainWhere({ ctype: type, key, what, label, pos });
export const trayWhere = plainWhere;

/* ------------------------------ the message ------------------------------ */
// note: { cid, ctype, unnamed, key, what, quote, lines, tab, text, edited }. num is the number the message prints (the position when nothing is given).
export function noteLine(n, i, num) {
  const head = "`" + cleanLabel(n.cid) + "` (" + cleanLabel(n.ctype) + (n.unnamed ? ", unnamed" : "") + ")" + (n.tab ? " [tab \"" + cleanLabel(n.tab) + "\"]" : "");
  const parts = [describeWhere(n.ctype, n.key, n.what, !!n.quote, n.cell)].filter(Boolean);
  if (n.lines) parts.push("lines " + cleanLabel(n.lines));
  if (n.quote) parts.push("\"" + cleanQuote(n.quote) + "\"");
  const body = cleanNote(n.text).split("\n").map((l) => "   " + l).join("\n");
  return (num > 0 ? num : i + 1) + ". " + (n.edited ? "(edited) " : "") + head + " > " + parts.join(", ") + "\n" + body;
}
// The clauses that explain the ids and the row numbers are printed only when a note in THIS message needs them.
function clausesFor(list) {
  const clauses = ["Ids are the variable names in the widget source"];
  if (list.some((n) => n.unnamed)) clauses.push("`Type#n` is the n-th component of that type in reading order (no name in the source)");
  if (list.some((n) => /^(row|cell):/.test(String(n.key || "")) && n.ctype === "Table")) clauses.push("table rows count from 1, not counting the header row");
  return clauses.join("; ") + ".";
}
// A message is refused, never cut, when it is over the limit.
function finish(head, list, numbers) {
  const text = head + "\n\n" + list.map((n, i) => noteLine(n, i, numbers && numbers[i])).join("\n");
  if (text.length > NOTE_LIMITS.message) {
    return { ok: false, error: "The message would be " + text.length.toLocaleString("en-US") + " characters; the limit is " + NOTE_LIMITS.message.toLocaleString("en-US") + ". Shorten or remove a few notes." };
  }
  return { ok: true, text };
}
const checkList = (list) => {
  if (!list.length) return { ok: false, error: "There are no notes to add." };
  if (list.length > NOTE_LIMITS.notes) return { ok: false, error: "At most " + NOTE_LIMITS.notes + " notes per widget. Remove " + (list.length - NOTE_LIMITS.notes) + "." };
  return null;
};
// Returns { ok: true, text } or { ok: false, error } (a limit was hit: say so, never cut). numbers: the number of each note (the position when absent).
export function buildMessage(stem, notes, numbers) {
  const list = Array.isArray(notes) ? notes : [];
  const bad = checkList(list);
  if (bad) return bad;
  const head = "Notes on widget `" + cleanLabel(stem) + "` (" + list.length + "). Please answer each note by its number. " + clausesFor(list);
  return finish(head, list, numbers);
}
// The message of a second draft: only the notes that are not in the message box yet (new ones, and edited ones, which keep their number and say so).
export function buildFollowUp(stem, notes, numbers) {
  const list = Array.isArray(notes) ? notes : [];
  const bad = checkList(list);
  if (bad) return bad;
  const edited = list.filter((n) => n.edited).length, fresh = list.length - edited;
  const counts = [fresh ? fresh + " new" : "", edited ? edited + " edited" : ""].filter(Boolean).join(", ");
  const cont = "These continue the numbering of the earlier message" + (edited ? "; an edited note replaces the earlier note with the same number" : "") + ".";
  const head = "More notes on widget `" + cleanLabel(stem) + "` (" + counts + "). " + cont + " Please answer each note by its number. " + clausesFor(list);
  return finish(head, list, numbers);
}

/* ------------------------------ numbers and what was drafted ------------------------------ */
// Each note can carry drafted (its text is in the message box: set only when insertText said true) and edited (it was drafted, then its text changed).
// A list's numbering is { frozen, top }. While nothing has left the widget (frozen is false) the number is the position and a removal renumbers.
// The first successful draft freezes the numbers: each note keeps the number it had (num), a removed note leaves a gap, and a new note takes top + 1,
// top being the highest number ever used in this list (a removed highest number is not used again). Clearing the list starts over.
export const NO_META = { frozen: false, top: 0 };
export function reviveMeta(raw) {
  let d = raw;
  if (typeof raw === "string") {
    try { d = JSON.parse(raw); } catch (e) { return { ...NO_META }; }
  }
  if (!d || typeof d !== "object") return { ...NO_META };
  const top = Number.isInteger(d.top) && d.top >= 0 && d.top < 100000 ? d.top : 0;
  return { frozen: d.frozen === true, top };
}
export const isFrozen = (notes, meta) => !!((meta && meta.frozen) || (Array.isArray(notes) && notes.some((n) => n && n.drafted)));
// The number of every note of the current list.
export function numbersFor(notes, meta) {
  const list = Array.isArray(notes) ? notes : [];
  return isFrozen(list, meta) ? list.map((n, i) => (n.num > 0 ? n.num : i + 1)) : list.map((_, i) => i + 1);
}
const highest = (notes, meta) => Math.max((meta && meta.top) || 0, notes.length, ...notes.map((n) => n.num || 0));
// Frozen lists only: a note without a number (a set-aside note that was kept) takes the next one; the list is in number order.
export function settleNumbers(notes, meta) {
  const m = { ...NO_META, ...(meta || {}) };
  if (!m.frozen) return { notes, meta: m };
  let top = Math.max(m.top || 0, ...notes.map((n) => n.num || 0));
  const out = notes.map((n) => (n.num > 0 ? n : { ...n, num: ++top }));
  out.sort((a, b) => a.num - b.num);
  return { notes: out, meta: { frozen: true, top } };
}
// The first draft that went through: the listed notes are in the message box now. The first one also freezes the numbers.
export function markDrafted(notes, indexes, meta) {
  const m = { ...NO_META, ...(meta || {}) };
  const list = Array.isArray(notes) ? notes : [];
  const was = isFrozen(list, m);
  const pick = new Set(indexes);
  const out = list.map((n, i) => {
    const x = pick.has(i) ? { ...n, drafted: true, edited: false } : { ...n, drafted: !!n.drafted, edited: !!n.edited };
    return was ? x : { ...x, num: i + 1 };
  });
  return { notes: out, meta: { frozen: true, top: was ? highest(list, m) : list.length } };
}
// What the primary button would draft, or "none" when every note is in the message box. all: the "Add all again" button.
//   first  nothing has been drafted: every note, the original header      more  a later draft: the notes not in the box yet, the follow-up header
//   all    every note again, the original header, the numbers unchanged   none  nothing new
export function planDraft(stem, notes, meta, all) {
  const list = Array.isArray(notes) ? notes : [];
  const nums = numbersFor(list, meta);
  const every = list.map((_, i) => i);
  let kind = "first", idx = every;
  if (all) kind = "all";
  else if (isFrozen(list, meta)) {
    idx = every.filter((i) => !list[i].drafted);
    kind = idx.length ? "more" : "none";
  }
  if (kind === "none") return { kind, indexes: [], fresh: 0, edited: 0, message: null };
  const pick = idx.map((i) => list[i]), nn = idx.map((i) => nums[i]);
  const message = kind === "more" ? buildFollowUp(stem, pick, nn) : buildMessage(stem, pick, nn);
  const edited = kind === "more" ? pick.filter((n) => n.edited).length : 0;
  return { kind, indexes: idx, fresh: pick.length - edited, edited, message };
}
const noteWord = (n) => (n === 1 ? "1 note" : n + " notes");
// "1 new note", "2 edited notes", "3 new or edited notes": the words of the button and of the sentence after a draft.
export function countWords(fresh, edited) {
  if (fresh && edited) return fresh + edited + " new or edited notes";
  return edited ? edited + " edited " + (edited === 1 ? "note" : "notes") : fresh + " new " + (fresh === 1 ? "note" : "notes");
}
export function buttonLabel(plan, count) {
  return "Add " + (plan.kind === "more" ? countWords(plan.fresh, plan.edited) : noteWord(count)) + " to your message";
}
export function addedSentence(plan, count) {
  const what = plan.kind === "more" ? countWords(plan.fresh, plan.edited) : plan.kind === "all" ? (count === 1 ? "the note again" : "all " + count + " notes again") : noteWord(count);
  return "Added " + what + " to your message box. Edit it if you like, then send.";
}

/* ------------------------------ ids ------------------------------ */
// The widget's file stem from the file the directive names (".../widgets/<stem>.oui").
export function stemOf(file) {
  const m = /([^/\\]+?)(?:\.oui)?$/.exec(String(file || ""));
  return m ? m[1] : "widget";
}
// Components without a source variable name (an inline component) are called Type#n, n being their place among their type in document order.
export function fallbackId(type, n) {
  return type + "#" + n;
}

// A short fingerprint of the widget's source text (FNV-1a, 32 bits, base 36): a note keeps the one of the source it was written for.
export function hashText(value) {
  const t = value == null ? "" : String(value);
  let h = 0x811c9dc5;
  for (let i = 0; i < t.length; i++) {
    h ^= t.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(36);
}
// A note written for another version of the source (src is empty for a note stored before versions were kept: it counts as current).
export const isStale = (note, currentHash) => !!(currentHash && note && note.src && note.src !== currentHash);

/* ------------------------------ the list ------------------------------ */
// Adds a note (a new object); the 21st is refused. Returns { ok, notes, meta?, error? }. meta (optional): the list's numbering; in a frozen list the new note takes the next number.
export function addNote(notes, note, meta) {
  if (notes.length >= NOTE_LIMITS.notes) return { ok: false, notes, meta, error: "At most " + NOTE_LIMITS.notes + " notes per widget. Remove one first." };
  const text = cleanNote(note.text);
  if (!text) return { ok: false, notes, meta, error: "Write something first." };
  if (text.length > NOTE_LIMITS.note) return { ok: false, notes, meta, error: "A note is at most " + NOTE_LIMITS.note.toLocaleString("en-US") + " characters." };
  const m = { ...NO_META, ...(meta || {}) };
  const frozen = isFrozen(notes, m);
  const num = frozen ? highest(notes, m) + 1 : 0;
  const added = { ...note, text, drafted: false, edited: false };
  if (frozen) added.num = num;
  return { ok: true, notes: notes.concat([added]), meta: frozen ? { frozen: true, top: num } : meta };
}
// A drafted note whose text changed is "edited": it will be included again, with its number. The same text keeps it as it was.
export function updateNote(notes, index, text) {
  const t = cleanNote(text);
  if (!notes[index]) return { ok: false, notes, error: "No such note." };
  if (!t) return { ok: false, notes, error: "Write something first." };
  if (t.length > NOTE_LIMITS.note) return { ok: false, notes, error: "A note is at most " + NOTE_LIMITS.note.toLocaleString("en-US") + " characters." };
  const changed = t !== notes[index].text;
  return { ok: true, notes: notes.map((n, i) => (i !== index ? n : changed && n.drafted ? { ...n, text: t, drafted: false, edited: true } : { ...n, text: t })) };
}
// Before the first draft numbers are positions: after a removal the later notes move up. After it they stay (see numbersFor).
export function removeNote(notes, index) {
  return notes.filter((_, i) => i !== index);
}

/* ------------------------------ the store ------------------------------ */
// One list of notes per widget file stem, in memory for the life of the page and mirrored in sessionStorage (gone when the app quits). Every storage call is guarded.
const KEEP = ["cid", "ctype", "key", "what", "label", "quote", "anchor", "lines", "tab", "text", "cell", "pos", "src"];
export function reviveNotes(raw) {
  let data = raw;
  if (typeof raw === "string") {
    try { data = JSON.parse(raw); } catch (e) { return []; }
  }
  if (!Array.isArray(data)) return [];
  const out = [], seen = new Set();
  for (const x of data) {
    if (!x || typeof x !== "object" || out.length >= NOTE_LIMITS.notes) continue;
    if (typeof x.cid !== "string" || typeof x.ctype !== "string" || typeof x.text !== "string") continue;
    const n = { unnamed: x.unnamed === true };
    for (const f of KEEP) n[f] = typeof x[f] === "string" ? x[f] : "";
    n.nth = Number.isInteger(x.nth) && x.nth >= 0 && x.nth < 1000 ? x.nth : 0;
    // what was drafted, and the frozen number: anything else (an old list has none of them) means "not drafted", positional
    n.drafted = x.drafted === true;
    n.edited = x.edited === true && !n.drafted;
    n.num = Number.isInteger(x.num) && x.num > 0 && x.num < 100000 && !seen.has(x.num) ? x.num : 0;
    if (n.num) seen.add(x.num);
    n.text = cleanNote(n.text).slice(0, NOTE_LIMITS.note);
    if (n.text) out.push(n);
  }
  return out;
}
export const STORAGE_PREFIX = "hermes-openui:notes:";
export const META_PREFIX = "hermes-openui:notes-meta:"; // the numbering of a list (frozen, top): it outlives the notes, so a number is not used twice
export function createStore(getStorage) {
  const mem = new Map(), metas = new Map();
  const storage = () => { try { return getStorage(); } catch (e) { return null; } };
  return {
    get(stem) {
      if (!mem.has(stem)) {
        let raw = null;
        try { const s = storage(); raw = s ? s.getItem(STORAGE_PREFIX + stem) : null; } catch (e) {}
        mem.set(stem, reviveNotes(raw));
      }
      return mem.get(stem);
    },
    set(stem, notes) {
      mem.set(stem, notes);
      try {
        const s = storage();
        if (!s) return;
        if (notes.length) s.setItem(STORAGE_PREFIX + stem, JSON.stringify(notes));
        else s.removeItem(STORAGE_PREFIX + stem);
      } catch (e) {}
    },
    getMeta(stem) {
      if (!metas.has(stem)) {
        let raw = null;
        try { const s = storage(); raw = s ? s.getItem(META_PREFIX + stem) : null; } catch (e) {}
        metas.set(stem, reviveMeta(raw));
      }
      return metas.get(stem);
    },
    setMeta(stem, meta) {
      const m = reviveMeta(meta);
      metas.set(stem, m);
      try {
        const s = storage();
        if (!s) return;
        if (m.frozen || m.top) s.setItem(META_PREFIX + stem, JSON.stringify(m));
        else s.removeItem(META_PREFIX + stem);
      } catch (e) {}
    },
    forget(stem) { mem.delete(stem); metas.delete(stem); }, // the memory only (a test remounts from storage)
  };
}
