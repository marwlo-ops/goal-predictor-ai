import json
import math
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "latest.json"
TZ = ZoneInfo("Europe/Warsaw")

LEAGUES = {
    "PL": "Premier League",
    "PD": "LaLiga",
    "SA": "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "CL": "Liga Mistrzów",
}

def get_json(url):
    req = urllib.request.Request(
        url,
        headers={"X-Auth-Token": TOKEN}
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))

def poisson(k, x):
    return math.exp(-x) * x**k / math.factorial(k)

def predict(home_xg, away_xg):
    home = draw = away = 0.0
    over15 = over25 = btts = 0.0

    for h in range(9):
        for a in range(9):
            p = poisson(h, home_xg) * poisson(a, away_xg)

            if h > a:
                home += p
            elif h == a:
                draw += p
            else:
                away += p

            if h + a >= 2:
                over15 += p
            if h + a >= 3:
                over25 += p
            if h > 0 and a > 0:
                btts += p

    return {
        "home": home,
        "draw": draw,
        "away": away,
        "over15": over15,
        "over25": over25,
        "btts": btts,
    }

def main():
    if not TOKEN:
        raise RuntimeError("Brak sekretu FOOTBALL_DATA_TOKEN")

    now = datetime.now(TZ)
    today = now.date().isoformat()
    matches = []

    for code, league in LEAGUES.items():
        try:
            url = (
                "https://api.football-data.org/v4/competitions/"
                + code + "/matches?dateFrom=" + today
                + "&dateTo=" + today
            )
            data = get_json(url)

            for match in data.get("matches", []):
                if match.get("status") not in ("SCHEDULED", "TIMED"):
                    continue

                kickoff = match.get("utcDate")
                if not kickoff:
                    continue

                dt = datetime.fromisoformat(
                    kickoff.replace("Z", "+00:00")
                ).astimezone(TZ)

                if not (15 <= dt.hour < 22):
                    continue

                # Bazowe wartości modelowe. W kolejnej wersji
                # zastąpimy je estymacją z historii drużyn.
                hx, ax = 1.45, 1.15
                probs = predict(hx, ax)

                matches.append({
                    "id": str(match.get("id", "")),
                    "league": code,
                    "leagueName": league,
                    "time": dt.strftime("%H:%M") + " • Polska",
                    "kickoff": dt.isoformat(),
                    "home": match.get("homeTeam", {}).get(
                        "name", "Gospodarze"
                    ),
                    "away": match.get("awayTeam", {}).get(
                        "name", "Goście"
                    ),
                    "hx": hx,
                    "ax": ax,
                    "probabilities": probs,
                })

        except Exception as exc:
            print("Błąd ligi", code, str(exc))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generatedAt": now.isoformat(),
        "date": today,
        "timezone": "Europe/Warsaw",
        "count": len(matches),
        "matches": matches,
        "note": (
            "Terminarz z football-data.org. "
            "Prawdopodobieństwa są orientacyjne; "
            "wartości xG są tymczasowymi założeniami, "
            "a nie oficjalnymi statystykami."
        )
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Zapisano prognozy:", len(matches))

if __name__ == "__main__":
    main()
