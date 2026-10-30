// Cross-reference and limit checks for the `tooltips` argument of Dag, Erd, InfraMap, SequenceDiagram, Table, Metric, BarChart, GeoMap and Image, called from the Node
// validator (src/validate.mjs). Pure: it imports only tooltips-core.js. Every message names the target and what to do.
import { LIMITS, TIP_HOSTS, TIP_EXAMPLES, TARGET_FORMS, checkLink, targetSummary } from "./tooltips-core.js";

const str = (v) => (v == null ? "" : String(v));
const clip = (s, n) => { s = str(s).replace(/\s+/g, " ").trim(); return s.length > n ? s.slice(0, n - 1) + "\u2026" : s; };
const plural = (n, one, many) => n + " " + (n === 1 ? one : many);

function ambiguity(kind, key, whats, ends) {
  const n = whats.length;
  const lead = kind + " tooltip target `" + key + "` is ambiguous: ";
  if (whats.every((w) => w === "link")) {
    // The link ends come from the links themselves: a node id may contain `>`, so the key cannot be split.
    const pairs = [...new Set((ends || []).map((p) => p[0] + "\u0000" + p[1]))].map((k) => k.split("\u0000"));
    if (pairs.length > 1) return lead + "it matches " + n + " links (" + pairs.map((p) => "`" + p[0] + "` to `" + p[1] + "`").join(", ") + "); a node id with `>` in it makes the target unclear, so rename it.";
    return lead + n + " links join `" + pairs[0][0] + "` to `" + pairs[0][1] + "` (remove the extra links, or put the tooltip on the nodes instead).";
  }
  if (whats.every((w) => w === "column" || w === "cell")) {
    const header = key.startsWith("col:") ? key.slice(4) : key.slice(key.indexOf(".") + 1);
    return lead + n + " columns are headed `" + header + "` (give each column its own header).";
  }
  if (whats.every((w) => w === "bar")) return lead + n + " bars are labelled `" + key + "` (give each bar its own label).";
  if (whats.every((w) => w === "point")) return lead + n + " points are labelled `" + key + "` (give each point its own label).";
  if (whats.includes("participant") && whats.includes("message")) return lead + "it is both a participant id and a message id (give the message another id).";
  return lead + n + " elements share that name (" + [...new Set(whats)].join(", ") + "); make the names unique.";
}

