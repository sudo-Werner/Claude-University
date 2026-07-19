# Installing Claude University as an app

Claude University ships a web app manifest + service worker, so any browser
that supports PWA install can add it as a standalone windowed/home-screen app
— no App Store, no `.exe`. This requires an **HTTPS origin**: Chrome (and
most browsers) refuse to show the install prompt over plain HTTP, except on
`localhost`. Tailscale gives the Pi a real HTTPS origin on its own MagicDNS
name without exposing anything to the public internet.

## One-time setup: enable Tailscale HTTPS certificates

This is an account-level setting, not a device one — it can only be turned on
by the tailnet admin (Werner), via the web dashboard:

1. Go to <https://login.tailscale.com/admin/dns> (log in with the account
   this tailnet is on).
2. Under **HTTPS Certificates**, click **Enable HTTPS**.
3. On the Pi, run once:
   ```
   sudo tailscale cert wernerpi.tail0a23da.ts.net
   sudo tailscale serve --bg https / http://localhost:8200
   ```
   `tailscale serve` adds an HTTPS listener in front of the existing
   waitress service — it does **not** touch the existing plain-HTTP access
   on port 8200 at all. Verify both still work:
   - `https://wernerpi.tail0a23da.ts.net/api/health` → `{"status":"ok"}`
   - `http://192.168.2.69:8200/api/health` → `{"status":"ok"}` (unchanged)
4. To undo at any point: `sudo tailscale serve reset`.

Only devices on this tailnet can reach the HTTPS origin — `tailscale serve`
(without `funnel`) never exposes anything to the public internet.

## Installing, once the HTTPS origin is live

### Mac / Windows (Chrome or Edge)

1. Open `https://wernerpi.tail0a23da.ts.net/` in the browser.
2. Click the install icon in the address bar (a small monitor-with-arrow
   icon), or the browser menu → **Install Claude University…**.
3. It opens in its own window, with its own Dock/Taskbar icon and app
   switcher entry — no browser chrome.

### Android (Chrome)

1. Open the HTTPS URL.
2. Tap the **⋮** menu → **Add to Home screen** / **Install app**.
3. It appears on the home screen and opens standalone, like any other app.

### iPhone/iPad (Safari)

Safari doesn't support the full PWA install-prompt flow, but reads the same
manifest for "Add to Home Screen":

1. Open the HTTPS URL in Safari.
2. Tap **Share** → **Add to Home Screen**.
3. It appears on the home screen with the app icon and opens without Safari's
   address bar.

## Plain LAN access is unaffected

Nothing about `http://192.168.2.69:8200` (or any other LAN IP/hostname)
changes — `tailscale serve` only adds a new HTTPS listener alongside the
existing one, it never replaces it. Any device that hasn't set up Tailscale
keeps working exactly as before; it just won't get the install prompt (no
HTTPS on that origin).
