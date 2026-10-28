# Export to HTML

`export_widgets` saves widgets, or a whole report, as **one standalone HTML file**. The file opens in any browser, works offline, and keeps the charts, tables and diagrams interactive.

![An exported report in the light theme: a platform map, three metric tiles, a line chart and notes](images/export-report-light.png)

## Ask for it in chat

You do not name the tool. Ask in plain words, at any point in a conversation:

- *Export that dashboard as an HTML page.*
- *Save the last three widgets as one report.*
- *Put the platform map, a latency chart and these notes into a report and save it to ~/Documents/platform.html.*

Each section of a report is either **new OpenUI Lang** or **a widget already shown in the chat**. That is how you export "a few components": the agent gives each widget its own section. To write a report from scratch, it composes sections from Markdown, tiles, tables and charts.

## What the agent sends

| Parameter | Meaning |
|---|---|
| `title` | The page title and its top heading. At most 120 characters. Default: `Hermes report`. |
| `sections` | One to 30 sections. Each has an optional `title` (its heading) and **exactly one** of `source` (OpenUI Lang) or `widget` (the name of a widget rendered earlier in this chat). |
| `path` | Where to save. A `.html` or `.htm` file, or a folder. Optional. |
| `overwrite` | `true` replaces an existing file. Default `false`. |
| `theme` | `auto` follows the viewer's light or dark setting. `light` or `dark` forces one. Default `auto`. |

A `widget` name is the file name in the render result, without `.html`. For `::preview{file=".../widgets/platform-status-1a2b3c.html"}` it is `platform-status-1a2b3c`. A name must be a plain file name that exists in this profile's `widgets/` folder.

A complete request:

```json
{
  "title": "Platform report",
  "sections": [
    {"title": "Load", "source": "root = Stack([a, b], \"row\", \"m\", true)\na = Metric(\"Servers up\", \"7 / 8\", \"-1\", \"warn\")\nb = Metric(\"Queue\", \"12\", \"-3\", \"good\")"},
    {"title": "Notes", "source": "root = Stack([m])\nm = Markdown(\"**web-2** is degraded.\")"}
  ]
}
```

## Where the file goes

- **Default:** the `exports/` folder in the profile's Hermes home, for example `~/.hermes/exports/` or `~/.hermes/profiles/<name>/exports/`. The name is the title plus six random characters, such as `platform-status-9680cb.html`, so an export never replaces an earlier one. Hermes does not prune this folder.
- **Not `cache/documents`.** That folder is Hermes's media cache, and Hermes prunes old files from it, so an export placed there would disappear.
- **Your own default:** set `export_dir` in the plugin's settings. It must be an absolute path or start with `~`.
- **A path in the request:** a file ending in `.html` or `.htm`, or a folder. A folder is an existing one, a path ending in `/`, or a new path with no extension. Missing folders are created. `~` is expanded, and any other path must be absolute.
- **Existing files are kept** unless the request says `overwrite`.

### Places that are refused

The agent chooses the path, so the tool checks it before writing anything:

1. Hermes's own write guard (`agent.file_safety`) must allow it, and must not require the user's approval. The tool never routes around Hermes's approval system. If a place needs approval, the agent tells you and offers another folder.
2. A built-in list also applies, **on top of** the guard, because the guard allows places an exported page has no business in. It refuses anything inside `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.config/gcloud`, `~/.kube` and `~/.docker`; the Hermes home's `.env`, `auth.json`, `config.yaml`, `plugins`, `skills` and `sessions` (for this profile and the default one); and `/etc`, `/usr`, `/bin`, `/sbin`, `/System`, `/Library`, `/private/etc` and `/var/root`.

Symlinks are resolved before the check. Only `.html` and `.htm` files are ever written, and a file is written whole or not at all.

## How the file shows up in Hermes

Hermes has no artifacts folder and no artifacts API for plugins. The Desktop's Artifacts view is built from what a tool result and the reply contain, so "artifact" describes how the file is presented, not where it is stored. The file still has to live somewhere that lasts, which is why the default stays `exports/` in the Hermes home.

A successful export returns two extra keys, `artifact_path` and `media_tag` (`MEDIA:` followed by the path). The tool's reply also tells the agent to put that tag alone on its own line. Hermes then does the rest.

| Where | What the user gets |
| --- | --- |
| Desktop app | The tag becomes a file card with Preview and Download. `artifact_path` and `media_tag` are on the Desktop's list of result keys that mark a file as an artifact. A plain `path` key is not. |
| Telegram, Slack and other gateways | The gateway reads the tag and sends the file as an attachment. `.html` is on its list of deliverable types. |
| CLI | The agent prints the path. Use `hermes openui export` for a scripted run. |

Three details matter.

- **No backticks.** Hermes ignores a `MEDIA:` tag inside inline code or a code block. The tool's reply says so, because models like to put paths in backticks. I checked this against Hermes's own extractor.
- **Spaces in paths are fine.** The extractor returned the whole path for `/Users/me/My Reports/q3 status.html`.
- **A refused export carries neither key.** An export the tool rejects has no `path`, `artifact_path` or `media_tag`, so nothing shows up as a file.

What is not verified. I read the Desktop and gateway code and ran the gateway's extractor, but I have not watched an export appear in the Artifacts view of a live chat or arrive on a messaging platform.

## What the page is

- **One file** with the runtime inside it, typically 280 to 400 KB. The limit is 8 MB. Images may be up to 1 MB each, where a chat widget allows 100 KB.
- **Offline.** In a headless Chrome, a page with a map, tiles, a chart and Markdown made no network requests and logged no console errors.
- **Light or dark.** The default follows the viewer's setting. A forced theme also overrides the page's own check, so the charts agree.
- **Buttons.** A `Button` or `Choice` talks to the agent, which a file on disk cannot do. Clicking one shows the notice "Interactive buttons work inside Hermes only".
- **Custom components.** Linked packs that a report uses are embedded once. See [Custom components](custom-components.md).

## From the terminal

```sh
hermes openui widgets                                    # names of the widgets rendered in this profile, newest first
hermes openui export platform-status-1a2b3c web-map-77aa10 --title "Platform report" --out ~/Documents/platform.html
```

`export` uses the same code as the tool, so it follows the same rules. It also takes `--theme light|dark` and `--overwrite`. Add `-p <profile>` to work on another profile.

## Known gaps

- **Only Chrome was tried** (Chrome 145 on macOS). The page needs `DecompressionStream`: Chrome 80, Safari 16.4 and Firefox 113 or newer. An older browser shows a short "could not start" message.
- **Print layout was never rendered.** The page has print rules, but no one has looked at the result.
- **It is not a static snapshot.** The charts are drawn by JavaScript when the page opens.
- **Large images** up to the 8 MB limit were checked in Python only, not drawn in a browser.
- **Windows and Linux** paths were not tried.