// props: the parsed props of one diagram. kind: "Dag" | "Erd" | "InfraMap" | "SequenceDiagram". Returns a list of problems.
export function checkTooltips(kind, props) {
  const raw = props && Array.isArray(props.tooltips) ? props.tooltips : [];
  if (!raw.length) return [];
  const problems = [];
  const summary = targetSummary(kind, props);
  const items = [];
  raw.forEach((x, n) => {
    const type = x && x.typeName;
    if (type !== "Tooltip") {
      problems.push(kind + " `tooltips` can hold only Tooltip, but item " + (n + 1) + " is " + (type ? str(type) : typeof x) + " (give each remark as Tooltip(target, hint?, detail?, code?, language?, tone?, link?, linkLabel?)).");
      return;
    }
    items.push(x.props || {});
  });
  if (raw.length > LIMITS.count) problems.push(kind + " has " + raw.length + " tooltips; use at most " + LIMITS.count + " (add a tooltip only where there is something worth saying).");

  const distinct = new Set(items.map((a) => str(a.target)));
  if ((kind === "Metric" || kind === "Image") && distinct.size > 1) {
    problems.push(kind + " takes one tooltip at most (the whole " + (kind === "Metric" ? "tile" : "picture") + " is the target, `" + (summary.keys[0] || "") + "`), but it has " + distinct.size + ".");
  }
  const seen = new Set(), dup = new Set();
  items.forEach((a) => {
    const target = str(a.target);
    const name = "Tooltip for `" + clip(target, 40) + "`";
    const blank = (v) => v == null || str(v).trim() === "";
    if (blank(a.hint) && blank(a.detail) && blank(a.code) && a.link == null) {
      problems.push(name + " has none of hint, detail, code or link, so it would do nothing (add one of them, or remove the Tooltip).");
    }
    const over = (field, value, limit, unit) => {
      if (value != null && str(value).length > limit) problems.push(name + ": " + field + " is " + str(value).length + " " + unit + "; the limit is " + limit + ".");
    };
    over("hint", a.hint, LIMITS.hint, "characters");
    over("detail", a.detail, LIMITS.detail, "characters");
    over("code", a.code, LIMITS.code, "characters");
    if (a.code != null) {
      const lines = str(a.code).replace(/\n+$/, "").split("\n").length;
      if (lines > LIMITS.codeLines) problems.push(name + ": code has " + lines + " lines; the limit is " + LIMITS.codeLines + ".");
    }
    over("language", a.language, LIMITS.language, "characters");
    over("linkLabel", a.linkLabel, LIMITS.linkLabel, "characters");
    if (a.link != null) {
      const r = checkLink(str(a.link));
      if (!r.ok) problems.push(name + ": link `" + clip(a.link, 60) + "` " + r.reason + ".");
    }

    if (seen.has(target)) { dup.add(target); return; }
    seen.add(target);
    const whats = summary.count[target];
    if (!whats) {
      const shown = summary.keys.slice(0, 5).join(", ");
      const more = summary.keys.length > 5 ? " and " + (summary.keys.length - 5) + " more" : "";
      const form = TARGET_FORMS[kind] ? "; " + TARGET_FORMS[kind] : "";
      problems.push(kind + " tooltip target `" + clip(target, 60) + "` matches no element (" + (summary.keys.length ? "valid targets: " + shown + more + form : "the " + (TARGET_FORMS[kind] ? kind.toLowerCase() : "diagram") + " has nothing a tooltip can name") + ").");
    } else if (whats.length > 1) {
      problems.push(ambiguity(kind, target, whats, summary.ends[target]));
    }
  });
  dup.forEach((t) => problems.push(kind + " has more than one tooltip for target `" + clip(t, 60) + "` (keep one Tooltip per element)."));
  return problems;
}

const hostList = () => TIP_HOSTS.slice(0, -1).join(", ") + " or " + TIP_HOSTS[TIP_HOSTS.length - 1];

// The rule in one sentence, appended to the errors that come from a Tooltip in the wrong place.
export function hostSentence() {
  return "A Tooltip only goes in the last argument (`tooltips`) of " + hostList() + ".";
}
// An unreachable Tooltip: the line that says it is defined but never used gets the rule.
export function orphanTooltipHint() {
  return hostSentence();
}
// A statement of kind `kind` holds a list of Tooltips that its signature cannot take (a slot of another type, or past the last argument).
// name: the first Tooltip variable in the list, for the example.
export function misplacedListHint(kind, name) {
  const ex = TIP_EXAMPLES[kind];
  if (ex) return "`tooltips` is the LAST argument: write `null` for each skipped optional argument before it, for example `" + ex.replace("t1", name || "t1") + "`.";
  return kind + " takes no tooltips. " + hostSentence();
}
// Whether the text of one statement has a list whose items are Tooltips (variables named in `names`, or an inline Tooltip(...)). Strings are ignored.
export function holdsTooltipList(text, names) {
  const t = str(text).replace(/"(?:[^"\\]|\\.)*"/g, '""');
  if (/[\[,]\s*Tooltip\s*\(/.test(t)) return true;
  return (names || []).some((n) => new RegExp("[\\[,]\\s*" + String(n).replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*[,\\]]").test(t));
}

// A Tooltip that is not an item of the `tooltips` argument of one of the components in TIP_HOSTS draws nothing. name is its variable (undefined when it is written inline).
export function strayTooltip(name) {
  const who = name ? "Tooltip `" + name + "`" : "A Tooltip written inline";
  const hosts = hostList();
  return who + " is used outside a component that takes tooltips: a Tooltip only goes in the last argument (`tooltips`) of " + hosts + ", for example `Dag(nodes, edges, null, null, [" + (name || "t1") + "])`.";
}
