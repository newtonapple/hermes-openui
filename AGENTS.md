# AGENTS.md: hermes-openui

For AI agents that **install**, **use** or **change** this plugin. Humans: read `README.md`. Long-form design and pitfalls: `docs/development.md`.

`hermes-openui` is a Hermes Agent plugin. It gives the model one tool, `render_widget`, that turns OpenUI Lang source into an inline widget (dashboards, charts, DAG/ER diagrams, maps) in the **Hermes desktop app**. Python half (stdlib only): `__init__.py`, `tools.py`, `page.py`, `lint.py`, `bundle.py`, `schemas.py`. Shipped, generated browser runtime: `assets/`. Optional native renderer: `desktop/plugin.js`. Build sources for the generated files: `build/`.

## 1. Install (do exactly this)

```sh
sh scripts/install.sh                 # from the repository root; installs into $HERMES_HOME or ~/.hermes, then enables
hermes plugins list | grep hermes-openui          # expect: enabled
hermes plugins doctor ~/.hermes/plugins/hermes-openui   # expect: OK ... registrations: 1 tool(s)
```

- **Another profile or a test home:** `sh scripts/install.sh --home <dir>` (profiles live in `~/.hermes/profiles/<name>`). To test without touching the real setup, use a fresh scratch directory, then `HERMES_HOME=<dir> hermes plugins list`.
- **Do not** use `hermes plugins install <path>`: a filesystem path is parsed as GitHub shorthand and fails. From Git: `hermes plugins install newtonapple/hermes-openui --enable`.
- **After installing, the tool exists only in NEW chats.** Tell the user to start a new chat, or to restart the gateway themselves (`hermes gateway restart` must run in a separate shell, never from inside a gateway-run command).
- **The desktop half is opt-in and runs with full app authority.** Never switch it on or set `mode: native` for the user without asking; the default `preview` mode needs neither.
- **Verify end to end:** in a new desktop chat ask for "a bar chart of 3, 5 and 2 for a, b, c". A widget should appear. You cannot see the desktop render: end with the directive the tool returned and ask the user to confirm.
- **Update:** `git pull && sh scripts/install.sh` (the old copy moves to `<home>/cache/`, never deleted; enabled state and settings are kept). **Remove:** `hermes plugins remove hermes-openui` (add `-p <name>` for a profile). It deletes the plugin folder, drops it from `plugins.enabled` and clears its settings, and it leaves `<home>/widgets/`, the `previous` copies and any manual `~/.hermes/desktop-plugins/hermes-openui/` file.
- **`install.sh` always enables** the plugin, even one the user disabled on purpose: pass `--no-enable` when the user did not ask to turn it on. Each profile is separate: install into every profile that needs it.
- **`config.yaml` edits:** install already creates a `plugins:` block (`enabled:`). Add `entries:` under it; never append a second top-level `plugins:` key.

## 2. Use the tool (when you are the agent in a Hermes desktop chat)

1. Call `render_widget(reference=true)` once per chat for exact component signatures. Never guess a signature.
2. Call `render_widget(source=<OpenUI Lang>)`. Format: `root = Stack([...])` first, then one `name = Component(...)` per line; **positional** arguments only (no `name: value`); double-quoted strings; literal data only; every variable reachable from `root`.
3. On `ok: false`, fix exactly the listed `errors` and call again. Nothing was written.
4. On `ok: true`, put the returned `directive` **alone on its own line** in your reply, after at most one sentence. Do not repeat the widget's data in prose.
5. One widget per reply (use Tabs/Cards for sections). Plain text for a single value or a short answer. Never invent data to fill a layout. Button and Choice clicks arrive as your next user turn: act, then render a NEW widget.
6. Patterns and pitfalls: `skill_view("hermes-openui:openui-render")`.

## 3. Change the code

**Hard rules**
- **Python: standard library only; keep it runnable on 3.9** (Hermes itself needs 3.11+, 3.9 is the conservative floor the tests run on). No dependencies; no `X | Y` type unions or `match` at runtime.
- **No network access, no telemetry, anywhere.** `tests/test_plugin.py` and both build scripts fail on `fetch(`, `XMLHttpRequest`, `sendBeacon`, `WebSocket(`, `posthog`, `cloudfront` in any shipped browser file. Never `import * as` a whole OpenUI package into a bundle (it keeps their dormant telemetry); import named exports.
- **Never edit generated files by hand:** `assets/*`, `desktop/plugin.js`, `THIRD_PARTY_NOTICES.md`. Change `build/src/` and rebuild.
- **Vet before adding any npm dependency** (postinstall scripts, telemetry). Installs run with `--ignore-scripts`; the lockfile is `build/package-lock.json`; use `npm ci`.
- **Context discipline.** The schema description (`schemas.py`) is at most about 700 characters, its first sentence is at most 60 characters and names DAG/ER/maps/dashboards (that sentence is all Tool Search lists). The component reference is returned by `render_widget(reference=true)`, never put in the schema. Extra tools or long descriptions cost every chat.
- **Description words are the search index.** Tool Search finds the tool by the words in its description (BM25, gated on the rarest query word). `tests/test_plugin.py` pins the words; `tools/verify_discovery.py` measures recall (20 of 20 keyword queries). Re-run it after changing the description.
- **Page budget:** a preview page must stay under 480 KB (the app reads at most 512 KiB and silently truncates). Only the packs a widget uses are embedded. Images: 100 KB each.
- **Do not touch Hermes core** and do not rebind its functions. Paths come from `get_hermes_home()` at call time (one process serves several profiles).
- **Local installs and iCloud:** never run `npm ci` or create `.git`-heavy trees inside a synced folder (iCloud). Build in a normal directory.
- Ask the owner before committing, tagging or publishing.

