
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from model_analytics import analyze_match

BASE_URL = "https://api.football-data.org/v4"
TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
WARSAW = ZoneInfo("Europe/Warsaw")
OUTPUT = Path("data/latest.json")
MIN_REQUEST_INTERVAL = 6.3
last_request_time = 0.0
diagnostics = []

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
    "EL": "Liga Europy",
    "ECL": "Liga Konferencji",
    "BL2": "2. Bundesliga",
    "BL3": "3. Liga (Niemcy)",
    "SB": "Serie B",
    "SD": "LaLiga 2",
    "FL2": "Ligue 2",
    "EL1": "League One",
    "FAC": "Puchar Anglii",
    "DFB": "Puchar Niemiec",
    "CDR": "Puchar Króla",
    "GSL": "Liga grecka",
    "MLS": "MLS",
}


def api_get(path, params=None):
    global last_request_time

    if not TOKEN:
        raise RuntimeError("Brak sekretu FOOTBALL_DATA_TOKEN.")

    if params:
        path += "?" + urllib.parse.urlencode(params)

    elapsed = time.monotonic() - last_request_time
    if last_request_time and elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)

    request = urllib.request.Request(
        BASE_URL + path,
        headers={"X-Auth-Token": TOKEN},
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            last_request_time = time.monotonic()
            return result
    except urllib.error.HTTPError as exc:
        last_request_time = time.monotonic()
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Błąd połączenia: {exc}") from exc


def poisson_probability(lam, goals):
    if lam <= 0:
        return 1.0 if goals == 0 else 0.0
    return math.exp(-lam) * lam**goals / math.factorial(goals)


def calculate_probabilities(home_xg, away_xg):
    # Extend the score matrix to reduce truncation for high-total-goal fixtures.
    hp = [poisson_probability(home_xg, g) for g in range(16)]
    ap = [poisson_probability(away_xg, g) for g in range(16)]
    hw = draw = aw = over15 = over25 = btts = 0.0

    for h, ph in enumerate(hp):
        for a, pa in enumerate(ap):
            p = ph * pa
            if h > a:
                hw += p
            elif h == a:
                draw += p
            else:
                aw += p
            if h + a >= 2:
                over15 += p
            if h + a >= 3:
                over25 += p
            if h >= 1 and a >= 1:
                btts += p

    # The finite score matrix omits a tiny Poisson tail; normalize every market
    # against the same probability mass so displayed markets stay calibrated.
    total = hw + draw + aw
    if total:
        hw, draw, aw, over15, over25, btts = (
            value / total for value in (hw, draw, aw, over15, over25, btts)
        )

    return {
        "homeWin": round(hw * 100, 1),
        "draw": round(draw * 100, 1),
        "awayWin": round(aw * 100, 1),
        "over15": round(over15 * 100, 1),
        "over25": round(over25 * 100, 1),
        "btts": round(btts * 100, 1),
    }


def table_maps(data):
    maps = {"TOTAL": {}, "HOME": {}, "AWAY": {}}

    for standing in data.get("standings", []):
        kind = standing.get("type", "TOTAL")
        if kind not in maps:
            continue

        for row in standing.get("table", []):
            name = (row.get("team") or {}).get("name")
            played = row.get("playedGames") or 0
            if not name or played < 1:
                continue
            maps[kind][name] = {
                "played": played,
                "for": row.get("goalsFor", 0) or 0,
                "against": row.get("goalsAgainst", 0) or 0,
            }

    return maps


def team_stats(maps, name, venue):
    stats = maps.get(venue, {}).get(name)
    if stats and stats["played"] >= 3:
        return stats, "venue"

    stats = maps.get("TOTAL", {}).get(name)
    if stats and stats["played"] >= 3:
        return stats, "total"

    return None, "missing"


def estimate_goals(home_name, away_name, maps):
    home, hs = team_stats(maps, home_name, "HOME")
    away, aws = team_stats(maps, away_name, "AWAY")

    if not home or not away:
        return None

    home_xg = (home["for"] / home["played"]
               + away["against"] / away["played"]) / 2
    away_xg = (away["for"] / away["played"]
               + home["against"] / home["played"]) / 2

    home_xg = max(0.15, min(4.0, home_xg))
    away_xg = max(0.15, min(4.0, away_xg))

    if hs == "venue" and aws == "venue":
        quality = "medium"
        confidence = "Umiarkowana: dane domowe i wyjazdowe"
    else:
        quality = "low"
        confidence = "Niska: użyto także danych ogólnych"

    return home_xg, away_xg, quality, confidence


def estimate_goals_from_history(match):
    """Fallback Poisson parameters from recent score history, never mislabeled as xG."""
    history = match.get("history") or {}
    home = (history.get("homeLast10") or {}).get("stats") or {}
    away = (history.get("awayLast10") or {}).get("stats") or {}
    home_played = home.get("played") or 0
    away_played = away.get("played") or 0
    if home_played < 3 or away_played < 3:
        return None

    home_attack = (home.get("goalsFor") or 0) / home_played
    home_defence = (home.get("goalsAgainst") or 0) / home_played
    away_attack = (away.get("goalsFor") or 0) / away_played
    away_defence = (away.get("goalsAgainst") or 0) / away_played
    home_rate = max(0.15, min(4.0, (home_attack + away_defence) / 2))
    away_rate = max(0.15, min(4.0, (away_attack + home_defence) / 2))
    return (
        home_rate,
        away_rate,
        "low",
        "Niska: model oparty na ostatnich wynikach, bez rzeczywistych xG",
    )

def fetch_league_matches(code, name, date_from, date_to):
    try:
        data = api_get(
            f"/competitions/{code}/matches",
            {"dateFrom": date_from, "dateTo": date_to},
        )
        matches = data.get("matches", [])
        diagnostics.append(
            f"{name} ({code}): {len(matches)} meczów w okresie."
        )
        return matches
    except Exception as exc:
        diagnostics.append(f"{name} ({code}): BŁĄD TERMINARZA: {exc}")
        return []


def fetch_standings(code):
    try:
        return table_maps(api_get(f"/competitions/{code}/standings"))
    except Exception as exc:
        diagnostics.append(f"{code}: brak tabeli: {exc}")
        return {"TOTAL": {}, "HOME": {}, "AWAY": {}}

def summarize_history(matches, team_name):
    """Podsumowanie ostatnich meczów konkretnej drużyny."""
    finished = []

    for match in matches:
        if match.get("status") not in (
            "FINISHED", "AWARDED", "EXTRA_TIME", "PENALTY_SHOOTOUT"
        ):
            continue

        home = (match.get("homeTeam") or {}).get("name")
        away = (match.get("awayTeam") or {}).get("name")
        score = match.get("score") or {}
        full_time = score.get("fullTime") or {}
        hg = full_time.get("home")
        ag = full_time.get("away")

        if home not in (team_name,) and away not in (team_name,):
            continue
        if hg is None or ag is None:
            continue

        finished.append({
            "date": match.get("utcDate"),
            "home": home,
            "away": away,
            "homeGoals": hg,
            "awayGoals": ag,
            # Preserve any match statistics provided by the data source.
            "stats": match.get("stats") or match.get("statistics") or match.get("matchStats") or None,
            "teamGoals": hg if home == team_name else ag,
            "conceded": ag if home == team_name else hg,
            "result": (
                "W" if (hg > ag if home == team_name else ag > hg)
                else "D" if hg == ag
                else "L"
            ),
        })

    finished.sort(key=lambda item: item.get("date") or "", reverse=True)
    recent = finished[:10]

    if not recent:
        return {"matches": [], "stats": None}

    count = len(recent)
    goals_for = sum(m["teamGoals"] for m in recent)
    goals_against = sum(m["conceded"] for m in recent)
    btts = sum(
        1 for m in recent
        if m["homeGoals"] > 0 and m["awayGoals"] > 0
    )

    return {
        "matches": recent,
        "stats": {
            "played": count,
            "wins": sum(1 for m in recent if m["result"] == "W"),
            "draws": sum(1 for m in recent if m["result"] == "D"),
            "losses": sum(1 for m in recent if m["result"] == "L"),
            "goalsFor": goals_for,
            "goalsAgainst": goals_against,
            "avgGoalsFor": round(goals_for / count, 2),
            "avgGoalsAgainst": round(goals_against / count, 2),
            "btts": btts,
            "over15": sum(
                1 for m in recent
                if m["homeGoals"] + m["awayGoals"] >= 2
            ),
            "over25": sum(
                1 for m in recent
                if m["homeGoals"] + m["awayGoals"] >= 3
            ),
        },
    }


def build_team_history(matches, home_name, away_name):
    """Ostatnie mecze obu drużyn i bezpośrednie starcia."""
    home_history = summarize_history(matches, home_name)
    away_history = summarize_history(matches, away_name)

    h2h = []
    for match in matches:
        if match.get("status") not in (
            "FINISHED", "AWARDED", "EXTRA_TIME", "PENALTY_SHOOTOUT"
        ):
            continue

        home = (match.get("homeTeam") or {}).get("name")
        away = (match.get("awayTeam") or {}).get("name")
        if not (
            (home == home_name and away == away_name)
            or (home == away_name and away == home_name)
        ):
            continue

        score = match.get("score") or {}
        full_time = score.get("fullTime") or {}
        hg = full_time.get("home")
        ag = full_time.get("away")
        if hg is None or ag is None:
            continue

        h2h.append({
            "date": match.get("utcDate"),
            "home": home,
            "away": away,
            "homeGoals": hg,
            "awayGoals": ag,
            "stats": match.get("stats") or match.get("statistics") or match.get("matchStats") or None,
        })

    h2h.sort(key=lambda item: item.get("date") or "", reverse=True)

    return {
        "homeLast10": home_history,
        "awayLast10": away_history,
        "h2h": h2h[:10],
    }
def main():
    now = datetime.now(WARSAW)
    date_from = now.date()
    date_to = date_from + timedelta(days=6)

    start = date_from.isoformat()
    end = date_to.isoformat()

    print(f"Od: {start} do: {end}")
    print("Strefa czasowa: Europe/Warsaw")
    print("Zakres godzin: cała doba (00:00–23:59) czasu Europe/Warsaw")
    print(f"Rozgrywki do sprawdzenia: {len(LEAGUES)}")

    if not TOKEN:
        raise RuntimeError(
            "Brak FOOTBALL_DATA_TOKEN. Sprawdź sekret w GitHub Actions."
        )

    all_matches = []
    for code, name in LEAGUES.items():
        all_matches.extend(
            fetch_league_matches(code, name, start, end)
        )

    selected = []
    seen = set()

    for match in all_matches:
        code = (match.get("competition") or {}).get("code")
        if code not in LEAGUES:
            continue

        match_id = match.get("id")
        if match_id in seen:
            continue
        seen.add(match_id)

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

        if not (date_from <= kickoff_dt.date() <= date_to):
            continue

        kickoff_time = kickoff_dt.strftime("%H:%M")

        home = (match.get("homeTeam") or {}).get("name")
        away = (match.get("awayTeam") or {}).get("name")
        if not home or not away:
            continue

        selected.append({
            "id": match_id,
            "league": code,
            "leagueName": LEAGUES[code],
            "date": kickoff_dt.strftime("%Y-%m-%d"),
            "time": kickoff_dt.strftime("%H:%M"),
            "kickoff": kickoff_dt.isoformat(),
            "home": home,
            "away": away,
        })

    selected.sort(key=lambda m: (m["kickoff"], m["leagueName"]))

    # Nie nadpisuj ostatnich poprawnych danych pustym wynikiem, gdy API terminarzy zawiodło.
    schedule_errors = [item for item in diagnostics if "BŁĄD TERMINARZA" in item]
    if not selected and schedule_errors:
        raise RuntimeError(
            "Nie znaleziono meczów, a co najmniej jedno zapytanie terminarza zakończyło się błędem. "
            "Przerywam, aby nie opublikować pustych lub niewiarygodnych danych."
        )

    tables = {}
    for code in sorted({m["league"] for m in selected}):
        tables[code] = fetch_standings(code)

    history_by_league = {}
    history_from = (now.date() - timedelta(days=180)).isoformat()

    for code in sorted({m["league"] for m in selected}):
        history_by_league[code] = fetch_league_matches(
            code,
            LEAGUES[code] + " — historia",
            history_from,
            start,
        )

    for match in selected:
        match["history"] = build_team_history(
            history_by_league.get(match["league"], []),
            match["home"],
            match["away"],
        )

    predictions = []
    for match in selected:
        maps = tables.get(
            match["league"],
            {"TOTAL": {}, "HOME": {}, "AWAY": {}},
        )
        estimate = estimate_goals(match["home"], match["away"], maps)
        model_status = "table_based"
        model_label = "Dixon-Coles + Monte Carlo — dane tabeli"

        if not estimate:
            estimate = estimate_goals_from_history(match)
            model_status = "history_based" if estimate else "insufficient_data"
            model_label = "Dixon-Coles + Monte Carlo — ostatnie wyniki" if estimate else None

        analytics = None
        if estimate:
            hx, ax, quality, confidence = estimate
            stable_seed = sum(ord(char) for char in str(match.get("id") or ""))
            analytics = analyze_match(hx, ax, seed=stable_seed)
            probabilities = analytics["markets"]
        else:
            hx = ax = None
            probabilities = None
            quality = "insufficient_data"
            confidence = "Za mało danych do obliczenia prognozy"

        match.update({
            "hx": round(hx, 2) if hx is not None else None,
            "ax": round(ax, 2) if ax is not None else None,
            "probabilities": probabilities,
            "analytics": analytics,
            "model": model_label,
            "quality": quality,
            "confidence": confidence,
            "modelStatus": model_status,
        })
        predictions.append(match)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "generatedAt": now.isoformat(),
        "modelVersion": "dixon-coles-mc-v1",
        "dateFrom": start,
        "dateTo": end,
        "timezone": "Europe/Warsaw",
        "filter": {"from": "00:00", "to": "23:59"},
        "count": len(predictions),
        "matches": predictions,
        "diagnostics": diagnostics,
        "note": (
            "Prognozy orientacyjne z modelu Dixon-Coles i symulacji Monte Carlo. "
            "Parametr korekty niskich wyników rho nie jest dopasowany do ligi. "
            "Model nie uwzględnia automatycznie składów, kontuzji, pogody ani kursów. "
            "Nie gwarantuje wyników."
        ),
    }

    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Łącznie meczów przez całą dobę na 3 dni: {len(predictions)}")
    print(
        "Mecze z obliczonymi prognozami: "
        f"{sum(m['probabilities'] is not None for m in predictions)}"
    )
    print(f"Zapisano: {OUTPUT}")

    for item in diagnostics:
        print(item)


if __name__ == "__main__":
    main()
