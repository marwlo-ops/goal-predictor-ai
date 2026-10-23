#!/usr/bin/env python3
"""Supplemental API-Football fixture verification and match-statistics feed.

API key is read only from the API_FOOTBALL_KEY environment variable.
Budget guard: up to 3 date calls, 4 H2H calls, and 6 statistics calls per run.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
BASE = "https://v3.football.api-sports.io"
WARSAW = ZoneInfo("Europe/Warsaw")
INPUT = Path("data/latest.json")
OUTPUT = Path("data/api-football.json")
MAX_STATS_CALLS = 6
MAX_H2H_CALLS = 4


def api_get(path, params):
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{BASE}{path}?{query}",
        headers={"x-apisports-key": KEY, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        raise RuntimeError(f"API-Football HTTP {exc.code}: {detail}") from exc
    if payload.get("errors"):
        raise RuntimeError(f"API-Football errors: {payload['errors']}")
    return payload


def norm(value):
    value = (value or "").lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def main():
    if not KEY:
        print("API_FOOTBALL_KEY nie ustawiony — pomijam weryfikację pomocniczą.")
        return 0
    if not INPUT.exists():
        raise RuntimeError("Brak data/latest.json; najpierw wygeneruj terminarz.")

    latest = json.loads(INPUT.read_text(encoding="utf-8"))
    matches = latest.get("matches", [])
    today = datetime.now(WARSAW).date()
    dates = sorted({m.get("date") for m in matches if m.get("date")})
    if not dates:
        dates = [(today + timedelta(days=i)).isoformat() for i in range(3)]

    raw_fixtures = []
    diagnostics = []
    for date in dates[:3]:
        payload = api_get("/fixtures", {"date": date, "timezone": "Europe/Warsaw"})
        response = payload.get("response", [])
        raw_fixtures.extend(response)
        diagnostics.append(f"{date}: {len(response)} spotkań w API-Football")

    indexed = {}
    for raw in raw_fixtures:
        fixture = raw.get("fixture") or {}
        teams = raw.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        kickoff = fixture.get("date")
        if not home.get("name") or not away.get("name") or not kickoff:
            continue
        indexed[(kickoff[:10], norm(home["name"]), norm(away["name"]))] = {
            "fixtureId": fixture.get("id"),
            "kickoff": kickoff,
            "status": (fixture.get("status") or {}).get("short"),
            "elapsed": (fixture.get("status") or {}).get("elapsed"),
            "home": home["name"],
            "away": away["name"],
            "homeTeamId": home.get("id"),
            "awayTeamId": away.get("id"),
            "venue": (fixture.get("venue") or {}).get("name"),
            "referee": fixture.get("referee"),
            "league": (raw.get("league") or {}).get("name"),
            "season": (raw.get("league") or {}).get("season"),
            "homeGoals": (raw.get("goals") or {}).get("home"),
            "awayGoals": (raw.get("goals") or {}).get("away"),
        }

    verified = []
    for match in matches:
        key = (match.get("date", ""), norm(match.get("home")), norm(match.get("away")))
        supplemental = indexed.get(key)
        if supplemental:
            verified.append({"matchId": match.get("id"), **supplemental, "source": "API-Football"})

    # Only request stats for live/finished games; upcoming games have no match stats yet.
    stats_by_fixture = {}
    stat_candidates = [
        item for item in verified
        if item.get("fixtureId") and item.get("status") in {
            "1H", "HT", "2H", "ET", "P", "FT", "AET", "PEN"
        }
    ][:MAX_STATS_CALLS]
    for item in stat_candidates:
        try:
            payload = api_get("/fixtures/statistics", {"fixture": item["fixtureId"]})
            parsed = []
            for team_block in payload.get("response", []):
                team_name = (team_block.get("team") or {}).get("name")
                values = {}
                for stat in team_block.get("statistics", []):
                    name = stat.get("type")
                    if name:
                        values[name] = stat.get("value")
                parsed.append({"team": team_name, "values": values})
            stats_by_fixture[str(item["fixtureId"])] = parsed
        except Exception as exc:
            diagnostics.append(f"Statystyki {item['home']} — {item['away']}: {exc}")

    h2h_by_match = {}
    h2h_pairs = set()
    h2h_count = 0
    for item in verified:
        home_id, away_id = item.get("homeTeamId"), item.get("awayTeamId")
        if not home_id or not away_id or h2h_count >= MAX_H2H_CALLS:
            continue
        pair = tuple(sorted((home_id, away_id)))
        if pair in h2h_pairs:
            continue
        h2h_pairs.add(pair)
        try:
            payload = api_get("/fixtures/headtohead", {
                "h2h": f"{home_id}-{away_id}",
                "last": 10,
                "timezone": "Europe/Warsaw",
            })
            games = []
            for raw in payload.get("response", []):
                fixture = raw.get("fixture") or {}
                teams = raw.get("teams") or {}
                goals = raw.get("goals") or {}
                h = teams.get("home") or {}
                a = teams.get("away") or {}
                games.append({
                    "fixtureId": fixture.get("id"),
                    "date": fixture.get("date"),
                    "home": h.get("name"),
                    "away": a.get("name"),
                    "homeGoals": goals.get("home"),
                    "awayGoals": goals.get("away"),
                    "status": (fixture.get("status") or {}).get("short"),
                })
            h2h_by_match[str(item["matchId"])] = games
            h2h_count += 1
        except Exception as exc:
            diagnostics.append(f"H2H {item['home']} — {item['away']}: {exc}")

    for item in verified:
        fixture_id = str(item.get("fixtureId"))
        match_id = str(item.get("matchId"))
        if fixture_id in stats_by_fixture:
            item["statistics"] = stats_by_fixture[fixture_id]
        if match_id in h2h_by_match:
            item["h2h"] = h2h_by_match[match_id]

    result = {
        "generatedAt": datetime.now(WARSAW).isoformat(),
        "source": "API-Football",
        "verifiedFixtures": verified,
        "verifiedCount": len(verified),
        "checkedCount": len(matches),
        "statisticsCount": len(stats_by_fixture),
        "h2hCount": len(h2h_by_match),
        "diagnostics": diagnostics,
        "requestBudget": {
            "dateCallsMax": 3,
            "statisticsCallsMax": MAX_STATS_CALLS,
            "h2hCallsMax": MAX_H2H_CALLS,
            "note": "Maksymalnie 13 żądań w tym skrypcie na jedno uruchomienie; API może naliczać je zgodnie z własnym limitem.",
        },
        "note": "Weryfikacja pomocnicza. Niedopasowane spotkania nie są łączone automatycznie.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"API-Football: zweryfikowano {len(verified)}/{len(matches)} spotkań; "
        f"statystyki {len(stats_by_fixture)}, H2H {len(h2h_by_match)}."
    )
    for diagnostic in diagnostics:
        print(diagnostic)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"API-Football enrichment failed: {exc}", file=sys.stderr)
        raise
