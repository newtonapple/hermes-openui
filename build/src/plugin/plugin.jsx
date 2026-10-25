// Hermes desktop plugin: renders OpenUI Lang widgets natively in the chat transcript.
//
//   ::openui{file="/Users/<you>/.hermes/widgets/<name>.oui"}
//
// The runtime loads ONCE (this file) instead of being copied into every widget, there is no 512 KiB per-widget cap on
// it, and widgets re-theme live with the app. Trade-offs the iframe version does not have: this runs with full app
// authority (no sandbox), and the SDK's composer.submit types a VISIBLE user message where the iframe's
// window.hermes.send is a hidden turn.
import { t0 } from "./t0.js";
import { useEffect, useState } from "react";
import { host, TRANSCRIPT_DIRECTIVE_AREA } from "@hermes/plugin-sdk";
import { Renderer, createLibrary } from "@openuidev/react-lang";
import { ThemeProvider } from "../../node_modules/@openuidev/react-ui/dist/components/ThemeProvider/index.js";
import { coreComponents } from "../core-components.jsx";
import { packs } from "../packs/index.js";
import { openuiTheme } from "../oui-theme.js";

const ROOT_CLASS = "hermes-openui-root";
const STYLE_ATTR = "data-hermes-openui";
const MAX_COLUMN_WIDTH = 640; // same column cap the iframe version adopts
const MAX_INTENT_LENGTH = 500; // same cap as window.hermes.send
const MIN_INTENT_GAP_MS = 1000; // same rate limit as window.hermes.send
const SOURCE_MAX_BYTES = 512 * 1024; // the file bridge truncates here; refuse instead of rendering half a widget

// Only widget files the skill wrote, never an arbitrary path a model (or an injected prompt) names.
const WIDGET_PATH = /\/widgets\/[A-Za-z0-9._-]+\.oui$/;

// The iframe version receives these through the app's theme prelude (inline-preview-directive.tsx THEME_BRIDGE_TOKENS);
// natively we alias the same app tokens on our own wrapper, so a theme switch restyles live with no re-render.
const THEME_BRIDGE = {
  "--foreground": "var(--ui-text-primary)",
  "--muted-foreground": "var(--ui-text-tertiary)",
  "--accent": "var(--ui-accent)",
  "--border": "var(--ui-stroke-tertiary)",
  "--card": "var(--ui-bg-editor)",
};

const library = createLibrary({ root: "Stack", components: [...coreComponents, ...packs.flatMap((p) => p.components)] });
const COMPONENT_COUNT = coreComponents.length + packs.reduce((n, p) => n + p.components.length, 0);
const WIDGET_CSS = packs.map((p) => p.css).filter(Boolean).join("\n");

// A hot reload re-evaluates this module: drop the previous copy's stylesheet first.
if (typeof document !== "undefined") document.querySelectorAll(`style[${STYLE_ATTR}]`).forEach((n) => n.remove());

// __PROBE__ is true only in the throwaway verification build, which reports through console.error because the app mirrors
// only error-level console lines into desktop.log.
const say = __PROBE__ ? console.error.bind(console) : console.info.bind(console);
try {
  say("[hermes-openui] module evaluated in " + (performance.now() - t0).toFixed(1) + " ms; " + COMPONENT_COUNT + " components; directive ::openui available once the plugin is enabled");
} catch (e) {}

let styleUsers = 0;
let styleEl = null;
function useWidgetStyles() {
  useEffect(() => {
    if (styleUsers++ === 0) {
      styleEl = document.createElement("style");
      styleEl.setAttribute(STYLE_ATTR, "");
      styleEl.textContent = WIDGET_CSS;
      document.head.appendChild(styleEl);
    }
    return () => {
      if (--styleUsers === 0 && styleEl) {
        styleEl.remove();
        styleEl = null;
      }
    };
  }, []);
}

