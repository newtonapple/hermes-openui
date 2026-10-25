// Stand-ins for react-dom inside the plugin bundle. The desktop loader resolves only `react`, `react/jsx-runtime` and
// the SDK, so `react-dom` cannot be imported. The only consumers are portals (Radix tooltips in the charts) and
// flushSync (floating-ui): render a portal inline and run flushSync callbacks directly. Tooltips therefore render inside
// the widget instead of on <body>, which is acceptable for a read-only widget.
export function createPortal(children) {
  return children;
}
export function flushSync(fn) {
  return typeof fn === "function" ? fn() : undefined;
}
export const version = "0-shim";
export default { createPortal, flushSync, version };
