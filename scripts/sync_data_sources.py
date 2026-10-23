#!/usr/bin/env python3
"""Run the optional data providers in a consistent, deterministic order.

Order matters: the base publisher creates latest.json first, then Sportmonks
adds fixtures/stats, then API-Football enriches and verifies the consolidated list.
Each provider is isolated so one optional provider failing does not block another.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = [
    ("Sportmonks", "SPORTMONKS_API_TOKEN", "scripts/update_sportmonks.py"),
    ("API-Football", "API_FOOTBALL_KEY", "scripts/update_api_football.py"),
]


def main():
    configured = 0
    succeeded = 0
    failures = []
    for name, token_env, script in PROVIDERS:
        if not os.environ.get(token_env, "").strip():
            print(f"{name}: pomijam — brak skonfigurowanego sekretu {token_env}.")
            continue
        configured += 1
        print(f"\n===== Źródło danych: {name} =====", flush=True)
        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / script)],
                cwd=ROOT,
                check=False,
            )
        except OSError as exc:
            failures.append(f"{name}: nie można uruchomić skryptu ({exc})")
            print(failures[-1], file=sys.stderr)
            continue
        if result.returncode == 0:
            succeeded += 1
            print(f"{name}: zakończono bez błędu.", flush=True)
        else:
            failures.append(f"{name}: skrypt zakończył się kodem {result.returncode}")
            print(failures[-1], file=sys.stderr)

    print("\n===== Podsumowanie integracji API =====")
    print(f"Skonfigurowane źródła: {configured}; zakończone sukcesem: {succeeded}; błędy: {len(failures)}.")
    for failure in failures:
        print(f"OSTRZEŻENIE: {failure}")
    # Optional integrations are non-blocking; preserve valid base predictions.
    # GitHub logs still make any provider failure visible.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
