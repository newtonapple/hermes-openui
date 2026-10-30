# Changelog

All notable changes to hermes-openui are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0.0 a minor release can break things, and its entry says so.

## [Unreleased]

### Added

- **Tooltip**, a new built-in component: a hover tooltip with an optional click-to-open detail panel for one element of a Dag, Erd, InfraMap or SequenceDiagram. Each of the four takes it in a new last argument, `tooltips`. `Tooltip(target, hint, detail, code, language, tone, link, linkLabel)`: an element with a tooltip gets a small dot in the tone colour (`info`, `good`, `warn`, `bad`), a pointer cursor and a Tab stop; hovering it or tabbing to it shows the hint, and a click, Enter or Space opens one panel under the diagram with the detail text, the code (highlighted, with a Copy button) and a link line. A second click, the close button, Escape or the diagram background closes it; an Escape that closes a panel is marked handled, so in the desktop app it does not also stop a running turn, and an Escape with no panel open is left alone. A target is a node id (Dag), an entity name or `entity.column` (Erd), a node id, `zone:<name>` or `<from>><to>` (InfraMap), or a participant id or a `SeqMessage` id (SequenceDiagram; a message without an id cannot have a tooltip). The validator rejects an unknown, duplicate or ambiguous target, an item that is not a Tooltip, a Tooltip that is not in the `tooltips` of a diagram, a tooltip with nothing to show, more than 60 per diagram, and a `hint` over 140 characters, a `detail` over 800, a `code` over 2,000 characters or 40 lines, a `language` over 20, a `linkLabel` over 60 or a `link` over 300. The one interaction module is `build/src/components/tooltips.jsx`; the rules and checks are pure modules that Node tests run without a bundler. The tooltip stays inside the diagram (it never makes the page taller) and does not cover the element: beside it, it wraps to the room it has, and in a diagram too short for the text it is cut with an ellipsis. In preview mode the panel opens below the diagram and the frame stops at 1,200 px, so keep a diagram with tooltips under about 800 px. It works in preview and native mode with the same code. The page is [docs/ui-components/Tooltip.md](docs/ui-components/Tooltip.md), with three examples and a Tooltips section on each diagram page.
- **Tooltips on Table, Metric, BarChart, GeoMap and Image.** Each takes the same `Tooltip` items in a new last argument, `tooltips`, with the same hover and focus tooltip, one click-to-open panel under the component, link rules, limits and keyboard behavior as the four diagrams: `Table(columns, rows, tooltips)`, `Metric(label, value, delta, tone, tooltips)`, `BarChart(labels, values, title, unit, tooltips)`, `GeoMap(points, links, title, tooltips)` and `Image(src, alt, caption, tooltips)`. A target is `row:3`, `col:status` or `cell:3.status` for a Table (a row, a header, a cell; the first dot splits a cell target), a Metric's own label, a bar's label, a pin's label or `A>B` for a GeoMap link (a thin dashed line with a 12 px invisible hit path), and the word `image` for an Image. The validator rejects an unknown, duplicate or ambiguous target (two columns with one header, two bars or pins with one label, two links joining one pair), names it, lists up to five valid ones and says which forms exist, and a second tooltip on a Metric or an Image. The free-standing Tooltip error now lists the nine components that take `tooltips`; Button, Choice, Stack, Card, Tabs, Text, Markdown, Callout, Faq, CodeBlock and the library charts still do not. A table row stays a real `<tr>` and keeps its own role, like a header and a cell (they only become focusable), so a screen reader still reads a table; the table keeps scrolling sideways, and a tooltip for a cell scrolled out of view waits until it is back. In native mode the text of an element with a tooltip can be selected and copied. An open Metric panel takes a line of its own below the tiles of a row that wraps, so the other tiles keep their place and height, and the hint of a Metric is drawn below the tile. The validator also says what to do when a Tooltip list is in the wrong place: it names the nine components for a component that takes no tooltips or an unreachable Tooltip, and says to write `null` for each skipped optional argument before `tooltips`, with an example for the component. Each of the five pages has a Tooltips section with an example and a screenshot, and `Tooltip.md` has a table of where tooltips work and one note about the panel height for all components.
- **Links in a tooltip** are `http://` or `https://` only (lowercase, with a host, no `user:password@`, no spaces, no invisible character, only ASCII in the host and the port, a port from 1 to 65535, so the address shown is the address the app opens); the validator rejects `javascript:`, `data:`, `file:`, `mailto:`, `//host` and everything else, and the renderer checks again at click time. The full address is always shown as text, with a Copy button. In native mode, when the app offers `window.hermesDesktop.openExternal`, a click on it calls that once; the preview frame and exported pages never do, because the sandbox blocks navigation. The `onAction` rule that ignores `open_url` is unchanged.
- `tools/shoot.py --steps` drives a page with real mouse and keyboard events (move, click, Tab, Enter, Escape) from the DevTools protocol, records values, and takes extra screenshots, in both modes. The page height is measured again after the steps, so an opened panel is part of the screenshot.

