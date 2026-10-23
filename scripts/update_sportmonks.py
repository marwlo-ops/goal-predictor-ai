#!/usr/bin/env python3
"""Sportmonks Football API v3 supplemental fixtures feed.

Reads SPORTMONKS_API_TOKEN (GitHub Actions secret NEWAPT).
The integration enriches matching fixtures and never invents predictions.
"""
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TOKEN = os.environ.get("SPORTMONKS_API_TOKEN", "").strip()
BASE = "https://api.sportmonks.com/v3/football"
WARSAW = ZoneInfo("Europe/Warsaw")
UTC = ZoneInfo("UTC")
LATEST = Path("data/latest.json")
OUTPUT = Path("data/sportmonks.json")
MAX_PAGES_PER_DATE = 20


def get(path, params=None):
    params = dict(params or {})
    params["api_token"] = TOKEN
    url = BASE + path + "?" + urllib.parse.urlencode(params, safe=";,")
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "GoalPredictorAI/1.1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Sportmonks HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Sportmonks connection error: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Sportmonks zwrócił nieoczekiwany format JSON.")
    if payload.get("message") and payload.get("errors"):
        raise RuntimeError("Sportmonks API: " + str(payload["message"])[:300])
    return payload


def fetch_date(day, includes):
    """Fetch every page (API defaults to 25 rows; request 50 per page)."""
    all_rows = []
    diagnostics = []
    for page in range(1, MAX_PAGES_PER_DATE + 1):
        payload = get(
            "/fixtures/date/" + day,
            {"include": includes, "per_page": 50, "page": page},
        )
        rows = payload.get("data") or []
        if not isinstance(rows, list):
            raise RuntimeError(f"Sportmonks {day}: pole data nie jest listą.")
        all_rows.extend(rows)
        pagination = payload.get("pagination") or (payload.get("meta") or {}).get("pagination") or {}
        has_more = pagination.get("has_more")
        diagnostics.append({"page": page, "count": len(rows)})
        if has_more is False or not rows or (has_more is None and len(rows) < 50):
            return all_rows, diagnostics
    raise RuntimeError(
        f"Sportmonks {day}: osiągnięto limit {MAX_PAGES_PER_DATE} stron; "
        "odmawiam publikacji niepełnego terminarza."
    )


def relation_names(item):
    participants = item.get("participants") or []
    home = away = None
    for participant in participants:
        meta = participant.get("meta") or {}
        location = meta.get("location")
        name = participant.get("name")
        if location == "home":
            home = name
        elif location == "away":
            away = name
    if not home and participants:
        home = participants[0].get("name")
    if not away and len(participants) > 1:
        away = participants[1].get("name")
    return home, away


def parse_fixture(item):
    home, away = relation_names(item)
    starting = item.get("starting_at")
    if not home or not away or not starting:
        return None
    try:
        dt = datetime.fromisoformat(str(starting).replace("Z", "+00:00"))
        # Do not request a local timezone from the API: naive API timestamps are UTC.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        local = dt.astimezone(WARSAW)
    except (TypeError, ValueError):
        return None
    league = item.get("league") or {}
    state = item.get("state") or {}
    return {
        "fixtureId": item.get("id"),
        "home": home,
        "away": away,
        "kickoff": local.isoformat(),
        "date": local.date().isoformat(),
        "time": local.strftime("%H:%M"),
        "league": league.get("name"),
        "leagueId": league.get("id"),
        "status": state.get("name") or state.get("short_name"),
        "scores": item.get("scores") or [],
        "statistics": item.get("statistics") or [],
        "events": item.get("events") or [],
        "referees": item.get("referees") or [],
        "odds": item.get("odds") or [],
        "predictions": item.get("predictions") or [],
        "source": "Sportmonks",
    }


