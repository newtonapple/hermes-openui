# Development notes

Design, measurements and the traps found while building `hermes-openui`. Rules and commands are in [AGENTS.md](../AGENTS.md); this file explains why.

## Request flow

```
model ── render_widget(source) ──▶ lint.py        structural checks, pure Python (always)
                                    │
                                    ▼
                                 node assets/validate.cjs     the real OpenUI parser + cross-reference checks (when Node exists)
                                    │
                    mode=preview ───┴─── mode=native
                         │                    │
        page.build_page: core + needed packs   write <slug>.oui (images inlined)
        embedded as base64 gzip in one HTML     │
                         │                      ▼
        write <slug>.html                  directive ::openui{file="….oui"}
                         │
                         ▼
        directive ::preview{file="….html"}  ──▶ the model puts it alone on a line in its reply
```

All output goes to `$HERMES_HOME/widgets/<name>-<6 hex>.{html,oui}` (profile-aware via `get_hermes_home()`).

## The runtime is a core plus packs

A widget page must fit the app's 512 KiB file read (it truncates silently and a cut page renders blank), and the sandboxed frame cannot load sibling files, so the whole runtime travels inside the page. Page size is `gzip(core + packs used) × 4/3 + shell + content`, and `page.py` refuses more than 480 KB.

| Piece | Components | Adds to the page |
|---|---|---|
| core (always) | Stack, Text, Card, Metric, Table, BarChart, Callout, Button, Tabs, TabItem, Image | about 267 KB |
| `charts` | LineChart, AreaChart, PieChart, RadarChart, Series | +84 KB |
| `map` | GeoMap, GeoPoint | +15 KB |
| `diagrams` | Dag, DagNode, Erd, Entity, Relation | +7 KB |
| `text` | Markdown, CodeBlock, Faq, FaqItem, Choice | +6 KB |

`page.select_packs` scans the source for `Name(` calls (text inside strings is blanked first) and embeds only the packs those names live in (`assets/packs.json` maps component → pack). A dashboard with no charts is about 275 KB; every pack is about 390 KB. If detection ever misses, the page prints `Widget is missing component(s): X` instead of showing a silently partial widget.

Of the core's 267 KB, `zod` is 444 KB raw and React DOM 205 KB; OpenUI's own visual components are about 12 %. OpenUI's ready-made wrappers for tabs, cards and the like pull in syntax highlighting, math and markdown engines (hundreds of KB each), so those components are written locally; only the four charts are OpenUI's own code. Provenance: `build/src/core-components.jsx` and `build/src/packs/*.jsx`.

## Why a tool, and why it stays cheap

The earlier design was a skill that told the model to run a script. A tool plugin is cheaper in context and validates server-side. The catch is discovery: plugin skills are **not** listed in the system prompt, and Hermes defers plugin tools behind Tool Search (`tool_search` / `tool_describe` / `tool_call`), so the model finds the tool through one always-visible listing line and a BM25 search over the tool's text.

How that search works (`tools/tool_search_catalog.py` in Hermes):
- It indexes the tool name, its toolset label, the **full description** and the top-level parameter names.
- It gates on the query word with the highest IDF: a tool that lacks that word is not offered at all, and a word no tool carries offers nothing. Recall therefore depends on which everyday words the description contains.
- The listing shows only the first sentence, clipped to 60 characters: `- render_widget: Draw charts, graphs, DAG/ER diagrams, maps and dashboards.`