### Changed

- **`Tooltip` is now a reserved component name.** A custom pack that defines a component with that name is skipped with the usual message.
- The component reference the agent loads on first use grows from about 3,700 to 4,750 tokens (the `Tooltip` line and the new `tooltips` argument of nine components). The `render_widget` description is unchanged, and the discovery check still finds 33 of 33 keyword queries.
- The `openui-render` skill has three lines about tooltips. Its size limit goes from 4,500 to 5,000 characters (it was at 4,376), about 1,250 tokens.
- The tooltip interaction module and the code highlighter are in the core once, so the diagrams, infra, sequence and text packs no longer carry a copy. The core grows by about 7.8 KB gzipped (205.7 to 213.5 KB), the diagrams, infra and sequence packs shrink by about 5.8 KB each and the text pack by about 1.5 KB, the map pack grows by about 0.6 KB, and `desktop/plugin.js` grows by about 6.7 KB (2.7 KB gzipped). A page with no pack weighs about 8 KB more, a page with one diagram pack about 2 KB more, and a page with two or more of them less than before. The packs take the module from the core through internal entries of `window.__HM.mods`, next to the shared `Tooltip` definition; the pack API (`api: 1`) is unchanged.

## [0.3.0] - 2026-10-29

### Added

- **SequenceDiagram**, a built-in component in a new `sequence` pack (with `SeqParticipant`, `SeqMessage`, `SeqNote` and `SeqGroup`). Participants are columns with dashed lifelines; messages are numbered arrows from top to bottom, in three styles (`sync`, `async`, `return`), with self-calls, activation bars worked out from the messages, notes over one participant or spanning several, and `alt`, `opt`, `loop` and `par` groups that nest and can have a second branch. It keeps its natural size, left aligned, and shrinks to 78% and then scrolls like the other diagrams. The layout is a pure function (`build/src/components/sequence-layout.js`) that Node tests run without a browser. The validator rejects an unknown or duplicate participant id, a duplicate message id, more than 10 participants or 100 steps, groups nested deeper than 3, and a step or a participant that is not a Seq item. A user pack that reuses one of the five names is skipped, like the `Infra*` names. The page is [docs/ui-components/SequenceDiagram.md](docs/ui-components/SequenceDiagram.md), with three examples.
- The native layout check (`tools/verify_native.py`) draws a sequence diagram too, and checks that it stays left aligned and gets its own scroller in a 360 px column. With `--app-css` it also checks that the diagram's text can be selected.

### Changed

- In native mode the text of every diagram (Dag, Erd, InfraMap, SequenceDiagram) can now be selected and copied: the app's own `svg{user-select:none}` rule is overridden by one line in `NATIVE_CSS`.
- The `render_widget` description now says "sequence diagrams (call flow, request flow, message sequence chart, API call sequence)". On the discovery check, the five new keyword queries (`sequence diagram`, `call flow`, `request flow`, `message sequence chart`, `API call sequence`) and the 28 older ones all rank the tool in the top 5, 33 of 33, and `export_widgets` still ranks first on all 7 export queries. The description stays at about 750 characters: a few filler words (`interactive`, `written`, `clickable`) were cut to make room.
- The component reference the agent loads on first use grows from about 3,100 to 3,700 tokens (the five SequenceDiagram lines). Every chat that uses `render_widget` pays it once.
- The `openui-render` skill has a row and a rule line for sequences of calls. Its size limit goes from 4,000 to 4,500 characters (it was at 3,995), about 1,100 tokens.