**Commands (run from the repository root)**

```sh
python3 -m unittest discover -s tests              # must pass; ~2 s
hermes plugins validate .                          # must print `Validation passed` with every check ticked (security scan, desktop surface, declared tools).
                                                   # One warning is expected: `private core imports` from tools/verify_*.py. Those dev scripts test Hermes's Tool Search
                                                   # on purpose and the installer does not copy them. Any other warning is new: fix it.
cd build && npm ci && npm run build                # regenerates assets/ and desktop/plugin.js; commit the results with the source change
node scripts/notices.mjs                           # after a dependency change (from build/)
python3 tools/check_docs.py                        # docs/ui-components checks
python3 tools/shoot.py <file.oui> <out.png>        # screenshot a widget (needs Chrome; see its --help)
```

Runtime checks against a real Hermes, in an isolated home: install with `scripts/install.sh --home <fresh dir>`, then `HERMES_HOME=<dir> ~/.hermes/hermes-agent/venv/bin/python tools/verify_runtime.py` and `tools/verify_discovery.py`.

**Definition of done**
- [ ] Unit tests pass; `hermes plugins validate .` passes.
- [ ] If `build/src/` changed: rebuilt, `assets/packs.json` hashes updated, and the **desktop loader check** passed (`build/tests/plugin-loader-check.mjs` runs inside `npm run build`).
- [ ] If a component changed: its page and example in `docs/ui-components/` updated, `tools/check_docs.py` clean.
- [ ] If the schema changed: `tools/verify_discovery.py` still finds 20 of 20 keyword queries.
- [ ] You rendered at least one widget and looked at it (`tools/shoot.py`); a passing build does not prove it looks right.

## 4. Pitfalls already paid for (details in `docs/development.md`)

- `hermes plugins install` takes a catalog name, Git URL or `owner/repo`, never a path.
- The desktop loader rewrites only `import` + whitespace + quote. A minified `import"react"` stays bare and the **whole file is refused**; the build marks externals side-effect-free to prevent it. A harness with a native import map hides this: use `build/tests/plugin-loader-check.mjs`.
- A disk plugin may import only `@hermes/plugin-sdk`, `react`, `react/jsx-runtime`: no `react-dom` (shimmed), and bundled CommonJS calling `require("react")` needs the banner `require`.
- The app mirrors only **error-level** console lines into `desktop.log`.
- A plugin cannot send a hidden turn: `host.composer.submit` types a visible message.
- Plugin skills are not in the system prompt's skill index; the tool description is what makes the agent find the tool.
- Headless Chrome one-shot flags (`--screenshot`, `--dump-dom`) can hang on macOS; `tools/shoot.py` drives Chrome over its debugging port instead.
- gzip bytes differ between Node/zlib versions; compare the `sha256` of the uncompressed bundle in `assets/packs.json`.
- `tools/check_docs.py` ends an ```` ```openui ```` block at the first triple backtick, so an example whose string holds a code fence can never match its `.oui` file. Write the fence as `\u0060\u0060\u0060` inside the string (the parser accepts it and renders the same), as `docs/ui-components/examples/markdown-code-table.oui` does.
- `build/node_modules` may be a symlink to a local install. Never copy it into a synced folder or a commit; `build/dist/` is regenerable output and is git-ignored.

## 5. Release a new version

Ask the owner before you commit, tag or push. The version lives in three files and `tests/test_version.py` fails if they disagree.

1. Pick the number by the table in the README ([Versioning](README.md#versioning)). Removing or renaming a component, an argument, a setting or a `render_widget` parameter is a major change.
2. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`, add a fresh empty `## [Unreleased]` above it, and update the two link lines at the bottom.
3. Set `version:` to `X.Y.Z` in `plugin.yaml` and in `skills/openui-render/SKILL.md`.
4. If `build/src/` changed, rebuild first. The generated files are committed.
5. Run `python3 -m unittest discover -s tests`, `hermes plugins validate .` and `python3 tools/check_docs.py`. All three must pass.
6. Commit as `Release X.Y.Z`, then tag that commit: `git tag -a vX.Y.Z -m "hermes-openui X.Y.Z"`. Push the branch and the tag.
7. Raise `requires_hermes` only when the code needs a newer Hermes, and only to a version you ran it on. Test it both ways: it must load on the current Hermes, and a floor above the current version must be refused with `requires hermes ...` in `hermes plugins doctor`.