Measured against a 178-tool catalog (Hermes's own deferred tools plus 172 names shaped like a large MCP server): the first draft of the description found 13 of 20 keyword queries; adding graph, plot, flowchart, schema, topology and KPI found 20 of 20, with no false hits on unrelated requests. Whole-sentence queries still miss when a word is absent from every tool; that is the engine's design, and a model that sees the listing line usually goes straight to `tool_describe`. Re-measure with `tools/verify_discovery.py` after any wording change.

The component reference (about 2,800 tokens) is deliberately **not** in the schema: with Tool Search off the schema rides every API call. `render_widget(reference=true)` returns it on demand.

## Display modes

`preview` returns `::preview`, Hermes's built-in directive: a sandboxed `srcdoc` iframe, hidden-turn clicks, works on remote gateways. `native` writes only the `.oui` source and returns `::openui`, which the desktop half (`desktop/plugin.js`) renders inside the chat with the app's own React. Measured in headless Chrome: 20 widgets ready in about 50 ms against about 530 ms, a few MB against about 300 MB; file per widget 1–2 KB against 275–390 KB.

What `native` costs: full app authority (a desktop plugin is not sandboxed), visible user messages for clicks (the SDK's `composer.submit` has no hidden flag; core's preview uses an internal one), and local files only (it reads through `window.hermesDesktop.readFileText`, restricted to `…/widgets/<name>.oui`). The desktop half passes `hermes plugins validate`'s `desktop surface` check, which forbids `eval`, `new Function`, reaching into app markup, and any import except the SDK and React.

## Build and reproducibility

`build/` holds the sources and a lockfile. `npm run build` runs `build.mjs` (core, packs, validator, reference, manifest), `plugin-build.mjs` (desktop half) and the loader check. Installs use `--ignore-scripts` and OpenUI's documented opt-outs, because `@openuidev/lang-core` ships an install-time telemetry ping.

A clean-room check was done: copy `build/` without `node_modules`, `npm ci` from the lockfile, build, and compare. The uncompressed bundles are byte-identical to the shipped ones (`assets/packs.json` records each `sha256`). gzip bytes are **not** comparable across Node versions (the deflate stream differs by about a kilobyte), which is why the hash is over the uncompressed bundle.

Build guards (each fails the build): a pack that bundles its own React/zod/react-lang; a pack importing a react-lang export the core does not share (`ReactLangShared` in `src/core.jsx`); network code in any browser file; `packs/index.js` and `src/packs/*.jsx` disagreeing.

## Traps

1. **Shared context must be one instance.** A pack that bundled its own copy of OpenUI's `ThemeProvider` silently fell back to upstream's default blue palette (no error). `SHARED_FILES` in `build.mjs` maps the resolved path onto the core's module; the build warns about duplicated modules.
2. **Never expose a whole upstream package.** `import * as ReactLang` keeps every export and, with it, lang-core's dormant telemetry (a `fetch` and a CDN URL). The core shares an explicit name list.
3. **The desktop loader is regex-based.** It rewrites `import`, whitespace, a quote. esbuild emits a space-less `import"react"` for modules that only needed React for JSX; that stays bare and the browser refuses the whole file (`Failed to resolve module specifier "react"`). Marking the externals `sideEffects: false` prevents it. A harness with a native import map hides this, and so does a replica of the loader's own regex. `build/tests/plugin-loader-check.mjs` replays the app's real rewrite (extracted from `runtime-loader.ts`) and then parses the result with a real parser; its red case is the broken build.
4. **`react-dom` is not importable** by a disk plugin (only `@hermes/plugin-sdk`, `react`, `react/jsx-runtime`): portals and `flushSync` get an inline shim, so chart tooltips render inside the widget.
5. **Bundled CommonJS calling `require("react")`** throws in a browser module; a banner defines a `require` that returns the host's React.
6. **Only error-level console lines reach `desktop.log`.** To prove a load, build a throwaway probe (`OPENUI_PROBE=1`) that announces through `console.error`, read the log, then reinstall the normal build.
7. **OpenUI's `ThemeProvider` writes CSS variables on `body`** by default; pass a `cssSelector` for the widget's own wrapper, and alias the app tokens on it (`--ui-text-primary` → `--foreground`, `--ui-accent` → `--accent`, …) so a theme change restyles live.
8. **A Choice disables its other options after one pick**, so a click-everything test over-counts messages.
9. **One-shot headless Chrome hangs** here (`--screenshot`, `--dump-dom`, even on a blank page). `tools/shoot.py` launches Chrome with a debugging port and speaks the DevTools protocol over a small stdlib WebSocket client.
10. **iCloud Drive and Git do not mix well.** Keep `node_modules` out of a synced folder; build in a normal directory.

## What is verified, and what is not

Verified in this repository: 60+ unit tests (Python 3.9); Hermes's own `plugins validate` and `plugins doctor`; install, enable and tool registration in an isolated Hermes home; that the tool is deferred behind Tool Search and enabled for desktop sessions by default; dispatch through Hermes's own function-call path; the desktop half evaluated in the real app (module evaluation about 7 ms, directive registered, file bridge and path guard exercised); structural parity between native and iframe rendering for every example; a clean-room rebuild.

Not verified: how the desktop app *renders* a widget (only a headless-Chrome harness was used); the **Capabilities → Plugins** Desktop switch for a manually copied package (its fallback is to copy `desktop/plugin.js` to `~/.hermes/desktop-plugins/hermes-openui/`); Linux and Windows; any model other than the one used while building.

## Ideas

- A hidden-turn option for plugins (`host.composer.submit(sessionId, text, { hidden: true })`) would remove the main `native` trade-off. It needs an SDK change in Hermes.
- Pruning old widgets (they are never deleted automatically, because old messages still point at them).
- A tool-side `list_components` or per-component reference to shrink the 2,800-token first use.