## [0.2.2] - 2026-10-28

### Changed

- **Native mode fills the chat column.** The desktop half capped every widget at 640 px, a limit copied from the preview frame. The cap is gone: the widget root is `width: 100%`, so charts, tables, the Metric row, tabs and code blocks use the whole column. InfraMap, Dag, Erd and images keep their natural size, left aligned. A column narrower than the content still shrinks a diagram to 78% and then scrolls it, and a Table and a CodeBlock scroll in place. Preview mode is unchanged: the app caps a preview frame at 40rem and never above 640 px (560 px at its default 14 px font), and a page cannot change that.
- In native mode a pie chart and its legend sit together (at most 720 px) instead of taking half a wide column each, and a map stops at 960 px instead of growing as tall as it is wide (1,200 px high in a 2,400 px column). The map pack gets a `data-hermes-openui-map` attribute for this. The preview render of the map at 640 px gives identical PNG bytes before and after (same sha256); the map pack's JavaScript differs by that one attribute plus the minifier's renames of short identifiers.
- The hint in the component reference (`render_widget(reference=true)`) no longer says the widget renders in a ~640px chat column; it says to design for a column of up to 640px and that native mode may be wider.

### Fixed

- In native mode an image or a map with its 1 px border no longer ends 2 px past the edge of a narrow column.
- In native mode the widget root has the class `not-prose` and `overflow-wrap: normal`. The app draws a message inside a Tailwind Typography `.prose` block that sets `overflow-wrap: anywhere`, so without them a Markdown table takes the whole column instead of its own width, and a Table or a Markdown block with a table is about 50 px taller (harness numbers). This is derived from the app's source and compiled stylesheet and checked in the harness with the stylesheet inlined; nobody has seen it in the running app.
- The preview docs said the app's cap is 640 px; it is 40rem and never above 640 px, which is 560 px at the app's default 14 px font.

### Added

