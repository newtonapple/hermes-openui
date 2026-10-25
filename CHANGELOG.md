# Changelog

All notable changes to hermes-openui are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0.0 a minor release can break things, and its entry says so.

## [Unreleased]

### Changed

- The README and AGENTS.md now recommend `hermes plugins install newtonapple/hermes-openui --enable`. They describe `scripts/install.sh` as the alternative for offline use and uncommitted changes, and compare the two. Only a Git install records its source, so only a Git install works with `hermes plugins update`.

### Added

- A "Multiple profiles" section. Hermes keeps plugin files and the enabled list per profile, so the plugin is installed once per profile.

### Fixed

- The README told users to copy `desktop/plugin.js` into `~/.hermes/desktop-plugins/` by hand. The app copies it itself, and a hand-placed file is never refreshed, so it goes stale. If you followed that advice, delete `~/.hermes/desktop-plugins/hermes-openui/`.
- The README, AGENTS.md and the installer said Hermes cannot install from a local path. A `file://` URL works. A bare path still fails.

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

[Unreleased]: https://github.com/newtonapple/hermes-openui/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/newtonapple/hermes-openui/releases/tag/v0.1.0
