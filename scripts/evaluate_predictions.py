#!/usr/bin/env python3
"""Evaluate archived pre-match forecasts against accumulated full-time results."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ARCHIVE = Path("data/prediction-history.json")
RESULTS = Path("data/results.json")
OUTPUT = Path("data/model-performance.json")


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def key(item):
    if item.get("id") is not None:
        return "id:" + str(item["id"])
    return "|".join(str(item.get(name) or "").strip().casefold()
                    for name in ("date", "home", "away"))


def actual_markets(match):
    home, away = int(match["homeGoals"]), int(match["awayGoals"])
    total = home + away
    return {
        "homeWin": int(home > away), "draw": int(home == away),
        "awayWin": int(home < away), "over15": int(total >= 2),
        "over25": int(total >= 3), "over35": int(total >= 4),
        "btts": int(home > 0 and away > 0),
        "homeOver05": int(home >= 1), "awayOver05": int(away >= 1),
        "homeOver15": int(home >= 2), "awayOver15": int(away >= 2),
    }


def main():
    archive = load(ARCHIVE)
    results = load(RESULTS)
    archived = archive.get("matches") if isinstance(archive.get("matches"), list) else []
    finished = results.get("matches") if isinstance(results.get("matches"), list) else []
    results_by_key = {key(item): item for item in finished if isinstance(item, dict)}
    evaluations = []
    for forecast in archived:
        if not isinstance(forecast, dict) or not isinstance(forecast.get("probabilities"), dict):
            continue
        result = results_by_key.get(key(forecast))
        if not result or result.get("homeGoals") is None or result.get("awayGoals") is None:
            continue
        probabilities = forecast["probabilities"]
        actual = actual_markets(result)
        row = {"forecast": forecast, "actual": actual, "hit": {}}
        for market, target in actual.items():
            value = probabilities.get(market)
            if isinstance(value, (int, float)) and math.isfinite(value):
                p = max(0.0, min(1.0, float(value) / 100.0))
                row["hit"][market] = int((p >= 0.5) == bool(target)) if market not in ("homeWin", "draw", "awayWin") else None
        evaluations.append((row, result))

    markets = sorted({market for row, _ in evaluations for market in row["forecast"]["probabilities"]
                      if market in ("homeWin", "draw", "awayWin", "over15", "over25", "over35",
                                    "btts", "homeOver05", "awayOver05", "homeOver15", "awayOver15")})
    report = {}
    resolved = len(evaluations)
    for market in markets:
        total = 0
        hits = 0
        brier_sum = 0.0
        logloss_sum = 0.0
        for row, result in evaluations:
            value = row["forecast"]["probabilities"].get(market)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                continue
            p = max(0.0001, min(0.9999, float(value) / 100.0))
            actual = row["actual"][market]
            total += 1
            hits += int((market in ("homeWin", "draw", "awayWin") and p == max(
                float(row["forecast"]["probabilities"].get(k, 0)) / 100.0
                for k in ("homeWin", "draw", "awayWin")
            ) and actual == 1) or (market not in ("homeWin", "draw", "awayWin") and (p >= 0.5) == bool(actual)))
            brier_sum += (p - actual) ** 2
            logloss_sum += -(actual * math.log(p) + (1 - actual) * math.log(1 - p))
        report[market] = {
            "count": total,
            "hitRate": round(100.0 * hits / total, 2) if total else None,
            "brierScore": round(brier_sum / total, 4) if total else None,
            "logLoss": round(logloss_sum / total, 4) if total else None,
        }

    # Multiclass 1X2 top-choice accuracy and normalized Brier score.
    outcome_hits = 0
    brier_1x2 = 0.0
    calibration = []
    for row, _ in evaluations:
        p = row["forecast"]["probabilities"]
        keys = ("homeWin", "draw", "awayWin")
        if not all(isinstance(p.get(name), (int, float)) for name in keys):
            continue
        actual = [row["actual"][name] for name in keys]
        predicted = [max(0.0, min(1.0, float(p[name]) / 100.0)) for name in keys]
        outcome_hits += int(max(range(3), key=lambda i: predicted[i]) == actual.index(1))
        brier_1x2 += sum((predicted[i] - actual[i]) ** 2 for i in range(3)) / 3.0
        for i, name in enumerate(keys):
            calibration.append((predicted[i], actual[i]))
    bins = []
    for lower in range(0, 100, 10):
        values = [(p, y) for p, y in calibration if lower / 100 <= p < (lower + 10) / 100]
        if values:
            bins.append({
                "range": f"{lower}-{lower + 10}%",
                "count": len(values),
                "predicted": round(100 * sum(p for p, _ in values) / len(values), 2),
                "observed": round(100 * sum(y for _, y in values) / len(values), 2),
            })

    output = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Pierwsze zapisane prognozy przedmeczowe porównane z wynikami końcowymi",
        "forecastCount": len(archived), "resolvedCount": resolved,
        "oneXTwoAccuracy": round(100 * outcome_hits / resolved, 2) if resolved else None,
        "oneXTwoBrierScore": round(brier_1x2 / resolved, 4) if resolved else None,
        "markets": report, "calibration": bins,
        "note": "Próba może być mała lub niepełna. Wyniki historyczne nie gwarantują przyszłej skuteczności; prawdopodobieństwa nie są zweryfikowane do momentu zebrania dostatecznej próby."
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Skuteczność: {resolved} rozstrzygniętych prognoz; zapisano {OUTPUT}.")


if __name__ == "__main__":
    main()
