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
| `infra` | InfraMap, InfraZone, InfraNode, InfraLink | +9 KB |
| `sequence` | SequenceDiagram, SeqParticipant, SeqMessage, SeqNote, SeqGroup | +9 KB |
| `text` | Markdown, CodeBlock, Faq, FaqItem, Choice | +6 KB |

`page.select_packs` scans the source for `Name(` calls (text inside strings is blanked first) and embeds only the packs those names live in (`assets/packs.json` maps component → pack). A dashboard with no charts is about 275 KB; every pack is about 390 KB. If detection ever misses, the page prints `Widget is missing component(s): X` instead of showing a silently partial widget.

Of the core's 267 KB, `zod` is 444 KB raw and React DOM 205 KB; OpenUI's own visual components are about 12 %. OpenUI's ready-made wrappers for tabs, cards and the like pull in syntax highlighting, math and markdown engines (hundreds of KB each), so those components are written locally; only the four charts are OpenUI's own code. Provenance: `build/src/core-components.jsx` and `build/src/packs/*.jsx`.

## Custom component packs

The runtime already had a plugin point: a pack is a script that calls `window.__HM.register({name, components})`, with React, zod and `defineComponent` taken from `window.__HM.mods`, and `page.build_page` already embedded packs as blobs. User-linked packs reuse that, so **the core and the built-in packs did not change** and stay byte-identical to a clean rebuild.

What was added around it:

| Piece | Job |
|---|---|
| `packs.py` | Reads the JSON header (`api`, `name`, a component to reference-line map) so Python knows a pack's components without running JavaScript. Checks names against the built-ins and other packs, size (200 KB) and forbidden APIs. A broken pack is skipped and reported, never fatal. |
| `lint.py`, `tools.py` | Take the built-in names plus the packs' names, append the packs' reference lines to `reference=true`, refuse custom components in native mode, and report broken packs as `pack_warnings`. |
| `page.py` | Embeds only the packs whose components the source calls, gzipped with a fixed timestamp so the bytes are reproducible. |
| `build/src/validate.mjs` | `--pack FILE` evaluates the pack in a bare `vm` context against the same React, zod and `defineComponent`, so zod schemas are enforced as in the page. It runs the pack's `validate(typeName, props)` hook on each of its nodes, and fails if the header and the registered components disagree. |

Decisions worth knowing:

