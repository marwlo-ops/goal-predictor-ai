#!/usr/bin/env python3
"""Keep the first published pre-match forecast for later honest evaluation."""
import json
from datetime import datetime, timezone
from pathlib import Path

LATEST = Path("data/latest.json")
ARCHIVE = Path("data/prediction-history.json")
MAX_AGE_DAYS = 365
MAX_RECORDS = 12000


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def main():
    payload = read_json(LATEST, {})
    archive = read_json(ARCHIVE, {"source": "Goal Predictor AI", "matches": []})
    existing = archive.get("matches") if isinstance(archive.get("matches"), list) else []
    by_key = {}
    for item in existing:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id")) if item.get("id") is not None else "|".join(
            str(item.get(part) or "") for part in ("kickoff", "home", "away")
        )
        by_key[key] = item

    now = datetime.now(timezone.utc)
    added = 0
    for match in payload.get("matches", []):
        if not isinstance(match, dict) or not isinstance(match.get("probabilities"), dict):
            continue
        kickoff = match.get("kickoff")
        try:
            start = datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if start.astimezone(timezone.utc) <= now:
                continue
        except (ValueError, TypeError):
            continue
        key = str(match.get("id")) if match.get("id") is not None else "|".join(
            str(match.get(part) or "") for part in ("kickoff", "home", "away")
        )
        if key in by_key:
            continue
        by_key[key] = {
            "id": match.get("id"), "date": match.get("date"),
            "kickoff": kickoff, "league": match.get("league"),
            "leagueName": match.get("leagueName"), "home": match.get("home"),
            "away": match.get("away"), "hx": match.get("hx"), "ax": match.get("ax"),
            "probabilities": match["probabilities"], "analytics": match.get("analytics"),
            "model": match.get("model"), "modelStatus": match.get("modelStatus"),
            "predictionGeneratedAt": payload.get("generatedAt"),
        }
        added += 1

    cutoff = now.timestamp() - MAX_AGE_DAYS * 86400
    retained = []
    for item in by_key.values():
        stamp = item.get("kickoff") or item.get("predictionGeneratedAt")
        try:
            parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed.timestamp() >= cutoff:
                retained.append(item)
        except (ValueError, TypeError):
            continue
    retained.sort(key=lambda item: str(item.get("kickoff") or ""), reverse=True)
    retained = retained[:MAX_RECORDS]
    output = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Pierwsza opublikowana prognoza przedmeczowa; duplikaty nie nadpisują pierwszej prognozy",
        "count": len(retained), "matches": retained,
    }
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Archiwum prognoz: {len(retained)} zapisanych, {added} nowych.")


if __name__ == "__main__":
    main()
