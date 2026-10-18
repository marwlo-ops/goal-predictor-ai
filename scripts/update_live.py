import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_URL = "https://api.football-data.org/v4"
TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
WARSAW = ZoneInfo("Europe/Warsaw")
OUTPUT = Path("data/live.json")
LIVE_STATUSES = "LIVE"


def main():
    if not TOKEN:
        raise RuntimeError("Brak sekretu FOOTBALL_DATA_TOKEN.")

    url = BASE_URL + "/matches?" + urllib.parse.urlencode({"status": LIVE_STATUSES})
    request = urllib.request.Request(url, headers={"X-Auth-Token": TOKEN})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"API HTTP {exc.code}: {detail}") from exc

    matches = []
    for item in payload.get("matches", []):
        score = item.get("score") or {}
        current = score.get("fullTime") or {}
        competition = item.get("competition") or {}
        home = item.get("homeTeam") or {}
        away = item.get("awayTeam") or {}
        matches.append({
            "id": item.get("id"),
            "league": competition.get("code"),
            "leagueName": competition.get("name") or competition.get("code"),
            "home": home.get("name"),
            "away": away.get("name"),
            "status": item.get("status"),
            "minute": item.get("minute"),
            "score": {"home": current.get("home"), "away": current.get("away")},
            "utcDate": item.get("utcDate"),
            "updatedAt": item.get("lastUpdated"),
        })

    result = {
        "updatedAt": datetime.now(WARSAW).isoformat(),
        "source": "football-data.org",
        "refreshIntervalMinutes": 10,
        "count": len(matches),
        "matches": matches,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Zapisano {len(matches)} meczów live do {OUTPUT}")


if __name__ == "__main__":
    main()
