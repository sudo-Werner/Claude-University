// Minimal service worker: caches the static app shell only, so the install
// prompt has something to point at. NEVER caches /api/* — every dynamic read
// (courses, lessons, stats, chat) must always hit the network; the offline
// sync design (frontend/src/sync.js) already owns its own localStorage queue
// and would double up badly with a cached API response.
const CACHE = "cu-shell-v3";
const SHELL = ["/", "/styles.css"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.pathname.startsWith("/api/")) return;
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const network = fetch(event.request)
        .then((resp) => {
          if (resp.ok) caches.open(CACHE).then((cache) => cache.put(event.request, resp.clone()));
          return resp;
        })
        .catch(() => cached);
      return cached || network;
    }),
  );
});