def normalize_name(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    # Common club-name suffixes often differ between data providers.
    value = re.sub(r"\b(fc|cf|afc|sc|club)\b", " ", value)
    return " ".join(value.split())


def fixture_key(match):
    return (
        str(match.get("date") or ""),
        normalize_name(match.get("home")),
        normalize_name(match.get("away")),
    )


def main():
    if not TOKEN:
        raise RuntimeError(
            "Brak SPORTMONKS_API_TOKEN. Dodaj token w GitHub Secrets jako NEWAPT; "
            "nie publikuję pustego feedu."
        )

    previous_feed = {}
    if OUTPUT.exists():
        try:
            previous_feed = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous_feed = {}
    previous_fixtures = previous_feed.get("fixtures") or []
    previous_by_date = {}
    for fixture in previous_fixtures:
        previous_by_date.setdefault(fixture.get("date"), []).append(fixture)

    today = datetime.now(WARSAW).date()
    dates = [(today + timedelta(days=i)).isoformat() for i in range(7)]
    fixtures, diagnostics, failed_dates = [], [], []
    includes = "participants;league;state;scores;statistics.type;events.type;referees;odds"
    for day in dates:
        try:
            rows, pages = fetch_date(day, includes)
            parsed = [parse_fixture(item) for item in rows]
            fixtures.extend(item for item in parsed if item)
            diagnostics.append({"date": day, "count": len(rows), "parsed": sum(x is not None for x in parsed), "pages": pages, "ok": True})
        except Exception as exc:
            failed_dates.append(day)
            diagnostics.append({"date": day, "ok": False, "error": str(exc)[:300]})
            print(f"Sportmonks {day}: {exc}", file=sys.stderr)
            # Preserve the previous day's data on transient API errors.
            fixtures.extend(previous_by_date.get(day, []))

    if not any(item.get("ok") for item in diagnostics):
        raise RuntimeError("Wszystkie zapytania Sportmonks nie powiodły się; zachowuję poprzednie dane.")

    unique = {}
    for item in fixtures:
        fixture_id = item.get("fixtureId")
        if fixture_id is not None:
            unique[str(fixture_id)] = item
    fixtures = sorted(unique.values(), key=lambda x: (x.get("kickoff", ""), x.get("league") or ""))
    result = {
        "generatedAt": datetime.now(WARSAW).isoformat(),
        "source": "Sportmonks Football API v3",
        "count": len(fixtures),
        "fixtures": fixtures,
        "diagnostics": diagnostics,
        "failedDates": failed_dates,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if LATEST.exists():
        latest = json.loads(LATEST.read_text(encoding="utf-8"))
        # Remove only rows previously created by this integration, then rebuild them
        # from the current feed. This keeps repeated runs idempotent and expires stale rows.
        matches = [
            m for m in (latest.get("matches") or [])
            if not str(m.get("id") or "").startswith("sportmonks-")
        ]
        by_key = {fixture_key(m): m for m in matches}
        extras = []
        matched_ids = set()
        for fixture in fixtures:
            key = fixture_key(fixture)
            existing = by_key.get(key)
            if existing is not None:
                existing["sportmonks"] = fixture
                sources = existing.get("dataSources") or []
                existing["dataSources"] = sorted(set(sources + ["Sportmonks"]))
                matched_ids.add(str(fixture.get("fixtureId")))
            else:
                extras.append({
                    "id": "sportmonks-" + str(fixture.get("fixtureId")),
                    "source": "Sportmonks",
                    "league": "SM",
                    "leagueName": fixture.get("league") or "Sportmonks",
                    "date": fixture["date"],
                    "time": fixture["time"],
                    "kickoff": fixture["kickoff"],
                    "home": fixture["home"],
                    "away": fixture["away"],
                    "hx": None,
                    "ax": None,
                    "probabilities": None,
                    "model": "Tylko terminarz Sportmonks",
                    "modelStatus": "fixture_only",
                    "quality": "insufficient_data",
                    "confidence": "Brak prognozy — brak danych wystarczających dla modelu",
                    "history": {"homeLast10": {"matches": [], "stats": None}, "awayLast10": {"matches": [], "stats": None}, "h2h": []},
                    "sportmonks": fixture,
                    "dataSources": ["Sportmonks"],
                })
        latest["matches"] = matches + extras
        latest["count"] = len(latest["matches"])
        latest["sportmonksData"] = {
            "generatedAt": result["generatedAt"],
            "count": len(fixtures),
            "matchedCount": len(matched_ids),
            "additionalCount": len(extras),
            "failedDates": failed_dates,
        }
        LATEST.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Sportmonks: {len(fixtures)} spotkań; {len(matched_ids)} wzbogaconych, {len(extras)} dodatkowych.")
    print(f"Zapisano {OUTPUT}: {len(fixtures)} spotkań.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Sportmonks integration failed: {exc}", file=sys.stderr)
        raise
