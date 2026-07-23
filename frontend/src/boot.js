// App bootstrap, moved out of platform.html so the page carries no inline script
// (keeps the CSP script-src at 'self' with no hash/nonce).
import { init } from "/src/app.js";

init({ window, fetch: window.fetch.bind(window) });

if ("serviceWorker" in navigator) {
  // Registration requires a secure context (HTTPS, or localhost) — it
  // rejects on plain-HTTP LAN access until the Tailscale HTTPS origin
  // is set up (docs/INSTALL.md). That's expected there, not an error.
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
