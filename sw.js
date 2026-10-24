const CACHE = "goal-predictor-ai-v7";
const CORE_ASSETS = ["./", "./index.html", "./manifest.json"];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(CORE_ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("goal-predictor-ai-") && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  const isJsonData = /\/data\/[^/]+\.json$/.test(url.pathname);
  const dataName = isJsonData ? url.pathname.split("/").pop() : null;
  const canonicalDataRequest = isJsonData ? new Request(new URL("./data/" + dataName, self.registration.scope).toString()) : null;
  event.respondWith(fetch(event.request).then(response => {
    if (response.ok) {
      const copy = response.clone();
      event.waitUntil(caches.open(CACHE).then(async cache => {
        await cache.put(event.request, copy);
        if (canonicalDataRequest) await cache.put(canonicalDataRequest, response.clone());
      }));
    }
    return response;
  }).catch(async () => {
    const exact = await caches.match(event.request);
    if (exact) return exact;
    if (canonicalDataRequest) {
      const canonical = await caches.match(canonicalDataRequest);
      if (canonical) return canonical;
      return new Response(JSON.stringify({error:"offline_data_unavailable",matches:[],count:0}), {status:503,headers:{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store"}});
    }
    return await caches.match(event.request) || await caches.match("./index.html");
  }));
});
