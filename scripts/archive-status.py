#!/usr/bin/env python3
"""Prepend the previous status.json into status-history.json when it changes.

Keeps the homepage update flow as a one-file edit. Run from the repo root
after a commit that changed status.json (see .github/workflows/status-archive.yml).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "status.json"
HISTORY = ROOT / "status-history.json"


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def normalize(entry: object) -> dict | None:
    if not isinstance(entry, dict):
        return None
    text = entry.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    out = {"text": text.strip()}
    updated = entry.get("updated")
    if isinstance(updated, str) and updated.strip():
        out["updated"] = updated.strip()
    attribution = entry.get("attribution")
    if isinstance(attribution, str) and attribution.strip():
        out["attribution"] = attribution.strip()
    return out


def key(entry: dict) -> tuple:
    return (entry.get("text", ""), entry.get("updated", ""), entry.get("attribution", ""))


def previous_status() -> dict | None:
    try:
        raw = subprocess.check_output(
            ["git", "show", "HEAD~1:status.json"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return normalize(data)


def main() -> int:
    current = normalize(load_json(CURRENT, {}))
    if current is None:
        print("no current status; skip", file=sys.stderr)
        return 0

    prev = previous_status()
    if prev is None:
        print("no previous status; skip", file=sys.stderr)
        return 0
    if key(prev) == key(current):
        print("status unchanged; skip", file=sys.stderr)
        return 0

    history_raw = load_json(HISTORY, [])
    if not isinstance(history_raw, list):
        history_raw = []
    history = [e for e in (normalize(item) for item in history_raw) if e is not None]

    if history and key(history[0]) == key(prev):
        print("previous status already archived; skip", file=sys.stderr)
        return 0

    # Drop an older duplicate of the same text+updated if it somehow exists.
    history = [e for e in history if key(e) != key(prev)]
    history.insert(0, prev)

    with HISTORY.open("w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"archived: {prev['text'][:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
