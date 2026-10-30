---
name: custom-components
description: Write, check and link a custom render_widget component (a one-file JS pack).
version: 0.5.0
---

# Custom components

A pack is read on every call, so it needs no rebuild or restart. Step 5 reloads it.

## When to use

Use it for what the built-ins lack. Skip it when `Stack`, `Card`, `Table` and the charts can draw it.

## Procedure

1. Propose a PascalCase name and typed arguments, saying which are optional, and wait for a yes. Done when the user agrees.
2. Run `hermes config path`. `<home>` below is the folder that holds the `config.yaml` it prints. If `$HERMES_HOME` is set it must equal `<home>`, otherwise show the user both paths and ask. For a named profile use `hermes -p NAME` in every command, check the path has `profiles/NAME`, and touch no other profile. Run `hermes openui components list` and note the slugs and component names. Choose a new slug, because a repeated slug disables one pack, and never overwrite an existing pack file. Save the pack with `write_file` as `<home>/packs/<slug>.js` from the template, and write nowhere else. Done when `read_file` shows it.
3. Run `hermes openui components check <home>/packs/<slug>.js`. Done when it prints `OK` (fix and rerun on `FAIL`). If a `Node was not found` note follows, the zod checks did not run, so say so and ask the user to check the sample closely.
4. Read the list with `hermes config get plugins.entries.hermes-openui.settings.components --json` (read only; a non-zero exit means unset). If it holds `<home>/packs`, skip the rest of this step, because a folder entry links every `.js` in it, not subfolders. Otherwise show the user the pack path and wait for a yes before you run `config set`. Add `<home>/packs` and write the whole list back with `hermes config set plugins.entries.hermes-openui.settings.components '["<home>/packs"]'` (absolute paths, never hand-edit the YAML), because `set` replaces the list. Done when `hermes openui components list` shows the pack. If the user declines, name the folder to add under Capabilities > Plugins > hermes-openui.
5. Call `render_widget(reference=true)` again, because an earlier reference is stale. It also holds the OpenUI Lang syntax rules, and "Custom components" is its last section. Done when that section lists the new component and every component the step 2 list showed, and the result has no `pack_warnings`. That field also appears in a successful `render_widget` result and is absent when nothing is wrong. If not, run `hermes openui components list`.
6. Call `render_widget(source=..., name=...)` (`name` is an optional label for the saved file) with a sample such as `root = Stack([a])` and `a = <Component>(...)`. Show the `directive` alone on its own line and tell the user to read the pack file before relying on it. Done when `ok` is true, `packs` holds `custom:<slug>`, the result has no `pack_warnings` and the user confirms the look.
7. Iterate with edit, check and render, and fetch the reference again if a signature changed. Done when the user is satisfied.

## Template

Change `progress` in three places (header `name`, `register`, file name) and replace `ProgressBar`.

```js
/* hermes-openui-pack
{"api": 1, "name": "progress", "components": {
  "ProgressBar": "ProgressBar(label: string, value: number, max?: number). A bar for value out of max (default 100)."
}}
*/
(function () {
  var mods = window.__HM.mods;
  var h = mods.react.createElement, z = mods.zod.z;
  var defineComponent = mods["@openuidev/react-lang"].defineComponent;

  var ProgressBar = defineComponent({
    name: "ProgressBar",
    description: "A bar for value out of max.",
    props: z.object({ label: z.string(), value: z.number(), max: z.number().optional() }),
    component: function (ctx) {
      var p = ctx.props;
      var pct = Math.max(0, Math.min(100, (p.value / (p.max > 0 ? p.max : 100)) * 100));
      return h("div", { style: { color: "var(--foreground, CanvasText)" } },
        h("div", { style: { marginBottom: 4, overflowWrap: "anywhere" } }, p.label + " ",
          h("span", { style: { color: "var(--muted-foreground, GrayText)" } }, Math.round(pct) + "%")),
        h("div", { style: { height: 8, borderRadius: 4, overflow: "hidden", background: "var(--border, rgba(128,128,128,0.3))" } },
          h("div", { style: { width: pct + "%", height: "100%", background: "var(--accent, Highlight)" } })));
    },
  });

  window.__HM.register({ name: "progress", components: [ProgressBar] });
})();
```

## Rules

- The header is the JSON comment at the top. `api` is `1`, `name` is the pack slug (lowercase letters, digits, hyphens, at most 32, starting with a letter) and `components` maps each component name to its reference line. The agent reads only that line, not the `description` of `defineComponent`, and `check` compares only the names, so keep it equal to the zod props by hand (arguments in order, `?` on optional ones, an object array as `events: {date: string, title: string, detail?: string}[]`). Component names are PascalCase letters and digits, at most 48, and match no built-in or other pack.
- Call `window.__HM.register({ name, components })` once, with the header's slug (`check` does not compare them) and an array of the `defineComponent` results.
- Plain JavaScript, no `import`, no JSX. React, zod and `defineComponent` come from `window.__HM.mods`. The zod keys set the argument order, so put optional ones last.
- Types, each followed by its OpenUI Lang value, are `z.string()` `"a"`, `z.number()` `3`, `z.boolean()` `true`, `z.enum(["a", "b"])` `"a"`, `z.array(z.string())` `["a", "b"]`, `z.array(z.object({ label: z.string(), n: z.number() }))` `[{label: "a", n: 1}]` (plain objects). A left-out `.optional()` argument is `undefined`, and `null` stays `null`, so pass it to skip one in the middle.
- No network or dynamic code, for example `fetch`, `WebSocket`, `EventSource`, `sendBeacon`, `eval(`, `Function(`, `import(`. `check` names the exact word. At most 200 KB.
- The host defines `--foreground`, `--muted-foreground`, `--accent`, `--border` and `--card`. Use them with fallbacks. A literal color such as `#f5a623` is fine but ignores theme changes.
- The column is up to 640 px wide. Use `overflowX: "auto"` for wide content and `overflowWrap: "anywhere"` for long text. Do not set `fontFamily`; built-ins inherit the host's.
- The template clamps out-of-range values on purpose. Rules zod cannot state go in `validate: function (typeName, props) {...}` on the `register` argument. It returns an array of problem strings, runs only in the Node check of a rendered source (not in `check`), and must be pure.

## Pitfalls

- Packs run in the widget sandbox, in preview mode and on `export_widgets` pages. Native mode refuses them.
- To remove a pack, delete its file. Only if that leaves a linked folder with no `.js` file, and after the user says yes, write the list from step 4 back without that folder with `config set`. Use `hermes config unset` only if it was the only entry, because it drops the whole list.

## Verification

Report only what you saw. On `ok: false`, fix exactly the `errors`. `ok: true` with `checked: "node"` means the source parses, matches the zod schema and passed any `validate` hook. `"structural"` means the Node check did not run (no Node, no validator file or a timeout), so the schema was not checked. Neither runs your component function, which can still throw and draw nothing, so keep it null-safe.

## Making it built in (maintainers)

Work only in a development checkout of newtonapple/hermes-openui, never in the installed copy, and follow section 3 of its `AGENTS.md`. Ask before `cd build && npm ci` (network), then run `npm run build` and the tests. Ask before the commit and before the reload with `hermes plugins install file://<checkout path> --force --enable` (add `-p NAME` for a named profile). Then start a NEW chat. The user restarts the gateway with `hermes -p NAME gateway restart` in a separate shell.
