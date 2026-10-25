#!/usr/bin/env python3
"""Run optional football data providers in a consistent order."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = [
    ("Sportmonks", "SPORTMONKS_API_TOKEN", "scripts/update_sportmonks.py"),
    ("API-Football", "API_FOOTBALL_KEY", "scripts/update_api_football.py"),
]


def sportmonks_feed_is_fresh(max_age_minutes=25):
    """Avoid duplicate provider calls when the dedicated Sportmonks job just ran."""
    path = ROOT / "data/sportmonks.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        stamp_text = payload.get("generatedAt")
        if not stamp_text:
            return False
        stamp = datetime.fromisoformat(str(stamp_text).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
        return -300 <= age_seconds < max_age_minutes * 60
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def main():
    configured = 0
    succeeded = 0
    failures = []
    for name, token_env, script in PROVIDERS:
        if not os.environ.get(token_env, "").strip():
            print(f"{name}: pomijam — brak sekretu {token_env}.", flush=True)
            continue
        if name == "Sportmonks" and sportmonks_feed_is_fresh():
            print("Sportmonks: pomijam — feed jest świeży (mniej niż 25 minut).", flush=True)
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
    print(f"Skonfigurowane źródła: {configured}; sukcesy: {succeeded}; błędy: {len(failures)}.")
    for failure in failures:
        print(f"OSTRZEŻENIE: {failure}")
    # A source outage must not block valid predictions from the base provider.
    # Failures are explicit in the logs; any successful feed remains available.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
