#!/usr/bin/env python3
"""Sportmonks Football API v3 supplemental fixtures feed.

Reads SPORTMONKS_API_TOKEN (GitHub Actions secret SPORTMONKS).
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
    home = away = home_id = away_id = None
    for participant in participants:
        meta = participant.get("meta") or {}
        location = meta.get("location")
        name = participant.get("name")
        if location == "home":
            home, home_id = name, participant.get("id")
        elif location == "away":
            away, away_id = name, participant.get("id")
    if not home and participants:
        home, home_id = participants[0].get("name"), participants[0].get("id")
    if not away and len(participants) > 1:
        away, away_id = participants[1].get("name"), participants[1].get("id")
    return home, away, home_id, away_id


def compact_scores(rows):
    """Keep only score labels, participant and goal values from provider responses."""
    result = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        score = row.get("score")
        score = score if isinstance(score, dict) else {}
        kind = row.get("description") or row.get("type") or row.get("name")
        if isinstance(kind, dict):
            kind = kind.get("name") or kind.get("description")
        goals = score.get("goals")
        if goals is None:
            goals = row.get("goals")
        if goals is None and row.get("score") is not None and not isinstance(row.get("score"), dict):
            goals = row.get("score")
        participant = score.get("participant") or row.get("participant") or row.get("participant_id")
        if goals is not None or kind or participant is not None:
            result.append({
                "description": str(kind)[:48] if kind is not None else None,
                "participant": participant,
                "goals": goals,
            })
    return result[:16]


def compact_statistics(rows):
    """Retain only small, useful match-stat fields; discard provider metadata blobs."""
    allowed = ("shot", "corner", "card", "offside", "foul", "possession", "save", "attack")
    result = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        kind = row.get("type") or {}
        if isinstance(kind, dict):
            name = kind.get("name") or kind.get("developer_name") or kind.get("code")
        else:
            name = kind
        name = str(name or row.get("name") or "").strip()
        if not name or not any(term in name.casefold() for term in allowed):
            continue
        data = row.get("data")
        if isinstance(data, dict):
            value = data.get("value")
            if value is None:
                value = data.get("total")
            if value is None:
                value = data.get("percentage")
            if value is None:
                value = data.get("home")
        else:
            value = data if data is not None else row.get("value")
        if value is None or isinstance(value, (dict, list)):
            continue
        result.append({
            "type": name[:64],
            "value": value,
            "participantId": row.get("participant_id") or row.get("participantId"),
        })
    return result[:80]


def compact_saved_fixture(item):
    """Trim previous feed rows too, so an API outage cannot preserve a bloated legacy file."""
    return {
        "fixtureId": item.get("fixtureId"),
        "home": item.get("home"),
        "away": item.get("away"),
        "homeId": item.get("homeId"),
        "awayId": item.get("awayId"),
        "kickoff": item.get("kickoff"),
        "date": item.get("date"),
        "time": item.get("time"),
        "league": item.get("league"),
        "leagueId": item.get("leagueId"),
        "status": item.get("status"),
        "scores": compact_scores(item.get("scores")),
        "statistics": compact_statistics(item.get("statistics")),
        "source": "Sportmonks",
    }


def parse_fixture(item):
    home, away, home_id, away_id = relation_names(item)
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
        "homeId": home_id,
        "awayId": away_id,
        "kickoff": local.isoformat(),
        "date": local.date().isoformat(),
        "time": local.strftime("%H:%M"),
        "league": league.get("name"),
        "leagueId": league.get("id"),
        "status": state.get("name") or state.get("short_name"),
        "scores": compact_scores(item.get("scores")),
        "statistics": compact_statistics(item.get("statistics")),
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
            "Brak SPORTMONKS_API_TOKEN. Dodaj token w GitHub Secrets jako SPORTMONKS; "
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
        previous_by_date.setdefault(fixture.get("date"), []).append(compact_saved_fixture(fixture))

    today = datetime.now(WARSAW).date()
    dates = [(today + timedelta(days=i)).isoformat() for i in range(7)]
    fixtures, diagnostics, failed_dates = [], [], []
    # Odds/events/referee includes can produce huge nested payloads but are not required
    # by the cards. Request compact fixture fields and selected match statistics only.
    includes = "participants;league;state;scores;statistics.type"
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

    # This provider owns only data/sportmonks.json. Keeping it independent from
    # data/latest.json prevents concurrent workflows from overwriting each other's commits.
    print(
        "Sportmonks: feed kompaktowy; "
        f"{len(fixtures)} spotkań, rozmiar {OUTPUT.stat().st_size // 1024} KB."
    )
    print(f"Zapisano {OUTPUT}: {len(fixtures)} spotkań.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Sportmonks integration failed: {exc}", file=sys.stderr)
        raise
