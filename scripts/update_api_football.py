#!/usr/bin/env python3
"""Supplemental fixture verification using API-Football.

Reads the key from GitHub Actions secrets only. Does not expose credentials,
does not replace football-data.org predictions, and only links fixtures when
date and normalized home/away names match exactly.
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

    api_fixtures = []
    diagnostics = []
    for date in dates[:3]:
        payload = api_get("/fixtures", {"date": date, "timezone": "Europe/Warsaw"})
        response = payload.get("response", [])
        api_fixtures.extend(response)
        diagnostics.append(f"{date}: {len(response)} spotkań zwróconych przez API-Football")

    indexed = {}
    for raw in api_fixtures:
        fixture = raw.get("fixture") or {}
        teams = raw.get("teams") or {}
        home = (teams.get("home") or {}).get("name")
        away = (teams.get("away") or {}).get("name")
        kickoff = fixture.get("date")
        if not home or not away or not kickoff:
            continue
        indexed[(kickoff[:10], norm(home), norm(away))] = {
            "fixtureId": fixture.get("id"),
            "kickoff": kickoff,
            "status": (fixture.get("status") or {}).get("short"),
            "elapsed": (fixture.get("status") or {}).get("elapsed"),
            "home": home,
            "away": away,
            "venue": (fixture.get("venue") or {}).get("name"),
            "referee": fixture.get("referee"),
            "league": (raw.get("league") or {}).get("name"),
            "season": (raw.get("league") or {}).get("season"),
        }

    verified = []
    for match in matches:
        key = (match.get("date", ""), norm(match.get("home")), norm(match.get("away")))
        supplemental = indexed.get(key)
        if supplemental:
            verified.append({
                "matchId": match.get("id"),
                **supplemental,
                "source": "API-Football",
            })

    result = {
        "generatedAt": datetime.now(WARSAW).isoformat(),
        "source": "API-Football",
        "verifiedFixtures": verified,
        "verifiedCount": len(verified),
        "checkedCount": len(matches),
        "diagnostics": diagnostics,
        "note": "Dopasowanie wymaga zgodnej daty i nazw obu drużyn. Brak dopasowania nie oznacza błędu meczu.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"API-Football: zweryfikowano {len(verified)}/{len(matches)} spotkań.")
    for diagnostic in diagnostics:
        print(diagnostic)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"API-Football enrichment failed: {exc}", file=sys.stderr)
        raise
