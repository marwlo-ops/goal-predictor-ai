const CACHE = "goal-predictor-ai-v4";
const CORE_ASSETS = ["./", "./index.html", "./manifest.json"];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => cache.addAll(CORE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(key => key.startsWith("goal-predictor-ai-") && key !== CACHE)
          .map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;

  const requestUrl = new URL(event.request.url);
  const isLatestData = requestUrl.origin === self.location.origin
    && requestUrl.pathname.endsWith("/data/latest.json");
  const canonicalDataRequest = isLatestData
    ? new Request(new URL("./data/latest.json", self.registration.scope).toString())
    : null;

  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response.ok && requestUrl.origin === self.location.origin) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => {
            cache.put(event.request, copy);
            if (isLatestData && canonicalDataRequest) {
              cache.put(canonicalDataRequest, response.clone());
            }
          });
        }
        return response;
      })
      .catch(() => caches.match(event.request).then(cached => {
        if (cached) return cached;
        if (isLatestData && canonicalDataRequest) {
          return caches.match(canonicalDataRequest).then(data => data || caches.match("./index.html"));
        }
        return caches.match("./index.html");
      }))
  );
});
