import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_URL = "https://api.football-data.org/v4"
TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
WARSAW = ZoneInfo("Europe/Warsaw")
OUTPUT = Path("data/results.json")


def main():
    if not TOKEN:
        raise RuntimeError("Brak sekretu FOOTBALL_DATA_TOKEN.")
    today = datetime.now(WARSAW).date()
    date_from = (today - timedelta(days=7)).isoformat()
    date_to = today.isoformat()
    params = urllib.parse.urlencode({"dateFrom": date_from, "dateTo": date_to, "status": "FINISHED"})
    request = urllib.request.Request(
        f"{BASE_URL}/matches?{params}",
        headers={"X-Auth-Token": TOKEN},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"API HTTP {exc.code}: {detail}") from exc

    matches = []
    for item in payload.get("matches", []):
        score = item.get("score") or {}
        full_time = score.get("fullTime") or {}
        home_goals, away_goals = full_time.get("home"), full_time.get("away")
        if home_goals is None or away_goals is None:
            continue
        competition = item.get("competition") or {}
        home = item.get("homeTeam") or {}
        away = item.get("awayTeam") or {}
        matches.append({
            "id": item.get("id"),
            "date": item.get("utcDate"),
            "league": competition.get("code"),
            "leagueName": competition.get("name") or competition.get("code") or "Piłka nożna",
            "home": home.get("name") or "Gospodarze",
            "away": away.get("name") or "Goście",
            "homeGoals": home_goals,
            "awayGoals": away_goals,
            "status": item.get("status"),
        })
    matches.sort(key=lambda match: match.get("date") or "", reverse=True)
    result = {
        "updatedAt": datetime.now(WARSAW).isoformat(),
        "dateFrom": date_from,
        "dateTo": date_to,
        "source": "football-data.org",
        "count": len(matches),
        "matches": matches,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Zapisano {len(matches)} zakończonych meczów z {date_from}–{date_to}.")


if __name__ == "__main__":
    main()