- **A header, not introspection.** Running the script to learn its components needs Node and a sandbox on every call. The header costs the author one JSON comment, and the validator then checks the header against reality.
- **Plain scripts, no imports.** A pack needs no build step. Authors who want JSX can bundle it themselves the way `build.mjs` bundles the built-in packs.
- **Preview mode only.** The sandboxed frame already contains any script an agent can put in `::preview`. Native mode renders in the app with full authority, so it refuses packs.
- **The lint is not a boundary.** It matches words in code with strings and comments blanked. The sandbox is the boundary.
- **Without Node a custom component is unchecked.** The structural lint passes, and the browser draws a bad argument as if it were missing, with no error (seen when rendering the guide's example).

InfraMap is the built-in `infra` pack. It started as a user pack, and the port is pixel-identical to it in both themes on the four sample sources. Its renderer is `build/src/components/infra.jsx`, its schemas are `build/src/packs/infra.jsx`, and the cross-reference checks (unknown id, label used as id, duplicate id, empty zone) are in `build/src/validate.mjs`. It is a separate pack so a page that only draws a Dag does not get heavier. A user pack that reuses one of its names is skipped, with a message. The four reference lines add about 320 tokens to the on-demand reference for every user, because built-ins always appear in it.

SequenceDiagram is the built-in `sequence` pack, built the same way. Its layout is a pure function (`build/src/components/sequence-layout.js`, no imports, so Node tests load it without a bundler), its checks are `build/src/components/sequence-check.js`, called from `build/src/validate.mjs`, its view is `build/src/components/sequence.jsx` and its schemas are `build/src/packs/sequence.jsx`. A `SeqGroup` holds groups, so its `steps` are typed with getters (a recursive zod object); the reference still prints `(SeqMessage | SeqNote | SeqGroup)[]`. Activation bars are derived: a `sync` message opens a bar on its receiver and the next `return` back to the sender closes the most recent open one (`matchActivations`), so there is no argument for them. Text widths are estimates (characters times an average advance), as in InfraMap. The five reference lines add about 470 tokens. The reserved names are the manifest's component names, so no list needed extending in `packs.py`.

## Export

`export_widgets` is a second tool so `render_widget`'s schema and discoverability stay as they were. Measured with Tool Search's own ranking against a catalog of 172 unrelated tools: `render_widget` keeps 25 of 25 keyword queries, and all 7 export queries rank `export_widgets` first. The export description avoids `render_widget`'s vocabulary on purpose: in the export agent's measurement the first draft cost `render_widget` one top-5 hit.

- **The page** (`page.build_export_page`) is the widget template plus page chrome: a centered column, a heading per section, a footer, print rules, and one `HermesOpenUI.mount` per section. Runtime and packs are embedded once. It defines its own `--accent`, because the runtime's `AccentColor` fallback is not recognized by Chrome 145.
- **`window.hermes`** is shimmed, only when the host did not provide one, so a Button shows a notice instead of failing silently. A forced theme installs a `matchMedia` shim before the runtime runs, so the runtime's own dark check agrees.
- **Where files go.** The default is `<home>/exports`. `cache/documents` looks like the obvious "assets" folder, but it is the gateway's inbound media cache, and housekeeping prunes old files from it. A user-chosen `path` is checked by `export.check_destination`: Hermes's guard first, then a built-in list that always applies, because the real guard allows `~/.hermes/plugins`, `skills`, `auth.json` and `/etc` (measured). The tool never routes around an approval.
- **Artifacts.** Hermes has no artifacts folder, so the default stays `<home>/exports`. The result also carries `artifact_path` and `media_tag`, which the Desktop's Artifacts view and the messaging gateways read, and the `next` text tells the agent to put the tag alone on its own line without backticks. A reply that wraps the tag in inline code is not delivered. Parsing was checked with the gateway's own `extract_media`; how the Desktop lists the file was not watched in a live chat.
- **Widgets by name.** A `widget` section recovers its source from the saved page's `oui-src` JSON. The name must be a plain file name inside `widgets/`.

## Why a tool, and why it stays cheap

The earlier design was a skill that told the model to run a script. A tool plugin is cheaper in context and validates server-side. The catch is discovery: plugin skills are **not** listed in the system prompt, and Hermes defers plugin tools behind Tool Search (`tool_search` / `tool_describe` / `tool_call`), so the model finds the tool through one always-visible listing line and a BM25 search over the tool's text.

How that search works (`tools/tool_search_catalog.py` in Hermes):
- It indexes the tool name, its toolset label, the **full description** and the top-level parameter names.
- It gates on the query word with the highest IDF: a tool that lacks that word is not offered at all, and a word no tool carries offers nothing. Recall therefore depends on which everyday words the description contains.
- The listing shows only the first sentence, clipped to 60 characters: `- render_widget: Draw charts, graphs, DAG/ER diagrams, maps and dashboards.`

Measured against a 178-tool catalog (Hermes's own deferred tools plus 172 names shaped like a large MCP server): the first draft of the description found 13 of 20 keyword queries; adding graph, plot, flowchart, schema, topology and KPI found 20 of 20, with no false hits on unrelated requests. Whole-sentence queries still miss when a word is absent from every tool; that is the engine's design, and a model that sees the listing line usually goes straight to `tool_describe`. Re-measure with `tools/verify_discovery.py` after any wording change. When InfraMap became a built-in, the four new infrastructure queries (`infrastructure map`, `infrastructure diagram`, `architecture diagram`, `server map`) all missed, and the set stood at 21 of 25. Adding "infrastructure and server maps, architecture diagrams" to the description (55 more characters) took it to 25 of 25, with `export_widgets` still first on all 7 export queries. The three new whole-sentence infrastructure queries still miss, like five of the ten older ones. Adding "sequence diagrams (call flow, request flow, message sequence chart, API call sequence)" for the five sequence queries kept all 28 older keyword queries and found the five new ones (33 of 33), with `export_widgets` first on all 7 export queries. The description stays at about 750 characters: `interactive`, `written` and `clickable` were cut. Cutting `visually` as well made `visualize data` miss, so it stays.

The component reference (about 3,700 tokens) is deliberately **not** in the schema: with Tool Search off the schema rides every API call. `render_widget(reference=true)` returns it on demand.

## Display modes

`preview` returns `::preview`, Hermes's built-in directive: a sandboxed `srcdoc` iframe, hidden-turn clicks, works on remote gateways. `native` writes only the `.oui` source and returns `::openui`, which the desktop half (`desktop/plugin.js`) renders inside the chat with the app's own React. Measured in headless Chrome: 20 widgets ready in about 50 ms against about 530 ms, a few MB against about 300 MB; file per widget 1–2 KB against 275–390 KB.

What `native` costs: full app authority (a desktop plugin is not sandboxed), visible user messages for clicks (the SDK's `composer.submit` has no hidden flag; core's preview uses an internal one), and local files only (it reads through `window.hermesDesktop.readFileText`, restricted to `…/widgets/<name>.oui`). The desktop half passes `hermes plugins validate`'s `desktop surface` check, which forbids `eval`, `new Function`, reaching into app markup, and any import except the SDK and React.

**Width.** The app caps a `::preview` frame at 40rem and never above 640 px, which is 560 px at the app's default 14 px font (`MAX_COLUMN_WIDTH` and `max-w-160` in its `inline-preview-directive.tsx`), so a preview widget never uses a wide window. `native` has no frame, so the widget root is `width: 100%` and takes whatever the chat column gives it. Charts, tables, the Metric row, tabs and code blocks use it. Diagrams (InfraMap, Dag, Erd, SequenceDiagram) and images keep their natural size, left aligned, and never grow. When the column is narrower than the content, diagrams shrink to 78% of their natural width and then scroll, and a Table and a CodeBlock scroll in place. Three things looked wrong in a very wide column and have native-only rules (`NATIVE_CSS` in `build/src/plugin/plugin.jsx`): a pie and its legend each took half the column and ended up far apart (the pair is capped at 720 px), a map kept its 2:1 shape so its height grew with the column (capped at 960 px, which needs the `data-hermes-openui-map` attribute that `map.jsx` now sets), and a 1 px border on an image or a map pushed it 2 px past the column. A bar chart with few bars and the options of a Choice also stretch across a wide column; they stay readable and are unchanged. A radar chart stays about 300 px wide and sits in the middle of a wide column.

**App styles.** The app draws a message inside a Tailwind Typography `.prose` block that also sets `overflow-wrap: anywhere` (read from its source and compiled stylesheet; nobody has watched it in the running app). The preview frame has none of that, so the widget root carries the class `not-prose` and `overflow-wrap: normal` (in `NATIVE_CSS`) to look like the preview. The app's sheet also has `img,picture,video,canvas,svg{user-select:none}`, which made the text of every diagram impossible to select; `NATIVE_CSS` sets `.hermes-openui-root svg{user-select:text}` (more specific, so it wins), and `tools/verify_native.py --app-css auto` checks the computed value on the sequence sample. Without them, in the harness with the app's stylesheet, a Markdown table takes the whole column instead of its own width (220 px) and a Table or a Markdown block with a table is about 50 px taller.

To see the layout without the app, run `python3 tools/verify_native.py --png native.png` (`--theme light` for the light tokens, which are approximations of the app's). It draws the real `desktop/plugin.js` against a stub SDK, in chat columns of 360, 640, 1000, 1800 and 2400 px on one page, in one headless Chrome launch, and prints each widget's size and scrollers. `--app-css auto` also inlines the compiled stylesheet of an installed Hermes Desktop and wraps every widget in the classes of the app's message elements, so `.prose` and `overflow-wrap` rules reach it; the wrapper is a copy of those classes, not the app's React tree. It still cannot show what Hermes Desktop does: the width and padding of the real message column, any rule the app applies to a transcript directive, and the app's theme tokens are assumed. `OPENUI_TEST_CHROME=1 python3 -m unittest tests.test_native_layout` runs the same checks as a test.

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

Also verified for packs and export: a pack and an export tested through Hermes's own `handle_function_call` in an installed Git copy, with the pack linked through `config.yaml`; the real `hermes openui` CLI; the export destination policy against the real `agent.file_safety`; exported pages from `file://` in headless Chrome with no console errors and no requests; every commit on the branch passing the suite on its own.

Not verified: how the desktop app *renders* a widget (only a headless-Chrome harness was used); the **Capabilities → Plugins** Desktop switch, and the app's automatic copy of `desktop/plugin.js` into `desktop-plugins/` (both come from Hermes's docs; neither was seen in the app); Linux and Windows; any model other than the one used while building; exported pages in Safari or Firefox; the print layout of an export; a six-zone InfraMap's scrollbar in the desktop app; custom packs under native mode (refused by design, so never rendered).

## Ideas

- A hidden-turn option for plugins (`host.composer.submit(sessionId, text, { hidden: true })`) would remove the main `native` trade-off. It needs an SDK change in Hermes.
- Pruning old widgets (they are never deleted automatically, because old messages still point at them).
- A tool-side `list_components` or per-component reference to shrink the 3,700-token first use.