function readColorMode() {
  const m = document.documentElement.dataset.hermesMode;
  if (m === "light" || m === "dark") return m;
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch (e) {
    return "light";
  }
}
function useColorMode() {
  const [mode, setMode] = useState(readColorMode);
  useEffect(() => {
    const obs = new MutationObserver(() => setMode(readColorMode()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-hermes-mode", "class"] });
    return () => obs.disconnect();
  }, []);
  return mode;
}

async function readWidget(file) {
  if (!WIDGET_PATH.test(file) || file.includes("..")) throw new Error("not a widget file (expected .../widgets/<name>.oui)");
  const bridge = window.hermesDesktop;
  if (!bridge || typeof bridge.readFileText !== "function") throw new Error("the desktop file bridge is unavailable");
  const r = await bridge.readFileText(file);
  if (!r || typeof r.text !== "string") throw new Error("could not read " + file.split("/").pop());
  if (r.binary) throw new Error("not a text file");
  if (r.truncated || (r.byteSize ?? 0) > SOURCE_MAX_BYTES) throw new Error("widget source is over 512 KiB");
  if (!r.text.trim()) throw new Error("empty widget");
  return r.text;
}

let lastIntentAt = 0;
function onAction(event) {
  if (!event || event.type !== "continue_conversation" || !event.humanFriendlyMessage) return; // open_url: not allowed, same as the sandbox
  const text = String(event.humanFriendlyMessage).trim();
  const now = Date.now();
  if (!text || text.length > MAX_INTENT_LENGTH || now - lastIntentAt < MIN_INTENT_GAP_MS) return;
  lastIntentAt = now;
  let sent = false;
  try {
    sent = host.composer.submit(null, text);
  } catch (e) {
    sent = false;
  }
  if (!sent) {
    try {
      host.notify({ kind: "error", message: "OpenUI widget: no chat input accepted the message." });
    } catch (e) {}
  }
}

function Notice({ children }) {
  return <div style={{ fontSize: 12.5, color: "var(--ui-text-tertiary)", padding: "4px 0" }}>{children}</div>;
}

function OpenUIWidget({ file }) {
  const [state, setState] = useState({ status: "loading" });
  const [missing, setMissing] = useState("");
  const mode = useColorMode();
  useWidgetStyles();
  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });
    setMissing("");
    readWidget(file).then(
      (text) => alive && setState({ status: "ready", text }),
      (err) => alive && setState({ status: "error", message: String((err && err.message) || err) }),
    );
    return () => {
      alive = false;
    };
  }, [file]);

  if (state.status === "loading") return <Notice>Loading widget…</Notice>;
  if (state.status === "error") return <Notice>OpenUI widget unavailable: {state.message}</Notice>;
  return (
    <div className={ROOT_CLASS} data-hermes-openui-widget="" style={{ ...THEME_BRIDGE, maxWidth: MAX_COLUMN_WIDTH, minWidth: 0, color: "var(--foreground)" }}>
      <ThemeProvider mode={mode} lightTheme={openuiTheme} darkTheme={openuiTheme} cssSelector={"." + ROOT_CLASS}>
        <Renderer
          response={state.text}
          library={library}
          isStreaming={false}
          onAction={onAction}
          onError={(errors) => {
            const names = [...new Set((errors || []).filter((e) => e && e.code === "unknown-component").map((e) => e.component))];
            if (names.length) setMissing(names.join(", "));
          }}
        />
      </ThemeProvider>
      {missing ? <Notice>Unknown component(s): {missing}</Notice> : null}
    </div>
  );
}

export default {
  id: "hermes-openui",
  name: "OpenUI widgets",
  description: "Renders OpenUI Lang widgets natively in chat: ::openui{file=\".../widgets/<name>.oui\"}",
  defaultEnabled: __PROBE__, // false when shipped: runs with full app authority, so the user opts in under Capabilities > Plugins > Plugins
  register(ctx) {
    try { say("[hermes-openui] enabled: ::openui directive registered"); } catch (e) {}
    ctx.register({
      id: "hermes-openui-directive",
      area: TRANSCRIPT_DIRECTIVE_AREA,
      data: {
        name: "openui",
        render: ({ attrs }) => (attrs && typeof attrs.file === "string" && attrs.file ? <OpenUIWidget file={attrs.file} /> : null),
      },
    });
  },
};
