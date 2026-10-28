# Custom components

You can add your own components to the widgets Hermes draws. A custom component lives in a small JavaScript file called a pack. Link the pack in the plugin's settings, and the agent can use its components in `render_widget` and `export_widgets` like any built-in one.

Packs work in **preview mode** only. Native mode renders inside the app itself and does not run user scripts, so it refuses a source that calls a custom component.

## Ask the agent to write one

You do not have to write the JavaScript yourself. Describe the component in a chat, for example "make me a custom component, a progress bar with a label and a percentage". The bundled skill `hermes-openui:custom-components` tells the agent to do these things, in order:

1. Agree the name and the arguments with you.
2. Write the pack into a `packs` folder in the profile's Hermes home.
3. Check it with `hermes openui components check`.
4. Link that folder in the `components` setting.
5. Fetch the component reference again, so the new component is listed.
6. Draw a sample for you to confirm, and change it until you are happy.

The skill tells the agent to ask before it edits `config.yaml`. If you would rather link the pack yourself, say so and it gives you the folder to add under **Capabilities → Plugins → hermes-openui**. A folder entry links every `.js` file in it, so the next component you ask for needs no change to the setting.

The pack runs in the widget sandbox, like any pack. Read the code the agent wrote before you rely on it. If the agent does not reach for the skill, ask it to load `hermes-openui:custom-components`.

## Link a pack

Open **Capabilities → Plugins → hermes-openui** and add paths to the `components` setting, or edit `config.yaml`:

```yaml
plugins:
  entries:
    hermes-openui:
      settings:
        components:
          - ~/hermes-packs/badges.js        # one pack
          - ~/hermes-packs/team             # a folder links every .js file in it
```

Merge this under the `plugins:` block that already exists in the file. A second top-level `plugins:` key is not valid YAML.

The setting is read on every call, so a change applies to the next widget without a restart. It is per profile, like the plugin's other settings. Check what is linked, and why a pack was skipped:

```sh
hermes openui components list
hermes -p <profile> openui components list
```

The agent learns the new components from `render_widget(reference=true)`, which now ends with a "Custom components" section. A chat that fetched the reference before you linked the pack needs to fetch it again, so ask the agent to, or start a new chat.

## Write a pack

A pack is one `.js` file. Its first comment is a JSON header, so Hermes can learn what the pack adds without running any JavaScript. The script registers the components with the runtime every widget page already carries.

```js
/* hermes-openui-pack
{
  "api": 1,
  "name": "badges",
  "components": {
    "StatusPill": "StatusPill(label: string, tone?: \"ok\" | \"warn\" | \"bad\") \u2014 A small colored pill."
  }
}
*/
(function () {
  var mods = window.__HM.mods;
  var React = mods.react;
  var z = mods.zod.z;
  var defineComponent = mods["@openuidev/react-lang"].defineComponent;

  var COLORS = { ok: "#3fb950", warn: "#d29922", bad: "#f85149" };

  var StatusPill = defineComponent({
    name: "StatusPill",
    description: "A small colored pill.",
    props: z.object({ label: z.string(), tone: z.enum(["ok", "warn", "bad"]).optional() }),
    component: function (ctx) {
      var color = COLORS[ctx.props.tone || "ok"];
      return React.createElement("span", {
        style: { display: "inline-block", alignSelf: "flex-start", padding: "2px 10px", borderRadius: 999, border: "1px solid " + color, color: color, fontSize: 13 },
      }, ctx.props.label);
    },
  });

  window.__HM.register({ name: "badges", components: [StatusPill] });
})();
```

Then `StatusPill("Postgres up", "ok")` works anywhere a built-in component does.

### The rules

