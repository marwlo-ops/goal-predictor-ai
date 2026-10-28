"""Explainable football scoreline analytics: Dixon-Coles grid + Monte Carlo."""
from __future__ import annotations

import bisect
import math
import random
from typing import Any


def _poisson(rate: float, max_goals: int) -> list[float]:
    rate = max(0.0, min(float(rate), 8.0))
    values = [math.exp(-rate)]
    for goals in range(1, max_goals + 1):
        values.append(values[-1] * rate / goals)
    total = sum(values)
    return [value / total for value in values] if total else [1.0] + [0.0] * max_goals


def _low_score_adjustment(home_goals: int, away_goals: int,
                          home_rate: float, away_rate: float,
                          rho: float) -> float:
    # Dixon-Coles adjustment for the four low-score outcomes. A negative rho
    # slightly increases 0-0/1-1 and reduces 0-1/1-0; rho is not fitted here.
    if home_goals == 0 and away_goals == 0:
        return 1.0 - home_rate * away_rate * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + home_rate * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + away_rate * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(home_rate: float, away_rate: float, max_goals: int = 12,
                 rho: float = -0.08) -> list[list[float]]:
    """Return a normalized joint score probability matrix."""
    if not (math.isfinite(home_rate) and math.isfinite(away_rate)):
        raise ValueError("Oczekiwane gole muszą być skończonymi liczbami.")
    if not (0.0 <= home_rate <= 8.0 and 0.0 <= away_rate <= 8.0):
        raise ValueError("Oczekiwane gole muszą mieścić się w zakresie 0–8.")
    if max_goals < 5 or max_goals > 30:
        raise ValueError("max_goals musi mieścić się w zakresie 5–30.")
    hp = _poisson(home_rate, max_goals)
    ap = _poisson(away_rate, max_goals)
    matrix = []
    for h, ph in enumerate(hp):
        row = []
        for a, pa in enumerate(ap):
            tau = _low_score_adjustment(h, a, home_rate, away_rate, rho)
            row.append(max(0.0, ph * pa * tau))
        matrix.append(row)
    total = sum(sum(row) for row in matrix)
    if total <= 0:
        raise ValueError("Model utworzył pusty rozkład wyników.")
    return [[value / total for value in row] for row in matrix]


def _market_counts(home_goals: int, away_goals: int) -> dict[str, int]:
    total = home_goals + away_goals
    return {
        "homeWin": int(home_goals > away_goals),
        "draw": int(home_goals == away_goals),
        "awayWin": int(home_goals < away_goals),
        "over15": int(total >= 2),
        "over25": int(total >= 3),
        "over35": int(total >= 4),
        "btts": int(home_goals >= 1 and away_goals >= 1),
        "homeOver05": int(home_goals >= 1),
        "awayOver05": int(away_goals >= 1),
        "homeOver15": int(home_goals >= 2),
        "awayOver15": int(away_goals >= 2),
    }


def analyze_match(home_rate: float, away_rate: float, *, seed: int = 0,
                  samples: int = 12000, rho: float = -0.08) -> dict[str, Any]:
    """Produce exact grid markets, reproducible Monte Carlo estimates and scorelines."""
    if samples < 1000 or samples > 200000:
        raise ValueError("Liczba symulacji musi mieścić się w zakresie 1000–200000.")
    matrix = score_matrix(home_rate, away_rate, rho=rho)
    market_names = tuple(_market_counts(0, 0).keys())
    exact = {name: 0.0 for name in market_names}
    outcomes = []
    flat_probs = []
    for h, row in enumerate(matrix):
        for a, probability in enumerate(row):
            for name, value in _market_counts(h, a).items():
                exact[name] += probability * value
            outcomes.append((h, a))
            flat_probs.append(probability)
    total = sum(flat_probs)
    cdf = []
    running = 0.0
    for probability in flat_probs:
        running += probability / total
        cdf.append(running)
    cdf[-1] = 1.0

    exact_percent = {name: round(value * 100.0, 2) for name, value in exact.items()}
    rng = random.Random(int(seed))
    simulated = {name: 0 for name in market_names}
    for _ in range(samples):
        idx = min(bisect.bisect_left(cdf, rng.random()), len(outcomes) - 1)
        h, a = outcomes[idx]
        for name, value in _market_counts(h, a).items():
            simulated[name] += value
    monte_carlo = {name: round(value * 100.0 / samples, 2)
                   for name, value in simulated.items()}

    scorelines = []
    for h, row in enumerate(matrix):
        for a, probability in enumerate(row):
            scorelines.append({"score": f"{h}:{a}", "probability": round(probability * 100, 2)})
    scorelines.sort(key=lambda item: item["probability"], reverse=True)
    home_expected = sum(h * sum(row) for h, row in enumerate(matrix))
    away_expected = sum(a * matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])))
    return {
        "method": "Dixon-Coles (rho ustawione domyślnie, niewyuczone)",
        "rho": rho,
        "maxGoalsPerTeam": len(matrix) - 1,
        "expectedGoals": {"home": round(home_expected, 3), "away": round(away_expected, 3)},
        "markets": exact_percent,
        "monteCarlo": {"samples": samples, "markets": monte_carlo},
        "topScorelines": scorelines[:5],
        "caveat": "Rho nie jest dopasowane do ligi. Wyniki zależą od jakości parametrów goli; Monte Carlo jest symulacją tego samego modelu, a nie niezależnym potwierdzeniem."
    }
