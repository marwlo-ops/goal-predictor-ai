#!/usr/bin/env python3
"""Sportmonks Football API v3 supplemental fixtures feed.
Token is read from SPORTMONKS_API_TOKEN (GitHub Actions secret NEWAPT).
Never invent probabilities: Sportmonks-only fixtures are marked fixture_only.
"""
import json, os, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TOKEN = os.environ.get("SPORTMONKS_API_TOKEN", "").strip()
BASE = "https://api.sportmonks.com/v3/football"
WARSAW = ZoneInfo("Europe/Warsaw")
LATEST = Path("data/latest.json")
OUTPUT = Path("data/sportmonks.json")

def get(path, params=None):
    params = dict(params or {})
    params["api_token"] = TOKEN
    url = BASE + path + "?" + urllib.parse.urlencode(params, safe=";,:")
    req = urllib.request.Request(url, headers={"Accept":"application/json","User-Agent":"GoalPredictorAI/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Sportmonks HTTP {exc.code}: {detail}") from exc
    if payload.get("message") and not payload.get("data"):
        raise RuntimeError("Sportmonks API: " + str(payload["message"])[:300])
    return payload

def relation_names(item):
    participants = item.get("participants") or []
    home = away = None
    for participant in participants:
        meta = participant.get("meta") or {}
        location = meta.get("location")
        name = participant.get("name")
        if location == "home": home = name
        elif location == "away": away = name
    if not home and len(participants) > 0: home = participants[0].get("name")
    if not away and len(participants) > 1: away = participants[1].get("name")
    return home, away

def parse_fixture(item):
    home, away = relation_names(item)
    starting = item.get("starting_at")
    if not home or not away or not starting: return None
    try:
        dt = datetime.fromisoformat(starting.replace("Z","+00:00"))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        local = dt.astimezone(WARSAW)
    except ValueError:
        return None
    league = item.get("league") or {}
    state = item.get("state") or {}
    scores = item.get("scores") or []
    score_values = []
    for score in scores:
        desc = str((score.get("description") or "")).lower()
        participant = score.get("score") or {}
        if desc in ("current", "2nd-half", "1st-half", "fulltime", "full-time"):
            score_values.append(participant.get("goals"))
    return {
        "fixtureId": item.get("id"), "home": home, "away": away,
        "kickoff": local.isoformat(), "date": local.date().isoformat(),
        "time": local.strftime("%H:%M"), "league": league.get("name"),
        "leagueId": league.get("id"), "status": state.get("name") or state.get("short_name"),
        "scores": scores, "statistics": item.get("statistics") or [],
        "events": item.get("events") or [], "referees": item.get("referees") or [],
        "odds": item.get("odds") or [], "predictions": item.get("predictions") or [],
        "source": "Sportmonks"
    }

def main():
    if not TOKEN:
        print("Brak SPORTMONKS_API_TOKEN (GitHub secret NEWAPT) — pomijam Sportmonks.")
        return 0
    today = datetime.now(WARSAW).date()
    dates = [(today + timedelta(days=i)).isoformat() for i in range(7)]
    fixtures, diagnostics = [], []
    # One call per date; request only data relevant to match cards/analysis.
    includes = "participants;league;state;scores;statistics;events;referees;odds;predictions"
    for day in dates:
        try:
            payload = get("/fixtures/date/" + day, {"include": includes, "timezone": "Europe/Warsaw"})
            rows = payload.get("data") or []
            fixtures.extend(x for x in (parse_fixture(item) for item in rows) if x)
            diagnostics.append({"date":day,"count":len(rows),"ok":True})
        except Exception as exc:
            diagnostics.append({"date":day,"ok":False,"error":str(exc)[:300]})
            print(f"Sportmonks {day}: {exc}", file=sys.stderr)
    # Fail closed if every date failed: do not publish an empty feed over working data.
    if not any(x["ok"] for x in diagnostics):
        raise RuntimeError("Wszystkie zapytania Sportmonks nie powiodły się; zachowuję poprzedni feed.")
    unique = {}
    for item in fixtures:
        unique[str(item["fixtureId"])] = item
    fixtures = sorted(unique.values(), key=lambda x:(x["kickoff"],x["league"] or ""))
    result = {"generatedAt":datetime.now(WARSAW).isoformat(),"source":"Sportmonks Football API v3",
              "count":len(fixtures),"fixtures":fixtures,"diagnostics":diagnostics}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")

    if LATEST.exists():
        latest = json.loads(LATEST.read_text(encoding="utf-8"))
        matches = latest.get("matches") or []
        def norm(s): return " ".join(str(s or "").lower().replace("&","and").split())
        by_key = {(m.get("date"),norm(m.get("home")),norm(m.get("away"))):m for m in matches}
        extra = []
        for fixture in fixtures:
            key=(fixture["date"],norm(fixture["home"]),norm(fixture["away"]))
            if key in by_key:
                by_key[key]["sportmonks"] = fixture
                by_key[key]["dataSources"] = sorted(set(by_key[key].get("dataSources",[]) + ["Sportmonks"]))
            else:
                extra.append({
                    "id":"sportmonks-"+str(fixture["fixtureId"]), "source":"Sportmonks",
                    "league":"SM", "leagueName":fixture.get("league") or "Sportmonks",
                    "date":fixture["date"],"time":fixture["time"],"kickoff":fixture["kickoff"],
                    "home":fixture["home"],"away":fixture["away"],"hx":None,"ax":None,
                    "probabilities":None,"model":"Tylko terminarz Sportmonks",
                    "modelStatus":"fixture_only","quality":"insufficient_data",
                    "confidence":"Brak prognozy — brak danych wystarczających dla modelu",
                    "history":{"homeLast10":{"matches":[],"stats":None},"awayLast10":{"matches":[],"stats":None},"h2h":[]},
                    "sportmonks":fixture,"dataSources":["Sportmonks"]
                })
        if extra:
            latest["matches"] = matches + extra
            latest["count"] = len(latest["matches"])
        latest["sportmonksData"]={"generatedAt":result["generatedAt"],"count":len(fixtures),
                                  "matchedCount":len(fixtures)-len(extra),"additionalCount":len(extra)}
        LATEST.write_text(json.dumps(latest,ensure_ascii=False,indent=2),encoding="utf-8")
        print(f"Sportmonks: {len(fixtures)} fixtures; {len(extra)} dodanych bez sztucznej prognozy.")
    print(f"Zapisano {OUTPUT}: {len(fixtures)} spotkań.")
    return 0

if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"Sportmonks integration failed: {exc}",file=sys.stderr)
        raise
