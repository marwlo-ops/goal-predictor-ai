/**
 * Goal Predictor AI — secure API-Football proxy for Cloudflare Workers.
 *
 * Required Worker secrets/settings:
 *   API_FOOTBALL_KEY (secret)
 *   ALLOWED_ORIGIN (plain text, exact origin, e.g. https://OWNER.github.io)
 *
 * Deploy this Worker separately from GitHub Pages. Never place the API key in frontend code.
 */
const ROUTES = {
  "/api/fixtures": {
    upstream: "/fixtures",
    allowed: ["date", "from", "to", "league", "season", "team", "last", "next", "live", "timezone", "status"],
  },
  "/api/h2h": {
    upstream: "/fixtures/headtohead",
    allowed: ["h2h", "date", "league", "season", "last", "next", "from", "to", "status", "timezone"],
    required: ["h2h"],
  },
  "/api/statistics": {
    upstream: "/fixtures/statistics",
    allowed: ["fixture", "team", "type", "half"],
    required: ["fixture"],
  },
  "/api/team-statistics": {
    upstream: "/teams/statistics",
    allowed: ["league", "season", "team", "date"],
    required: ["league", "season", "team"],
  },
  "/api/standings": {
    upstream: "/standings",
    allowed: ["league", "season", "team"],
    required: ["league", "season"],
  },
  "/api/injuries": {
    upstream: "/injuries",
    allowed: ["league", "season", "team", "fixture", "player", "date"],
  },
  "/api/odds": {
    upstream: "/odds",
    allowed: ["fixture", "league", "season", "date", "bookmaker", "bet"],
  },
};

function response(body, status, origin, extra = {}) {
  return new Response(body, {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Vary": "Origin",
      "X-Content-Type-Options": "nosniff",
      ...extra,
    },
  });
}

export default {
  async fetch(request, env, ctx) {
    const requestUrl = new URL(request.url);
    const allowedOrigin = env.ALLOWED_ORIGIN;
    const origin = request.headers.get("Origin");

    if (!allowedOrigin || !env.API_FOOTBALL_KEY) {
      return response(JSON.stringify({ error: "Worker is not configured." }), 500, allowedOrigin || "null");
    }
    if (origin && origin !== allowedOrigin) {
      return new Response("Forbidden", { status: 403, headers: { "Vary": "Origin" } });
    }
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": allowedOrigin,
          "Access-Control-Allow-Methods": "GET, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
          "Access-Control-Max-Age": "86400",
          "Vary": "Origin",
        },
      });
    }
    if (request.method !== "GET") {
      return response(JSON.stringify({ error: "Method not allowed." }), 405, allowedOrigin);
    }

    const route = ROUTES[requestUrl.pathname];
    if (!route) return response(JSON.stringify({ error: "Unknown endpoint." }), 404, allowedOrigin);

    const upstreamParams = new URLSearchParams();
    for (const [key, value] of requestUrl.searchParams.entries()) {
      if (!route.allowed.includes(key)) {
        return response(JSON.stringify({ error: `Unsupported parameter: ${key}` }), 400, allowedOrigin);
      }
      if (!value || value.length > 120 || /[<>\u0000-\u001f]/.test(value)) {
        return response(JSON.stringify({ error: `Invalid parameter: ${key}` }), 400, allowedOrigin);
      }
      upstreamParams.set(key, value);
    }
    for (const key of route.required || []) {
      if (!upstreamParams.has(key)) {
        return response(JSON.stringify({ error: `Missing required parameter: ${key}` }), 400, allowedOrigin);
      }
    }

    const target = `https://v3.football.api-sports.io${route.upstream}?${upstreamParams.toString()}`;
    const cacheKey = new Request(target, { method: "GET" });
    const cache = caches.default;
    const cached = await cache.match(cacheKey);
    if (cached) {
      const headers = new Headers(cached.headers);
      headers.set("Access-Control-Allow-Origin", allowedOrigin);
      headers.set("Vary", "Origin");
      return new Response(cached.body, { status: cached.status, headers });
    }

    try {
      const upstream = await fetch(target, {
        headers: { "x-apisports-key": env.API_FOOTBALL_KEY },
      });
      const text = await upstream.text();
      let parsed;
      try { parsed = JSON.parse(text); } catch {
        return response(JSON.stringify({ error: "Invalid response from football data provider." }), 502, allowedOrigin);
      }
      if (!upstream.ok) {
        return response(JSON.stringify({ error: "Football data provider returned an error.", status: upstream.status }), 502, allowedOrigin);
      }
      if (parsed.errors && Object.keys(parsed.errors).length) {
        return response(JSON.stringify({ error: "Football data provider rejected the request.", details: parsed.errors }), 502, allowedOrigin);
      }
      const ttl = requestUrl.pathname === "/api/fixtures" ? 60 : 300;
      const result = response(JSON.stringify(parsed), 200, allowedOrigin, {
        "Cache-Control": `public, max-age=${ttl}`,
      });
      ctx.waitUntil(cache.put(cacheKey, result.clone()));
      return result;
    } catch {
      return response(JSON.stringify({ error: "Could not reach football data provider." }), 502, allowedOrigin);
    }
  },
};
