// Stand-in for the app's `@hermes/plugin-sdk` in the native layout harness (native-harness.mjs). It carries only what
// desktop/plugin.js calls, and records the calls so the harness page can show them.
export const TRANSCRIPT_DIRECTIVE_AREA = "transcript-directive";
export const calls = [];
export const host = {
  composer: {
    submit: (...args) => (calls.push({ submit: args }), true),
    // Notes: insertText records its arguments and answers true unless the page set window.__insertResult to false (or to "throw").
    insertText: (...args) => {
      calls.push({ insertText: args });
      if (typeof window !== "undefined" && window.__insertResult === "throw") throw new Error("no composer");
      return Promise.resolve(!(typeof window !== "undefined" && window.__insertResult === false));
    },
    setDraft: (...args) => (calls.push({ setDraft: args }), Promise.resolve(true)),
    focus: (...args) => void calls.push({ focus: args }),
  },
  notify: (n) => calls.push({ notify: n }),
  // Notes: the runtime id of the session the primary chat shows (null = a fresh draft); a page sets window.__activeSessionId.
  state: { activeSessionId: { get: () => (typeof window !== "undefined" && "__activeSessionId" in window ? window.__activeSessionId : null) } },
};

if (typeof window !== "undefined") window.__hostCalls = calls; // the harness page reads what the widgets asked of the host
