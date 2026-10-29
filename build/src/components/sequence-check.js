// Cross-reference checks for SequenceDiagram, shared by the Node validator (src/validate.mjs). Pure: no React, no DOM.
// Each message names the offending id and what to do about it.
import { seqData, MAX_PARTICIPANTS, MAX_STEPS, MAX_DEPTH } from "./sequence-layout.js";

const str = (v) => (v == null ? "" : String(v));
const oneLine = (s) => str(s).replace(/\s+/g, " ").trim();
const clip = (s, n) => { s = oneLine(s); return s.length > n ? s.slice(0, n - 1) + "\u2026" : s; };
const dupes = (arr) => [...new Set(arr.filter((x, i) => arr.indexOf(x) !== i))];

// props: the parsed props of one SequenceDiagram. Returns a list of problems (empty when it is fine).
export function checkSequence(props) {
  const data = seqData(props);
  const problems = [];
  const parts = data.participants;
  const ids = parts.map((p) => p.id);

  // `participants` holds columns only: a Text or a SeqMessage there would draw a blank header (seqData reads id and label from any props)
  const rawParts = props && Array.isArray(props.participants) ? props.participants : [];
  rawParts.forEach((x, n) => {
    const type = x && x.typeName;
    if (type !== "SeqParticipant") problems.push(`SequenceDiagram \`participants\` can hold only SeqParticipant, but item ${n + 1} is ${type ? str(type) : typeof x} (give each column as SeqParticipant(id, label, kind?) and put calls in \`steps\`).`);
  });

  const dupParts = dupes(ids);
  if (dupParts.length) problems.push(`SequenceDiagram has duplicate participant ids: ${dupParts.join(", ")} (every SeqParticipant id must be unique).`);
  if (parts.length > MAX_PARTICIPANTS) problems.push(`SequenceDiagram has ${parts.length} participants; use at most ${MAX_PARTICIPANTS} (split the flow into two diagrams, or merge participants that always appear together).`);

  // walk every step, nested ones included
  let total = 0;
  const msgs = [];
  const refs = []; // { kind, label, end, id }
  const bad = [];
  const tooDeep = [];
  const ALLOWED = "SeqMessage, SeqNote and SeqGroup";
  const walk = (steps, depth, where) => {
    steps.forEach((s, n) => {
      total++;
      if (s.t === "msg") {
        msgs.push(s);
        refs.push({ kind: "SeqMessage", label: s.label, end: "from", id: s.from });
        refs.push({ kind: "SeqMessage", label: s.label, end: "to", id: s.to });
      } else if (s.t === "note") {
        refs.push({ kind: "SeqNote", label: s.text, end: "over", id: s.over });
        if (s.to != null) refs.push({ kind: "SeqNote", label: s.text, end: "to", id: s.to });
      } else if (s.t === "group") {
        const name = `SeqGroup \`${s.kind}\` "${clip(s.label, 30)}"`;
        if (depth + 1 > MAX_DEPTH && depth === MAX_DEPTH) tooDeep.push(`${name} is nested ${depth + 1} deep; use at most ${MAX_DEPTH} levels (flatten the groups, or split the flow into two diagrams).`);
        walk(s.steps, depth + 1, `${name} \`steps\``);
        if (s.elseSteps) walk(s.elseSteps, depth + 1, `${name} \`elseSteps\``);
      } else {
        bad.push(`${where} can hold only ${ALLOWED}, but step ${n + 1} is ${s.typeName} (use SeqMessage for a call, SeqNote for a remark, SeqGroup for alt / opt / loop / par).`);
      }
    });
  };
  walk(data.steps, 0, "SequenceDiagram `steps`");
  problems.push(...bad);
  if (total > MAX_STEPS) problems.push(`SequenceDiagram has ${total} steps in total (messages, notes and groups, nested ones included); use at most ${MAX_STEPS} (split the flow into two diagrams).`);
  problems.push(...tooDeep);

  if (!parts.length) {
    problems.push("SequenceDiagram needs participants: give `participants` at least two SeqParticipant items (one is enough only when every message is a self-call).");
    return problems;
  }

  // ids named by messages and notes
  const labels = new Map(parts.map((p) => [oneLine(p.label).toLowerCase(), p.id]));
  const reported = new Set();
  for (const r of refs) {
    if (ids.includes(r.id)) continue;
    const key = `${r.kind}|${r.label}|${r.end}|${r.id}`;
    if (reported.has(key)) continue;
    reported.add(key);
    const hint = labels.has(oneLine(r.id).toLowerCase()) ? ` \`${r.id}\` is a label; the id is \`${labels.get(oneLine(r.id).toLowerCase())}\`.` : "";
    problems.push(`${r.kind} "${clip(r.label, 30)}" uses unknown participant id \`${r.id}\` in \`${r.end}\` (${r.kind} takes SeqParticipant id strings, not variable names or labels; known ids: ${ids.join(", ")}).${hint}`);
  }

  if (parts.length < 2 && msgs.some((m) => m.from !== m.to)) {
    problems.push(`SequenceDiagram has one participant (\`${ids[0]}\`), so every message must be a self-call; add the other participant as a SeqParticipant.`);
  }

  const msgIds = msgs.filter((m) => m.id != null).map((m) => m.id);
  const dupMsg = dupes(msgIds);
  if (dupMsg.length) problems.push(`SequenceDiagram has duplicate message ids: ${dupMsg.join(", ")} (every SeqMessage id must be unique).`);
  return problems;
}
