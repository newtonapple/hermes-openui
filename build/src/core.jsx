// Browser core (the "engine"): React, the OpenUI Lang parser/renderer, the Hermes theme and the always-on
// components. Optional components arrive as packs: each pack script calls window.__HM.register(pack) before
// mount(). Packs are built with React, zod and react-lang mapped onto window.__HM.mods (see build.mjs), so
// they share this file's single instance of each (a second copy of react-lang would break its context).
// Do NOT expose @openuidev/lang-core here: a namespace import defeats tree-shaking and drags in its telemetry code.
import * as ReactNS from "react";
import * as JsxRuntime from "react/jsx-runtime";
import * as ReactDOMNS from "react-dom";
import * as ReactDOMClient from "react-dom/client";
import * as Zod from "zod/v4";
import { createRoot } from "react-dom/client";
import { createLibrary, Renderer, defineComponent, action, useTriggerAction, useIsQueryLoading } from "@openuidev/react-lang";
import * as UiTheme from "../node_modules/@openuidev/react-ui/dist/components/ThemeProvider/index.js";
const { ThemeProvider } = UiTheme;
import { coreComponents } from "./core-components.jsx";
import { Tooltip } from "./components/tooltip-schema.js";
import * as TooltipsModule from "./components/tooltips.jsx";
import * as CodeModule from "./components/code.jsx";
import { openuiTheme } from "./oui-theme.js";

// The ONLY react-lang exports packs may use. A namespace import (import * as) would keep every export and with it
// lang-core's dormant telemetry code, so this is an explicit list; build.mjs fails if a pack imports anything else.
const ReactLangShared = { defineComponent, action, useTriggerAction, useIsQueryLoading };

const packs = {};

function register(pack) {
  if (!pack || !pack.name || packs[pack.name]) return;
  packs[pack.name] = pack;
  if (pack.css) {
    const s = document.createElement("style");
    s.setAttribute("data-hermes-oui", pack.name);
    s.textContent = pack.css;
    document.head.appendChild(s);
  }
}

function onAction(event) {
  // @ToAssistant("...") -> hidden user turn in the owning Hermes session.
  if (event && event.type === "continue_conversation" && event.humanFriendlyMessage) {
    const send = window.hermes && window.hermes.send;
    if (send) send(String(event.humanFriendlyMessage)).then((ack) => ack && ack.ok === false && console.warn("hermes.send failed", ack));
  } else if (event && event.type === "open_url") {
    // Sandboxed iframe: navigation is blocked on purpose. Surface the URL instead.
    console.info("open_url blocked in widget:", event.params && event.params.url);
  }
}

const prefersDark = () => {
  try { return window.matchMedia("(prefers-color-scheme: dark)").matches; } catch (e) { return false; }
};

// A component whose pack was not embedded would otherwise vanish silently (render.py picks packs from the source,
// so this should not happen; if it does, say so on the page instead of showing a partial widget).
function reportErrors(errors) {
  const missing = [...new Set((errors || []).filter((e) => e && e.code === "unknown-component").map((e) => e.component).filter(Boolean))];
  const el = document.getElementById("oui-err");
  if (missing.length && el) {
    el.textContent = "Widget is missing component(s): " + missing.join(", ") + ". Their pack was not embedded; re-render with --all-packs.";
  }
}

window.__HM = {
  mods: {
    react: ReactNS,
    "react/jsx-runtime": JsxRuntime,
    "react-dom": ReactDOMNS,
    "react-dom/client": ReactDOMClient,
    zod: Zod,
    "@openuidev/react-lang": ReactLangShared,
    "react-ui/ThemeProvider": UiTheme,
    // Internal, for the built-in diagram packs only (build.mjs SHARED_FILES): the one Tooltip definition their `tooltips` argument refers to.
    "hermes-openui/tooltip-schema": { Tooltip },
    // Also internal: the one interaction module (Tipped, Hot, HotBox, ...) and the code highlighter it uses, so the core carries them once
    // and the packs that draw a tooltip (diagrams, infra, sequence, map) or a code block (text) do not bundle a copy.
    "hermes-openui/tooltips": TooltipsModule,
    "hermes-openui/code": CodeModule,
  },
  register,
  packs,
};

window.HermesOpenUI = {
  packs: () => Object.keys(packs),
  mount(el, source) {
    const library = createLibrary({
      root: "Stack",
      components: [...coreComponents, ...Object.values(packs).flatMap((p) => p.components)],
    });
    createRoot(el).render(
      <ThemeProvider mode={prefersDark() ? "dark" : "light"} lightTheme={openuiTheme} darkTheme={openuiTheme}>
        <Renderer response={source} library={library} isStreaming={false} onAction={onAction} onError={reportErrors} />
      </ThemeProvider>,
    );
  },
};
