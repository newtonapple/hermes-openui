# hermes-openui

Ask your Hermes agent to **draw**: dashboards, charts, DAG and ER diagrams, maps, tables. They appear as interactive widgets inside the Hermes desktop chat. Everything runs locally: no network, no accounts, no telemetry.

<table>
<tr>
<td><img src="docs/images/hero-dashboard.png" width="360" alt="A status dashboard widget"></td>
<td><img src="docs/images/hero-topology.png" width="360" alt="A network topology DAG widget"></td>
</tr>
</table>

> "Draw a DAG of our nightly build." &nbsp;·&nbsp; "Show GPU, queue and error rate as a dashboard with a line chart." &nbsp;·&nbsp; "Make an ER diagram of users, orders and order_items."

## What you get

- **One tool, `render_widget`.** The agent writes a few lines of *OpenUI Lang* (a compact component language); the plugin validates it, saves a widget, and the agent puts one line in its reply. The widget appears in the chat when the turn finishes.
- **21 components** (28 with helpers): metric tiles, tables, tabs, cards, line / area / pie / radar / bar charts, DAG pipelines, ER diagrams, offline maps, code, markdown, FAQs, and clickable choices. See the [component gallery](docs/ui-components/README.md) for a screenshot and example of each.
- **Plain English works.** You do not name the tool. Hermes's Tool Search keeps it out of the model's context until a request needs it.
- **Cheap on context.** About 20 tokens always on; about 3,000 tokens the first time it is used (the component reference); a few hundred per widget.
- **Two display modes.** `preview` (default) works out of the box. `native` renders in the app itself and makes widgets tiny, at the price of running with full app authority. See [Display modes](#display-modes).
- **Interactive.** Buttons and choices send their text back to the agent as your next turn.

## Gallery

<table>
<tr>
<td valign="top" width="33%"><a href="docs/ui-components/Dag.md"><img src="docs/ui-components/images/dag-pipeline.png" width="270" alt="A CI run with done, failed, running, skipped and pending steps"></a><br><b>Pipeline</b> &middot; <a href="docs/ui-components/Dag.md">Dag</a><br><sub>A CI run with done, failed, running, skipped and pending steps</sub></td>
<td valign="top" width="33%"><a href="docs/ui-components/Erd.md"><img src="docs/ui-components/images/erd-schema.png" width="270" alt="Tables, keys and relations from one short definition"></a><br><b>Schema</b> &middot; <a href="docs/ui-components/Erd.md">Erd</a><br><sub>Tables, keys and relations from one short definition</sub></td>
<td valign="top" width="33%"><a href="docs/ui-components/GeoMap.md"><img src="docs/ui-components/images/geo-map-world.png" width="270" alt="Pins and links on an offline world map"></a><br><b>Map</b> &middot; <a href="docs/ui-components/GeoMap.md">GeoMap</a><br><sub>Pins and links on an offline world map</sub></td>
</tr>
<tr>
<td valign="top" width="33%"><a href="docs/ui-components/AreaChart.md"><img src="docs/ui-components/images/area-chart-stacked.png" width="270" alt="Tokens per minute by model, stacked"></a><br><b>Chart</b> &middot; <a href="docs/ui-components/AreaChart.md">AreaChart</a><br><sub>Tokens per minute by model, stacked</sub></td>
<td valign="top" width="33%"><a href="docs/ui-components/CodeBlock.md"><img src="docs/ui-components/images/code-block-python.png" width="270" alt="Highlighted code with a Copy button"></a><br><b>Code</b> &middot; <a href="docs/ui-components/CodeBlock.md">CodeBlock</a><br><sub>Highlighted code with a Copy button</sub></td>
<td valign="top" width="33%"><a href="docs/ui-components/Faq.md"><img src="docs/ui-components/images/faq-first-open.png" width="270" alt="Expandable answers with lists and tables inside"></a><br><b>Answers</b> &middot; <a href="docs/ui-components/Faq.md">Faq</a><br><sub>Expandable answers with lists and tables inside</sub></td>
</tr>
</table>

Each picture is a real render of the example code on that component's page, with sample data. All 21 components, with the code for every picture, are in the [component gallery](docs/ui-components/README.md).

## Requirements

| | |
|---|---|
| Hermes Agent | 0.22.5 or newer. The manifest sets `requires_hermes: ">=0.22.5"`, so an older Hermes will not load the plugin. 0.22.5 is the only version it was tested on. Widgets render in the **desktop app** only; the CLI, TUI and messaging platforms see a file path. |
| Python | None to install. The plugin runs inside Hermes's own interpreter (Hermes itself needs 3.11+) and imports only the standard library. |
| Node.js | Optional, 18 or newer. With it, source is checked by the real OpenUI parser; without it, a built-in structural check still catches the common mistakes. |

## Install

### On this machine, from a checkout (works today)

```sh
git clone https://github.com/newtonapple/hermes-openui.git      # or copy the folder
cd hermes-openui
sh scripts/install.sh                          # copies the runtime files into ~/.hermes/plugins/hermes-openui and enables it
```

Then start a **new** chat (or restart the Hermes gateway: `hermes gateway restart`) and ask for a chart. The installer needs only `sh` and `cp`. Options: `--home DIR` installs into another Hermes home (a named profile lives under `~/.hermes/profiles/<name>`), `--no-enable` only copies. An existing copy is moved aside, never deleted.

`hermes plugins install` does not accept a filesystem path (it reads one as GitHub shorthand), which is why the script exists.

### With Hermes's installer, from Git

This installs the default branch:

```sh
hermes plugins install newtonapple/hermes-openui --enable
```

or in the desktop app: **Capabilities → Plugins → Install from Git**. To install a specific release, see [Versioning](#versioning).

Hermes clones the whole repository, about 10 MB with the docs, tests and build sources. `scripts/install.sh` copies only the 1.8 MB the plugin runs on. Hermes also prints a warning that the source is not from its catalog. That is expected for any plugin installed from a Git URL.

### On another computer

Repeat either route there. The plugin keeps no state outside `$HERMES_HOME/widgets/` (generated widgets). Keep this folder in Git, rsync or a synced drive and run `sh scripts/install.sh` on each machine. If you sync it through iCloud Drive, do not run `npm ci` inside the synced folder (see [Development](#development)).

### Into a profile

Each Hermes profile has its own home (`~/.hermes/profiles/<name>`), its own `plugins/` folder and its own enabled list in `config.yaml`. Installing the plugin in one profile does not add it to another, so repeat these steps for every profile that should have it.

```sh
hermes profile list                                                  # names and paths
sh scripts/install.sh --home ~/.hermes/profiles/<name>              # copy the files and enable it in that profile
hermes -p <name> plugins list | grep hermes-openui                  # status: enabled
```

If that profile has a gateway running, restart it from a separate shell (not from inside a chat that the gateway runs): `hermes -p <name> gateway restart`. The desktop app picks the plugin up in a **new** chat of that profile.

### Check that it worked

```sh
hermes plugins list | grep hermes-openui      # status: enabled
hermes plugins doctor ~/.hermes/plugins/hermes-openui
```

In a new desktop chat: *"Draw a bar chart of 3, 5 and 2 for a, b and c."* A widget should appear.

## Use it

You do not call the tool. Ask for something visual:

- *Draw a DAG of extract → clean → train → evaluate → publish, with train running.*
- *Put Berlin and Tokyo on a map and link them.*
- *Show these four numbers as KPI tiles.*
- *Ask me which sample to build next as clickable choices.*

If the agent answers in text instead, say **"as an inline widget"** or name the tool: *"use render_widget"*. Other diagram skills (Excalidraw, architecture diagrams) compete for words like "diagram"; being explicit settles it.

How it works behind the scenes, in order: the agent calls `render_widget(reference=true)` once to get the exact component signatures, then `render_widget(source=...)`. The tool returns a directive such as `::preview{file="…/widgets/gpu-status-1a2b3c.html"}`, which the agent puts alone on its own line. Details are in [docs/development.md](docs/development.md).

### Display modes

| | `preview` (default) | `native` |
|---|---|---|
| How it shows | The app's built-in `::preview`: a sandboxed frame per widget | This plugin's desktop half renders the widget in the chat itself, via `::openui` |
| File per widget | 275–390 KB self-contained HTML | 1–2 KB of source |
| Cost to show 20 widgets | about 530 ms and roughly 300 MB of extra memory | about 50 ms and about 4 MB, one shared runtime |
| Isolation | Sandboxed (opaque-origin iframe) | **None**: runs with the app's full authority |
| Buttons | Send a **hidden** turn to the agent | Type a **visible** user message (the plugin SDK cannot send hidden ones) |
| Remote gateways | Works | Local files only |
| Setup | none | enable the desktop half **and** set `mode` |

To use `native`: open **Capabilities → Plugins**, switch **Desktop** on for *OpenUI widgets* (review it first: it is a desktop plugin with full app authority), then set `mode: native` in the plugin's settings, or in `config.yaml`:

```yaml
plugins:
  entries:
    hermes-openui:
      settings:
        mode: native
```

Installing already created a `plugins:` block in that file (it holds `enabled:`). Add `entries:` **under it**. A second top-level `plugins:` key is a duplicate and is not valid YAML.

If the **Desktop** switch does not appear after a manual copy, copy `desktop/plugin.js` to `~/.hermes/desktop-plugins/hermes-openui/plugin.js` and use **⌘K → Reload desktop plugins**. (Both the switch and this fallback are untested in the app; the plugin file itself is verified against the app's loader.)

Timings and memory were measured in headless Chrome, not in the desktop app, so treat them as indicative. In `native` mode the directive shows as a plain line wherever the desktop half is off; switch back with `mode: preview`.

## Components

Every component has a page with its signature, arguments, rendered examples and pitfalls: **[docs/ui-components](docs/ui-components/README.md)**. Layout and data: Stack, Text, Card, Metric, Table, Tabs, Callout, Button. Charts: LineChart, AreaChart, PieChart, RadarChart, BarChart. Diagrams: Dag, Erd, GeoMap. Rich content: Markdown, CodeBlock, Image, Faq, Choice.

## Configuration

| Setting | Values | Default | Meaning |
|---|---|---|---|
| `mode` | `preview`, `native` | `preview` | How widgets are shown. Read on every call, so a change applies without a restart. |

Settings live under `plugins.entries.hermes-openui.settings` and appear on the plugin's page in the desktop app.

## Context cost

Measured, using Hermes's own estimate of 4 characters per token.

| What | When | Tokens |
|---|---|---|
| Tool listing line | every chat, with Tool Search on (the default) | about 20 |
| Tool schema (1.2 KB) | every API call **only if** Tool Search is off | about 310 |
| Component reference | the first use in a chat | about 2,800 |
| Your widget source | each widget, stays in the history | about 250–600 |
| Tool result | each widget | about 100 |

The bundled skill (`hermes-openui:openui-render`, about 640 tokens) is loaded on demand only.

## Security and privacy

- **No network, ever.** The browser runtime is embedded in each page; nothing is fetched. A test fails the build if network code appears in any shipped file.
- **No telemetry.** OpenUI's libraries contain opt-in telemetry code; none of it is in the shipped bundles, and the build runs with its opt-outs and `--ignore-scripts`.
- **Writes only to `$HERMES_HOME/widgets/`**, with a generated suffix on every name so an old message's widget is never overwritten. Nothing is cleaned up automatically; delete old files when you like.
- **Images** are read only from absolute paths with an image extension, at most 100 KB each, and embedded in the widget.
- **`preview` widgets run sandboxed.** In `native` mode the desktop half has full app authority; it only reads `…/widgets/<name>.oui` files and renders them with a declarative parser (no source is ever evaluated as code).
- Third-party code in the bundles is listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); all permissive.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The agent never uses it | The plugin is not enabled or the chat predates it: `hermes plugins list`, then start a **new** chat. Or ask for it explicitly: "as an inline widget". |
| `::preview{…}` shows as text | You are not in the desktop app, or the file was deleted. |
| `::openui{…}` shows as text | `mode` is `native` but the desktop half is off. Enable it, or set `mode: preview`. |
| A blank widget | The page exceeded the app's 512 KiB read limit. The tool refuses pages over 480 KB, so this means the file was edited or truncated by hand. |
| "Widget is missing component(s): X" | A component's runtime pack was not embedded. Report it; the tool normally picks packs from the source. |
| The tool says errors and writes nothing | Read `errors`, fix the source, call again. They name the line or variable. |
| "checked: structural" instead of "node" | Node is not installed, so only the built-in checks ran. Install Node 18+ for full validation. |
| `hermes plugins install` of a local path fails | Expected: use `sh scripts/install.sh`. |

## Update, reinstall and uninstall

Add `-p <name>` to the `hermes` commands (and `--home ~/.hermes/profiles/<name>` to `install.sh`) to act on a profile instead of the default home.

| Goal | Command | What happens |
|---|---|---|
| Update or reinstall in place | `git pull && sh scripts/install.sh` | The files are replaced. It stays enabled and keeps your settings (such as `mode`). The old copy moves to `<home>/cache/hermes-openui-previous-<time>`; delete it when you are happy. |
| Update a Git-installed copy | `hermes plugins update hermes-openui` | |
| Pause it | `hermes plugins disable hermes-openui` | The files stay. Re-run with `enable` to resume. |
| Uninstall | `hermes plugins remove hermes-openui` | Deletes the plugin folder, takes it out of the enabled list and clears its settings. The rest of `config.yaml` is untouched. |
| Clean reinstall | `hermes plugins remove hermes-openui`, then `sh scripts/install.sh` | A fresh copy with default settings (`mode` back to `preview`). |

Things to know:

- `install.sh` **enables** the plugin every time it runs, including one you disabled on purpose. Use `sh scripts/install.sh --no-enable` to leave the state alone.
- `remove` does **not** delete the generated widgets in `<home>/widgets/`, the `previous` copies in `<home>/cache/`, or a manual copy of the desktop file at `~/.hermes/desktop-plugins/hermes-openui/`. Delete those yourself if you want them gone. Old chat messages point at the widget files: delete a file and that message's widget no longer shows.
- Widgets already in a chat keep working after an uninstall, because each is a self-contained file.

## Versioning

The version is in `plugin.yaml`. Each release has an entry in [CHANGELOG.md](CHANGELOG.md) and a Git tag named `vX.Y.Z`. The numbers follow [Semantic Versioning](https://semver.org/). Before 1.0.0, a minor release can change behavior, and the changelog says when it does.

| Bump | When |
|---|---|
| Major | A component or an argument is removed or renamed, the `render_widget` parameters change, or a setting is renamed. Widgets written for the old version stop working. |
| Minor | A new component, argument, setting or display mode. Existing widgets keep working. |
| Patch | Bug fixes, documentation, or rebuilt assets with no change in behavior. |

`hermes plugins install` follows the default branch. It does not accept a tag for `--ref`, only a full 40-character commit SHA. To install an exact release, look up the commit its tag points to and pin that:

```sh
SHA=$(git ls-remote https://github.com/newtonapple/hermes-openui 'refs/tags/v0.1.0^{}' | cut -f1)
hermes plugins install newtonapple/hermes-openui --ref "$SHA" --enable
```

## Development

```sh
python3 -m unittest discover -s tests        # standard library only
hermes plugins validate .                    # Hermes's own plugin validator (the catalog CI gate)
cd build && npm ci && npm run build          # regenerate assets/ and desktop/plugin.js from source
python3 tools/check_docs.py                  # verify docs/ui-components
```

The generated files (`assets/`, `desktop/plugin.js`, `THIRD_PARTY_NOTICES.md`) are committed so that installing needs no build; rebuilding from the lockfile reproduces the same bytes (the manifest records a SHA-256 of each uncompressed bundle). Agents working in this repository should read [AGENTS.md](AGENTS.md); the design notes and the pitfalls found along the way are in [docs/development.md](docs/development.md).

## License

MIT, see [LICENSE](LICENSE). Bundled third-party code: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). OpenUI is by Thesys.
