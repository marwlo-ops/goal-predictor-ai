
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_URL = "https://api.football-data.org/v4"
TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
WARSAW = ZoneInfo("Europe/Warsaw")

LEAGUES = {
    "PL": "Premier League",
    "PD": "LaLiga",
    "SA": "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "DED": "Eredivisie",
    "PPL": "Primeira Liga",
    "CL": "Liga Mistrzów",
    "ELC": "Championship",
    "BSA": "Brasileirao",
    "EC": "Mistrzostwa Europy",
    "WC": "Mistrzostwa Świata",
}

OUTPUT = Path("data/latest.json")
MIN_REQUEST_INTERVAL = 6.3
last_request_time = 0.0
diagnostics = []


def api_get(path, params=None):
    """Pobiera dane z API z zachowaniem limitu zapytań."""
    global last_request_time

    if not TOKEN:
        raise RuntimeError(
            "Brak sekretu FOOTBALL_DATA_TOKEN w ustawieniach GitHub Actions."
        )

    if params:
        path += "?" + urllib.parse.urlencode(params)

    elapsed = time.monotonic() - last_request_time
    if last_request_time and elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)

    request = urllib.request.Request(
        BASE_URL + path,
        headers={
            "X-Auth-Token": TOKEN,
            "User-Agent": "Goal-Predictor-AI/1.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            last_request_time = time.monotonic()
            return result
    except urllib.error.HTTPError as exc:
        last_request_time = time.monotonic()
        if exc.code == 429:
            raise RuntimeError("Limit API przekroczony (429).") from exc
        if exc.code == 403:
            raise RuntimeError(
                "API nie udostępnia tego zasobu w obecnym planie (403)."
            ) from exc
        detail = exc.read().decode("utf-8", errors="replace")[:250]
        raise RuntimeError(f"API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Błąd połączenia z API: {exc}") from exc


def poisson_probability(lam, goals):
    if lam <= 0:
        return 1.0 if goals == 0 else 0.0
    return math.exp(-lam) * (lam ** goals) / math.factorial(goals)


def calculate_probabilities(home_xg, away_xg):
    scores = range(10)
    home_probs = [poisson_probability(home_xg, g) for g in scores]
    away_probs = [poisson_probability(away_xg, g) for g in scores]

    home_win = draw = away_win = 0.0
    over15 = over25 = btts = 0.0

    for h, ph in enumerate(home_probs):
        for a, pa in enumerate(away_probs):
            p = ph * pa

            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p

            if h + a >= 2:
                over15 += p
            if h + a >= 3:
                over25 += p
            if h >= 1 and a >= 1:
                btts += p

    total = home_win + draw + away_win
    if total:
        home_win /= total
        draw /= total
        away_win /= total

    return {
        "homeWin": round(home_win * 100, 1),
        "draw": round(draw * 100, 1),
        "awayWin": round(away_win * 100, 1),
        "over15": round(over15 * 100, 1),
        "over25": round(over25 * 100, 1),
        "btts": round(btts * 100, 1),
    }


def table_maps(data):
    """Tworzy statystyki drużyn z tabeli rozgrywek."""
    result = {"TOTAL": {}, "HOME": {}, "AWAY": {}}

    for standing in data.get("standings", []):
        kind = standing.get("type", "TOTAL")
        if kind not in result:
            continue

        for row in standing.get("table", []):
            team = row.get("team", {})
            name = team.get("name")
            played = row.get("playedGames") or 0

            if not name or played < 1:
                continue

            result[kind][name] = {
                "played": played,
                "for": row.get("goalsFor", 0) or 0,
                "against": row.get("goalsAgainst", 0) or 0,
            }

    return result


def team_stats(maps, name, venue):
    """Wybiera statystyki domowe/wyjazdowe, jeśli są dostępne."""
    stats = maps.get(venue, {}).get(name)
    if stats and stats["played"] >= 3:
        return stats, "venue"

    stats = maps.get("TOTAL", {}).get(name)
    if stats and stats["played"] >= 3:
        return stats, "total"

    return None, "missing"


def bounded(value):
    return max(0.15, min(4.0, value))


def estimate_goals(home_name, away_name, maps):
    home, home_source = team_stats(maps, home_name, "HOME")
    away, away_source = team_stats(maps, away_name, "AWAY")

    if not home or not away:
        return None

    home_for = home["for"] / home["played"]
    home_against = home["against"] / home["played"]
    away_for = away["for"] / away["played"]
    away_against = away["against"] / away["played"]

    # Połączenie ataku jednej drużyny i obrony rywala.
    home_xg = bounded((home_for + away_against) / 2)
    away_xg = bounded((away_for + home_against) / 2)

    if home_source == "venue" and away_source == "venue":
        quality = "medium"
        confidence = "Umiarkowana: dane domowe i wyjazdowe"
    else:
        quality = "low"
        confidence = "Niska: wykorzystano także dane ogólne"

    return home_xg, away_xg, quality, confidence


def get_today_matches(today):
    """Najpierw pobiera terminarz zbiorczo, a potem próbuje wariant awaryjny."""
    try:
        data = api_get("/matches", {"date": today})
        matches = data.get("matches", [])
        diagnostics.append(
            f"Terminarz zbiorczy: API zwróciło {len(matches)} meczów."
        )
        return matches
    except Exception as exc:
        diagnostics.append(f"Terminarz zbiorczy niedostępny: {exc}")
        matches = []

        for code in LEAGUES:
            try:
                data = api_get(
                    f"/competitions/{code}/matches",
                    {"dateFrom": today, "dateTo": today},
                )
                matches.extend(data.get("matches", []))
                diagnostics.append(
                    f"{LEAGUES[code]}: "
                    f"{len(data.get('matches', []))} meczów."
                )
            except Exception as league_exc:
                diagnostics.append(
                    f"{LEAGUES[code]}: błąd terminarza: {league_exc}"
                )

        return matches


def get_standings(code):
    try:
        data = api_get(f"/competitions/{code}/standings")
        maps = table_maps(data)
        teams = len(maps["TOTAL"]) + len(maps["HOME"]) + len(maps["AWAY"])
        diagnostics.append(f"{code}: pobrano tabelę ({teams} wpisów).")
        return maps
    except Exception as exc:
        diagnostics.append(f"{code}: brak tabeli: {exc}")
        return {"TOTAL": {}, "HOME": {}, "AWAY": {}}


def main():
    now = datetime.now(WARSAW)
    today = now.date().isoformat()

    print(f"Data: {today}")
    print("Strefa czasowa: Europe/Warsaw")
    print("Filtr godzin: 15:00–21:59")

    if not TOKEN:
        raise RuntimeError(
            "Nie znaleziono FOOTBALL_DATA_TOKEN. "
            "Sprawdź Settings → Secrets and variables → Actions."
        )

    all_matches = get_today_matches(today)
    selected = []

    for match in all_matches:
        competition = match.get("competition") or {}
        code = competition.get("code")

        if code not in LEAGUES:
            continue

        if match.get("status") not in ("SCHEDULED", "TIMED"):
            continue

        kickoff = match.get("utcDate")
        if not kickoff:
            continue

        try:
            kickoff_dt = datetime.fromisoformat(
                kickoff.replace("Z", "+00:00")
            ).astimezone(WARSAW)
        except ValueError:
            continue

        if kickoff_dt.date().isoformat() != today:
            continue

        if not (15 <= kickoff_dt.hour < 22):
            continue

        home = (match.get("homeTeam") or {}).get("name")
        away = (match.get("awayTeam") or {}).get("name")

        if not home or not away:
            continue

        selected.append({
            "id": match.get("id"),
            "league": code,
            "leagueName": LEAGUES[code],
            "time": kickoff_dt.strftime("%H:%M"),
            "kickoff": kickoff_dt.isoformat(),
            "home": home,
            "away": away,
        })

    selected.sort(key=lambda m: (m["kickoff"], m["leagueName"]))

    # Pobieramy tabele tylko dla lig, w których znaleziono mecze.
    standings_by_league = {}
    for code in sorted({m["league"] for m in selected}):
        standings_by_league[code] = get_standings(code)

    predictions = []

    for match in selected:
        maps = standings_by_league.get(
            match["league"],
            {"TOTAL": {}, "HOME": {}, "AWAY": {}},
        )

        estimate = estimate_goals(match["home"], match["away"], maps)

        if estimate:
            hx, ax, quality, confidence = estimate
            probabilities = calculate_probabilities(hx, ax)
            model_status = "table_based"
        else:
            # Bez wystarczających danych nie udajemy analizy statystycznej.
            hx = ax = None
            probabilities = None
            quality = "insufficient_data"
            confidence = "Brak wystarczających danych do wiarygodnej prognozy"
            model_status = "insufficient_data"

        match.update({
            "hx": round(hx, 2) if hx is not None else None,
            "ax": round(ax, 2) if ax is not None else None,
            "probabilities": probabilities,
            "model": "Poisson na podstawie tabeli" if estimate else None,
            "quality": quality,
            "confidence": confidence,
            "modelStatus": model_status,
        })
        predictions.append(match)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "generatedAt": now.isoformat(),
        "date": today,
        "timezone": "Europe/Warsaw",
        "filter": {"from": "15:00", "to": "21:59"},
        "count": len(predictions),
        "matches": predictions,
        "diagnostics": diagnostics,
        "note": (
            "Prognozy są orientacyjne i oparte na dostępnych tabelach. "
            "Nie używają kursów bukmacherskich, składów, kontuzji ani "
            "zaawansowanych statystyk. Nie stanowią gwarancji wyniku."
        ),
    }

    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Łącznie wybranych meczów: {len(predictions)}")
    print(f"Prognozy z wystarczającymi danymi: "
          f"{sum(m['probabilities'] is not None for m in predictions)}")
    print(f"Zapisano: {OUTPUT}")

    for item in diagnostics:
        print(item)


if __name__ == "__main__":
    main()
    
