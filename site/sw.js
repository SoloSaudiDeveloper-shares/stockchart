// Offline support for the installed app: the shell is served from cache and refreshed in
// the background; data.json always tries the network first so prices stay current.
const CACHE = "tawzi-v1";
const SHELL = ["./", "index.html", "style.css", "app.js", "manifest.webmanifest", "icon.svg", "icon-192.png", "icon-512.png"];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin) return;
  const fromNetwork = fetch(event.request).then(response => {
    if (response.ok) {
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put(event.request, copy));
    }
    return response;
  });
  if (url.pathname.endsWith("data.json")) {
    event.respondWith(fromNetwork.catch(() => caches.match(event.request)));
  } else {
    event.respondWith(caches.match(event.request).then(hit => hit || fromNetwork));
  }
});
