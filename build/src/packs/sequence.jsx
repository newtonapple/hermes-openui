// Pack "sequence": SequenceDiagram with its SeqParticipant, SeqMessage, SeqNote and SeqGroup parts. A pack of its own so a page
// that does not draw a sequence does not carry its layout engine.
import { defineComponent } from "@openuidev/react-lang";
import { z } from "zod/v4";
import { SequenceDiagramView, seqData } from "../components/sequence.jsx";
import { KINDS, STYLES, GROUP_KINDS } from "../components/sequence-layout.js";
import { Tooltip } from "../components/tooltip-schema.js";

const SeqParticipant = defineComponent({
  name: "SeqParticipant",
  description:
    "One column of a SequenceDiagram. id is unique and is what SeqMessage and SeqNote use; keep it short (`api`). label is the header text. kind only changes the header icon: actor (a person), service (the default), database, queue or external.",
  props: z.object({ id: z.string(), label: z.string(), kind: z.enum(KINDS).optional() }),
  component: () => null,
});

const SeqMessage = defineComponent({
  name: "SeqMessage",
  description:
    'One arrow from one participant id to another, drawn top to bottom in the order given, with its label above the arrow. from equal to to is a self-call (a small loop). style: "sync" (solid line, filled head, the default), "async" (solid, open head) or "return" (dashed, open head; use it for responses). id is optional and must be unique.',
  props: z.object({ from: z.string(), to: z.string(), label: z.string(), style: z.enum(STYLES).optional(), id: z.string().optional() }),
  component: () => null,
});

const SeqNote = defineComponent({
  name: "SeqNote",
  description: "A note box over one participant id, or one that spans from `over` to `to` when `to` is given. The text is wrapped to the box width.",
  props: z.object({ over: z.string(), text: z.string(), to: z.string().optional() }),
  component: () => null,
});

// A group holds more groups, so its steps are typed through getters: a plain `SeqGroup.ref` does not exist yet while it is being defined.
const stepTypes = () => z.union([SeqMessage.ref, SeqNote.ref, groupProps]);
const groupProps = z.object({
  kind: z.enum(GROUP_KINDS),
  label: z.string(),
  get steps() {
    return z.array(stepTypes());
  },
  get elseSteps() {
    return z.array(stepTypes()).optional();
  },
  elseLabel: z.string().optional(),
});

const SeqGroup = defineComponent({
  name: "SeqGroup",
  description:
    'A frame with a label tab (`alt cache hit?`) around some steps: "alt" (if / else), "opt" (optional), "loop" or "par" (in parallel). elseSteps adds a dashed divider labelled elseLabel with a second branch below it. Groups nest up to 3 deep. One SeqGroup per decision; put the other side in elseSteps, not in a second group.',
  props: groupProps,
  component: () => null,
});

const SequenceDiagram = defineComponent({
  name: "SequenceDiagram",
  description:
    "Sequence diagram of calls between participants: columns left to right, steps top to bottom, messages numbered unless numbered is false. A sync message opens an activation bar on its receiver until the next return back to the sender. Stays legible up to about 5 participants in the chat column; at most 10 participants and 100 steps, but aim for about 20 steps and split longer flows into two diagrams. Header labels are cut at 22 characters, message labels at 48, group labels at 40: keep them short. tooltips: Tooltip[] is the LAST argument (write null for each skipped optional argument before it, e.g. SequenceDiagram(participants, steps, null, null, [t1])) and adds a hover tooltip with an optional click-to-open detail panel (target: a participant id or a SeqMessage id; a message without an id cannot have a tooltip).",
  props: z.object({
    participants: z.array(SeqParticipant.ref),
    steps: z.array(z.union([SeqMessage.ref, SeqNote.ref, SeqGroup.ref])),
    title: z.string().optional(),
    numbered: z.boolean().optional(),
    tooltips: z.array(Tooltip.ref).optional(),
  }),
  component: ({ props }) => <SequenceDiagramView {...seqData(props)} tooltips={props.tooltips} />,
});

export const pack = { name: "sequence", components: [SeqParticipant, SeqMessage, SeqNote, SeqGroup, SequenceDiagram] };
