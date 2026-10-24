#!/usr/bin/env python3
"""Supplemental API-Football fixture verification and match-statistics feed.

API key is read only from the API_FOOTBALL_KEY environment variable.
Budget guard: up to 3 date calls, 4 H2H calls, and 6 statistics calls per run.
"""
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
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
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("&", " and ")
    value = re.sub(r"\b(fc|cf|afc|sc|club)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def main():
    if not KEY:
        print("API_FOOTBALL_KEY nie ustawiony — pomijam weryfikację pomocniczą.")
        return 0
    if not INPUT.exists():
        raise RuntimeError("Brak data/latest.json; najpierw wygeneruj terminarz.")

    latest = json.loads(INPUT.read_text(encoding="utf-8"))
    raw_matches = latest.get("matches") or []
    # Preserve existing predictions and remove stale provider-only rows from homepage data.
    matches = [
        m for m in raw_matches
        if not str(m.get("id") or "").startswith(("sportmonks-", "api-football-"))
        and isinstance(m.get("probabilities"), dict)
        and m.get("modelStatus") != "fixture_only"
    ]
    today = datetime.now(WARSAW).date()
    # API-Football Free restricts the accessible fixture-date window. Query only
    # today's local fixtures rather than failing the entire feed on future dates.
    dates = [today.isoformat()]

    raw_fixtures = []
    diagnostics = []
    successful_dates = 0
    for date in dates:
        try:
            payload = api_get("/fixtures", {"date": date, "timezone": "Europe/Warsaw"})
            response = payload.get("response", [])
            if not isinstance(response, list):
                raise RuntimeError("API-Football returned a non-list response.")
            raw_fixtures.extend(response)
            successful_dates += 1
            diagnostics.append(f"{date}: {len(response)} spotkań w API-Football")
        except Exception as exc:
            message = f"{date}: BŁĄD TERMINARZA: {str(exc)[:220]}"
            diagnostics.append(message)
            print("API-Football: " + message, file=sys.stderr)

    if not successful_dates:
        raise RuntimeError(
            "API-Football nie udostępnił terminarza dla dozwolonej daty; "
            "zachowuję poprzednie dane zamiast publikować pusty feed."
        )

    indexed = {}
    for raw in raw_fixtures:
        fixture = raw.get("fixture") or {}
        teams = raw.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        kickoff = fixture.get("date")
        if not home.get("name") or not away.get("name") or not kickoff:
            continue
        try:
            kickoff_dt = datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
            if kickoff_dt.tzinfo is None:
                kickoff_dt = kickoff_dt.replace(tzinfo=ZoneInfo("UTC"))
            local_kickoff = kickoff_dt.astimezone(WARSAW)
        except (TypeError, ValueError):
            continue
        kickoff_local = local_kickoff.isoformat()
        indexed[(local_kickoff.date().isoformat(), norm(home["name"]), norm(away["name"]))] = {
            "fixtureId": fixture.get("id"),
            "kickoff": kickoff_local,
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

    # Add API-Football-only fixtures for requested dates, without time filtering.
    # These are fixture-only: no probabilities or xG are invented.
    existing_keys = {(m.get("date", ""), norm(m.get("home")), norm(m.get("away"))) for m in matches}
    additional = []
    for key, item in indexed.items():
        date, home_norm, away_norm = key
        if date not in dates[:7] or key in existing_keys:
            continue
        try:
            kickoff = datetime.fromisoformat(item["kickoff"].replace("Z", "+00:00")).astimezone(WARSAW)
        except (TypeError, ValueError):
            continue
        api_id = "api-football-" + str(item["fixtureId"])
        extra = {
            "id": api_id, "source": "API-Football", "league": "API-Football",
            "leagueName": item.get("league") or "Mecz z API-Football",
            "date": kickoff.date().isoformat(), "time": kickoff.strftime("%H:%M"),
            "kickoff": kickoff.isoformat(), "home": item["home"], "away": item["away"],
            "hx": None, "ax": None, "probabilities": None,
            "history": {"homeLast10": {"matches": [], "stats": None}, "awayLast10": {"matches": [], "stats": None}, "h2h": []},
            "model": "Tylko terminarz API-Football", "modelStatus": "fixture_only",
            "quality": "insufficient_data", "confidence": "Brak prognozy: brak zweryfikowanych danych modelu",
            "apiFootballVerified": item,
        }
        additional.append(extra)
        verified.append({"matchId": api_id, **item, "source": "API-Football"})
        existing_keys.add(key)
    additional.sort(key=lambda item: (item["date"], item["time"], item["leagueName"]))
    # Fixtures unavailable to the model stay in this feed, not in latest.json.
    latest["matches"] = matches
    latest["count"] = len(matches)
    latest["apiFootballAdditionalCount"] = len(additional)
    latest["apiFootballFixtureOnlyCount"] = len(additional)
    INPUT.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Dodatkowe mecze API-Football przechowane tylko w feedzie źródłowym: " + str(len(additional)) + ".")

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
    # Enrich fixtures lacking a model first, then existing fixtures.
    match_lookup = {str(match.get("id")): match for match in latest.get("matches", [])}
    ordered_for_h2h = sorted(verified, key=lambda item: 0 if match_lookup.get(str(item.get("matchId")), {}).get("modelStatus") == "fixture_only" else 1)
    for item in ordered_for_h2h:
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

    for item in verified:
        match_id = str(item.get("matchId"))
        if not match_id.startswith("api-football-"):
            continue
        for match in latest.get("matches", []):
            if str(match.get("id")) == match_id:
                match["apiFootballVerified"] = {
                    "fixtureId": item.get("fixtureId"), "status": item.get("status"),
                    "elapsed": item.get("elapsed"), "league": item.get("league"),
                    "venue": item.get("venue"), "referee": item.get("referee"),
                    "statistics": item.get("statistics", []), "h2h": item.get("h2h", []),
                }
                break

    # Persist consolidated fixture data even if API-Football added no new fixtures.
    result = {
        "generatedAt": datetime.now(WARSAW).isoformat(),
        "source": "API-Football",
        "verifiedFixtures": verified,
        "fixtureOnly": additional,
        "fixtureOnlyCount": len(additional),
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
    latest["apiFootballData"] = {key: result[key] for key in ("generatedAt", "source", "verifiedCount", "checkedCount", "statisticsCount", "h2hCount")}
    INPUT.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
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
