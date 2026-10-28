// Stand-in for the app's `@hermes/plugin-sdk` in the native layout harness (native-harness.mjs). It carries only what
// desktop/plugin.js calls, and records the calls so the harness page can show them.
export const TRANSCRIPT_DIRECTIVE_AREA = "transcript-directive";
export const calls = [];
export const host = {
  composer: { submit: (...args) => (calls.push({ submit: args }), true) },
  notify: (n) => calls.push({ notify: n }),
};
