
import json
import math
import os
import urllib.request
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "latest.json"
TZ = ZoneInfo("Europe/Warsaw")

LEAGUES = {
    "PL": "Premier League",
    "PD": "LaLiga",
    "SA": "Serie A",
    "BL1": "Bundesliga",
    "DED": "Eredivisie",
    "BSA": "Brasileirao",
    "FL1": "Ligue 1",
    "CL": "Liga Mistrzów",
}

def get_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "X-Auth-Token": TOKEN,
            "User-Agent": "GoalPredictorAI/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP {exc.code}: {details[:300]}"
        ) from exc

def poisson(k, x):
    return math.exp(-x) * x**k / math.factorial(k)

def predict(home_xg, away_xg):
    home = draw = away = 0.0
    over15 = over25 = btts = 0.0

    for h in range(10):
        for a in range(10):
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
        "home": round(home, 4),
        "draw": round(draw, 4),
        "away": round(away, 4),
        "over15": round(over15, 4),
        "over25": round(over25, 4),
        "btts": round(btts, 4),
    }

def main():
    if not TOKEN:
        raise RuntimeError(
            "Brak sekretu FOOTBALL_DATA_TOKEN w GitHub Actions."
        )

    now = datetime.now(TZ)
    today = now.date().isoformat()
    matches = []
    diagnostics = []

    print("Data:", today)
    print("Strefa czasowa: Europe/Warsaw")
    print("Filtr godzin: 15:00–21:59")

    for code, league in LEAGUES.items():
        url = (
            "https://api.football-data.org/v4/competitions/"
            + code
            + "/matches?dateFrom="
            + today
            + "&dateTo="
            + today
        )

        try:
            data = get_json(url)
            all_matches = data.get("matches", [])

            print(
                f"DIAGNOSTYKA {league}: "
                f"API zwróciło {len(all_matches)} meczów"
            )

            kept = 0

            for match in all_matches:
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

                home_team = match.get("homeTeam", {})
                away_team = match.get("awayTeam", {})

                # Tymczasowe założenia modelu, nie rzeczywiste xG.
                home_xg = 1.45
                away_xg = 1.15

                matches.append({
                    "id": str(match.get("id", "")),
                    "league": code,
                    "leagueName": league,
                    "time": dt.strftime("%H:%M"),
                    "kickoff": dt.isoformat(),
                    "home": home_team.get("name", "Gospodarze"),
                    "away": away_team.get("name", "Goście"),
                    "hx": home_xg,
                    "ax": away_xg,
                    "probabilities": predict(home_xg, away_xg),
                })

                kept += 1

            diagnostics.append({
                "league": league,
                "apiMatches": len(all_matches),
                "selectedMatches": kept,
                "error": None,
            })

        except Exception as exc:
            message = str(exc)
            print(f"BŁĄD API {league}: {message}")

            diagnostics.append({
                "league": league,
                "apiMatches": None,
                "selectedMatches": 0,
                "error": message,
            })

    matches.sort(key=lambda m: m["kickoff"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({
            "generatedAt": now.isoformat(),
            "date": today,
            "timezone": "Europe/Warsaw",
            "count": len(matches),
            "matches": matches,
            "diagnostics": diagnostics,
            "note": (
                "Terminarz pochodzi z football-data.org. "
                "Prognozy używają tymczasowych założeń dotyczących "
                "goli, a nie zweryfikowanych statystyk xG. "
                "Nie są gwarancją wyniku."
            ),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Łącznie wybranych meczów:", len(matches))
    print("Zapisano plik:", OUT)

if __name__ == "__main__":
    main()
    