| Part | Rule |
|---|---|
| Header | A JSON object in the first `/* hermes-openui-pack ... */` comment. `api` must be `1`. `name` is a short lowercase slug. `components` maps each component name to its reference line. |
| Reference line | The agent reads it verbatim. Start with the component name, list the arguments in the order of the zod object's keys, mark optional ones with `?`, and finish with a short description. |
| Component names | PascalCase. They must not match a built-in component or a component in another linked pack. |
| Script | Plain JavaScript, no `import` and no JSX. Use `React.createElement`. React, zod and `defineComponent` come from `window.__HM.mods`. |
| Registration | Call `window.__HM.register({ name, components })` once. `name` must equal the header's. Every component in the header must be registered, and the reverse. |
| Size | At most 200 KB. A widget page carries the pack, and the desktop reads at most 512 KB of a page. |
| Forbidden | `fetch`, `XMLHttpRequest`, `sendBeacon`, `WebSocket`, `EventSource`, `importScripts`, `eval(`, `new Function`, `Function(` and `import(`. Words inside strings and comments do not count. |
| Colors | Use CSS variables with fallbacks, such as `var(--foreground, CanvasText)`, `var(--muted-foreground, GrayText)`, `var(--accent, AccentColor)`, `var(--border, ...)` and `var(--card, Canvas)`. The component then follows Hermes in light and dark, and also looks right on an exported HTML page. |
| Width | A preview frame is at most 640 px wide (40rem; 560 px at the app's default 14 px font). Scale to the container, and scroll sideways instead of clipping. |

### Child components

A component that only carries data for its parent, like `DagNode` for `Dag`, renders nothing. The parent lists it in its schema with `.ref` and reads the child's props:

```js
var Item = defineComponent({ name: "Item", description: "One item.", props: z.object({ id: z.string() }), component: function () { return null; } });
var List = defineComponent({
  name: "List", description: "A list.", props: z.object({ items: z.array(Item.ref) }),
  component: function (ctx) { return React.createElement("ul", null, ctx.props.items.map(function (n) { return React.createElement("li", { key: n.props.id }, n.props.id); })); },
});
```

### Extra checks with a validate hook

zod already checks argument types. For rules that span components, such as "every link names a node that exists", pass a `validate` function to `register`. It is called once for each component node of your pack and returns a list of problem strings, or an empty list. Nested components arrive as `{ typeName, props }` objects. The agent sees the problems and fixes its source, so word them as instructions.

```js
window.__HM.register({
  name: "sites",
  components: [Site, SiteMap],
  validate: function (typeName, props) {
    if (typeName !== "SiteMap") return [];
    var ids = props.nodes.map(function (n) { return n.props.id; });
    return props.links.filter(function (l) { return ids.indexOf(l.props.to) < 0; })
      .map(function (l) { return "Link goes to unknown node `" + l.props.to + "` (known: " + ids.join(", ") + ")."; });
  },
});
```

The hook must be a pure function. It runs in Node, with no browser APIs.

### Check a pack before you link it

```sh
hermes openui components check my-pack.js
```

It checks the header and the forbidden-API rule. With Node installed, it also loads the script in the same sandbox the validator uses. It fails if the script throws, or if the components it registers differ from the header's.

## How it works

- **Python** reads each pack's header. That tells it which components exist, so it can check names, write the reference the agent reads, and decide which packs a page needs.
- **A page embeds a pack only when the source calls one of its components.** Linking ten packs costs nothing for a widget that uses none of them.
- **The Node validator** runs the real parser with your pack loaded, so your zod schemas apply exactly as they do in the browser, and your `validate` hook adds its checks.
- **The browser** registers the pack's components before it draws the widget. Packs share the runtime's single copy of React and zod.

## Safety

A pack runs inside the same sandboxed frame as the rest of the widget: scripts allowed, no access to the app, no shared storage. That is the same boundary that already contains any HTML an agent writes with `::preview`. The forbidden-API check catches obvious mistakes. It is not a security boundary, and the sandbox is.

Link only packs you trust. A pack can draw anything inside its widget, including text that looks like part of the chat.

## Known gaps

- Preview mode only.
- Without Node installed, a source that uses custom components gets the structural check but not the zod check or your `validate` hook, and **the browser does not report the difference**. A pack in this guide drew a pill with an invalid `tone` as if the argument were missing, with no error anywhere. Install Node 18 or newer if you rely on packs.
- The pack API is version 1. A change that breaks packs will raise the number, and a pack with another `api` is refused with a message that says so.