- `tools/verify_native.py`, with `build/tests/native-harness.mjs`: draws the real `desktop/plugin.js` against a stub SDK in chat columns of 360, 640, 1000, 1800 and 2400 px, in one headless Chrome launch, and measures every widget (width, height, scrollers, overflow). `tests/test_native_layout.py` runs it when `OPENUI_TEST_CHROME=1`. It shows layout in plain Chrome, not in Hermes Desktop. `--app-css auto` also inlines the stylesheet of an installed Hermes Desktop and wraps each widget in the classes of the app's message elements (a copy, not the app's React tree); `--theme light` uses light stub tokens (approximations of the app's); the scroller check is evaluated at the 360 px column only.
- Tests that need no Chrome: every `max-width` in `build/src/plugin/plugin.jsx` is one of the two native-only limits, there is no 640 there, and the built `desktop/plugin.js` holds exactly the `NATIVE_CSS` rules of the source. The opt-in Chrome test skips when Chrome is missing. `AGENTS.md` says to run it after a change to `build/src/plugin/` or a component.

## [0.2.1] - 2026-10-28

### Added

- **A bundled skill, `hermes-openui:custom-components`.** It teaches an agent to write a component pack, check it, link it in the `components` setting (after asking the user), fetch the reference again and draw a sample. It has one complete template, and the tests load, validate and render that template (the pack loader, the Node validator and a Chrome render), so a change that breaks it fails the build. It also has a short path for making a component built in. A plugin skill is not in the prompt's skill index, so a one-line pointer to it now sits in the `render_widget(reference=true)` result, in the first "Unknown component" error and in the `openui-render` skill, which no longer points to a docs path that the installer does not copy.

### Changed

- The `render_widget` description now says "custom components". With three new keyword queries (`custom component`, `new component`, `add a component`), the discovery check found 27 of 28 before the change (`custom component` missed) and 28 of 28 after it. `export_widgets` still ranks first on all 7 export queries and there are no false positives. The description grows by 19 characters, which costs about 5 tokens on every API call when Tool Search is off. The new sentence query `make me a new component` still misses, like 8 of the 13 older ones.

## [0.2.0] - 2026-10-27

### Changed

- `scripts/install.sh` copies every top-level `.py` file and the `examples` folder. A fixed file list would have left the new modules behind, and the installed plugin would have failed to import.
- `assets/validate.cjs` is rebuilt so it accepts `--pack`. The browser core and the built-in packs are byte-identical to before.
- The README and AGENTS.md now recommend `hermes plugins install newtonapple/hermes-openui --enable`. They describe `scripts/install.sh` as the alternative for offline use and uncommitted changes, and compare the two. Only a Git install records its source, so only a Git install works with `hermes plugins update`.
- The component reference the agent loads on first use grows from about 2,800 to 3,100 tokens. That is the four InfraMap lines, and every chat that uses `render_widget` pays it once.
- The `render_widget` description names infrastructure and server maps and architecture diagrams. Before, a search for `infrastructure map` or `architecture diagram` did not find the tool. On the discovery check, keyword recall went from 21 of 25 to 25 of 25, and `export_widgets` still ranks first on all 7 export queries. The description grows by 55 characters, which costs about 14 tokens on every API call when Tool Search is off.
- The bundled skill picks `InfraMap` for infrastructure, says to link nodes by id and to leave `status` out unless the user or a tool gave it, and no longer sends network diagrams to `Dag`. It tells the agent to reply to an export with the result's `media_tag`.

### Added

- **Custom component packs.** Link a JavaScript file, or a folder of them, in the new `components` setting and the agent can use the components it adds, in `render_widget` and `export_widgets`. A pack's first comment is a JSON header, so Hermes learns its components without running it. A page embeds a pack only when the source uses one of its components. Preview mode only: native mode refuses them. See `docs/custom-components.md`.
- **InfraMap**, built in. `InfraMap`, `InfraZone`, `InfraNode` and `InfraLink` draw zones of nodes joined by labeled links, with an icon for each kind of node, status dots and a legend. A link that names a label instead of a node id is rejected, and the message gives the right id. It is an optional `infra` pack, so a page carries it (about 9 KB) only when the source calls one of its components. See `docs/ui-components/InfraMap.md`.
- **`export_widgets`**, a second tool that saves widgets already shown in the chat, new OpenUI Lang, or both as one standalone offline HTML page. It writes to the path the user names, or to `exports/` in the profile's Hermes home, and refuses protected places. New `export_dir` setting. See `docs/exporting.md`.
- `export_widgets` results carry `artifact_path` and `media_tag` (`MEDIA:` plus the path), and the reply instruction tells the agent to put the tag alone on its own line, with no backticks. The Desktop app and the messaging gateways read these to present the file. A refused export carries neither. Checked against Hermes's source and its own `extract_media`, not in a live chat.
- `hermes openui components list` and `check`, `hermes openui widgets`, and `hermes openui export`.
- `tools/shoot.py --pack` links a pack when taking a screenshot. `--html`, `--eval` and `--before` load a saved page from `file://`.
- `tools/verify_discovery.py` measures both tools together.
- A "Multiple profiles" section. Hermes keeps plugin files and the enabled list per profile, so the plugin is installed once per profile.

### Fixed

- The desktop-loader test failed on a fresh clone after `npm ci`, because the check wrote into `build/dist`, which only a build creates. The check now creates the folder.
- The README told users to copy `desktop/plugin.js` into `~/.hermes/desktop-plugins/` by hand. The app copies it itself, and a hand-placed file is never refreshed, so it goes stale. If you followed that advice, delete `~/.hermes/desktop-plugins/hermes-openui/`.
- The README, AGENTS.md and the installer said Hermes cannot install from a local path. A `file://` URL works. A bare path still fails.

### Known issues

- Without Node installed, a source that uses custom components gets no type check and no `validate` hook, and the browser draws a bad argument as if it were missing, with no error.
- The runtime's accent fallback `AccentColor` is not recognized by Chrome 145, so outside Hermes a Button loses its border. Exported pages define their own accent. The runtime itself is unchanged.
- An InfraMap with more than about four zones scrolls sideways inside the chat column. In a six-zone test the sixth zone was cut off with no visible cue, and the screenshot tool hides scrollbars, so the desktop app's behavior is unchecked.
- `hermes plugins validate` warns (catalog rule 9, not a failure) that `export.py` imports Hermes's private `agent.file_safety` to reuse its write guard. The import is guarded: if the module moves, the plugin falls back to its own protected-places list. A catalog submission would need a documented API for this, or a decision to drop the import.
- Exported pages were checked in Chrome only. Safari, Firefox and the print layout were not tried.

## [0.1.0] - 2026-10-24

First release.

### Added

- The `render_widget` tool. The model sends OpenUI Lang source. The plugin checks it, writes a widget file under `$HERMES_HOME/widgets/` and returns a `::preview` line for the reply. `render_widget(reference=true)` returns the component reference, which keeps it out of the tool schema.
- 21 components, 28 with their helpers: Stack, Text, Card, Metric, Table, Tabs, Callout, Button, Image, Markdown, CodeBlock, Faq, Choice, LineChart, AreaChart, BarChart, PieChart, RadarChart, Dag, Erd and GeoMap.
- Two display modes, chosen with the `mode` setting. `preview` is the default and uses the app's built-in `::preview`. `native` uses `::openui`, which the plugin's own desktop half renders. That half is off until you enable it and it runs with full app authority.
- A browser runtime split into a core and four packs: charts, map, diagrams and text. A widget embeds only the packs it uses, so a page is about 275 KB without charts and about 390 KB with every pack.
- An offline world map for GeoMap. It needs no tiles and no network.
- The bundled skill `hermes-openui:openui-render`, with layout patterns and pitfalls. Hermes loads it on demand.
- Installing from GitHub with `hermes plugins install newtonapple/hermes-openui --enable`.
- `scripts/install.sh`. It copies the runtime files into a Hermes home and enables the plugin. `--home` targets a profile and `--no-enable` leaves the enabled state alone. An existing copy moves to `<home>/cache/` instead of being deleted.
- `requires_hermes: ">=0.22.5"` in `plugin.yaml`. 0.22.5 is the only Hermes version this release was tested on.
- Docs: a README, AGENTS.md, development notes, and a page for every component with 59 example programs and a screenshot of each.
- 64 unit tests. `tools/check_docs.py` checks the docs, and `tools/verify_runtime.py` and `tools/verify_discovery.py` check the plugin against a real Hermes install.
- An MIT license and a list of the bundled third-party packages in `THIRD_PARTY_NOTICES.md`.

### Known issues

- The `donut` variant of PieChart renders as a thin ring over a grey disc.
- The optional second argument of `@ToAssistant` is ignored. Only the message text reaches the agent.
- Choice accepts more than six options, although the reference asks for two to six.
- Card and Metric have a minimum size along the stack's main axis. A lone one directly in a column is tall and mostly empty. Wrapping it in a one-item row avoids that.
- The app refuses a button message over 500 characters or sent less than a second after the previous click. The widget shows nothing when that happens.

### Not verified

- How the desktop app draws a widget. Rendering was checked in headless Chrome only.
- Clicks and the Copy button inside the app's widget frame.
- The Desktop switch in Capabilities, Plugins for a manually copied plugin.
- Linux and Windows.

[Unreleased]: https://github.com/newtonapple/hermes-openui/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/newtonapple/hermes-openui/releases/tag/v0.3.0
[0.2.2]: https://github.com/newtonapple/hermes-openui/releases/tag/v0.2.2
[0.2.1]: https://github.com/newtonapple/hermes-openui/releases/tag/v0.2.1
[0.2.0]: https://github.com/newtonapple/hermes-openui/releases/tag/v0.2.0
[0.1.0]: https://github.com/newtonapple/hermes-openui/releases/tag/v0.1.0
