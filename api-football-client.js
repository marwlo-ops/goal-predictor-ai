/**
 * Small browser client for the Goal Predictor AI API-Football Worker.
 * Configure window.GPA_API_BASE_URL to your deployed Worker URL before using.
 * The API key must never be stored in this file.
 */
(function (global) {
  "use strict";
  const allowed = new Set([
    "fixtures", "h2h", "statistics", "team-statistics", "standings", "injuries", "odds"
  ]);

  async function request(endpoint, params = {}) {
    if (!allowed.has(endpoint)) throw new Error("Nieobsługiwany endpoint API.");
    const base = String(global.GPA_API_BASE_URL || "").replace(/\/$/, "");
    if (!base) throw new Error("Najpierw skonfiguruj adres bezpiecznego proxy API-Football.");
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
    });
    const url = base + "/api/" + endpoint + (query.size ? "?" + query.toString() : "");
    const response = await fetch(url, { method: "GET", headers: { "Accept": "application/json" } });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || "Błąd pobierania danych.");
    return data;
  }

  global.GoalPredictorApiFootball = Object.freeze({
    fixtures: (params) => request("fixtures", params),
    headToHead: (teamA, teamB, params = {}) => request("h2h", { ...params, h2h: String(teamA) + "-" + String(teamB) }),
    fixtureStatistics: (fixtureId, params = {}) => request("statistics", { ...params, fixture: fixtureId }),
    teamStatistics: (params) => request("team-statistics", params),
    standings: (params) => request("standings", params),
    injuries: (params) => request("injuries", params),
    odds: (params) => request("odds", params)
  });
})(window);
