// Pack "text": Markdown, CodeBlock, Faq, Choice (they share the markdown/code renderers).
import React from "react";
import { defineComponent } from "@openuidev/react-lang";
import { z } from "zod/v4";
import { renderMarkdown } from "../components/markdown.jsx";
import { CodeView } from "../components/code.jsx";
import { FaqView, ChoiceView } from "../components/qa.jsx";

const Markdown = defineComponent({
  name: "Markdown",
  description:
    "Rich text from a markdown string (use \\n for newlines): headings, **bold**, *italic*, `code`, lists, > quotes, tables, ``` fenced code, ---. Links are shown but not clickable.",
  props: z.object({ text: z.string() }),
  component: ({ props }) => <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 14, minWidth: 0 }}>{renderMarkdown(props.text)}</div>,
});

const CodeBlock = defineComponent({
  name: "CodeBlock",
  description:
    'Syntax-highlighted code with a Copy button. language: python|js|ts|bash|sql|yaml|json|go|rust (others render unhighlighted). code is a string (use \\n for newlines). Optional title (e.g. a filename).',
  props: z.object({ code: z.string(), language: z.string().optional(), title: z.string().optional() }),
  component: ({ props }) => <CodeView code={props.code} language={props.language} title={props.title} />,
});

const FaqItem = defineComponent({
  name: "FaqItem",
  description: "One Q&A entry: question, answer (markdown string). Only valid inside Faq.",
  props: z.object({ question: z.string(), answer: z.string() }),
  component: () => null,
});
const Faq = defineComponent({
  name: "Faq",
  description: "Collapsible Q&A list. items: FaqItem[]. firstOpen: true expands the first answer.",
  props: z.object({ items: z.array(FaqItem.ref), firstOpen: z.boolean().optional() }),
  component: ({ props }) => <FaqView items={props.items ?? []} firstOpen={props.firstOpen} />,
});
const Choice = defineComponent({
  name: "Choice",
  description:
    'A question with clickable options for the USER to answer. Clicking sends "<question> — <option>" to the agent as a new turn. options: string[] (2-6). Optional hint line. Use to ask clarifying questions.',
  props: z.object({ question: z.string(), options: z.array(z.string()), hint: z.string().optional() }),
  component: ({ props }) => <ChoiceView question={props.question} options={props.options ?? []} hint={props.hint} />,
});

export const pack = { name: "text", components: [Markdown, CodeBlock, FaqItem, Faq, Choice] };
