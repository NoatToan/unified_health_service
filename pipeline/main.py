"""Entry point: `python -m pipeline.main`.

Runs every scraper (each isolated in its own try/except so one broken source
never fails the whole run), merges + dedupes the results, validates with
pydantic, and writes:
  - docs/races/latest.json   (always, unless the safety rule below trips)
  - docs/races/YYYY-MM-DD.json  (only when the race content actually changed)

Safety rule: if the total race count would drop by more than 50% versus the
previous latest.json, refuse to overwrite it and exit non-zero (this is what
triggers GitHub Actions' failure email instead of silently publishing a
broken/empty dataset).
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from pipeline.merge import merge
from scrapers import finishers, irace, vbm, vnexpress
from scrapers.base import PoliteClient, Race, now_iso

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
RACES_DIR = DOCS_DIR / "races"
LATEST_PATH = RACES_DIR / "latest.json"
SNAPSHOT_RETENTION_DAYS = 90
MAX_DROP_RATIO = 0.5  # refuse to publish if race count drops more than this

SCRAPERS = [
    ("vnexpress", vnexpress.scrape),
    ("irace", irace.scrape),
    ("vbm", vbm.scrape),
    ("finishers", finishers.scrape),
]


def vn_now() -> datetime:
    """Vietnam is UTC+7, no DST."""
    return datetime.now(timezone.utc) + timedelta(hours=7)


def load_previous() -> dict | None:
    if not LATEST_PATH.exists():
        return None
    try:
        return json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def run_scrapers(client: PoliteClient, previous: dict | None) -> tuple[list[Race], list[dict]]:
    """Run every scraper; on failure (exception or empty result), carry over
    that source's previously-published races instead of dropping them.
    """
    previous_by_source: dict[str, list[dict]] = {}
    if previous:
        for raw_race in previous.get("races", []):
            for src in raw_race.get("sources", []):
                previous_by_source.setdefault(src["name"], []).append(raw_race)

    all_races: list[Race] = []
    source_reports: list[dict] = []

    for name, fn in SCRAPERS:
        try:
            races = fn(client)
            if not races:
                raise ValueError("scraper returned zero races")
            all_races.extend(races)
            source_reports.append(
                {"name": name, "ok": True, "count": len(races), "error": None}
            )
        except Exception as exc:  # noqa: BLE001 - one bad source must not kill the run
            carried_raw = previous_by_source.get(name, [])
            carried: list[Race] = []
            for raw in carried_raw:
                try:
                    carried.append(Race.model_validate(raw))
                except ValidationError:
                    continue
            all_races.extend(carried)
            source_reports.append(
                {
                    "name": name,
                    "ok": False,
                    "count": len(carried),
                    "error": str(exc)[:500],
                }
            )

    return all_races, source_reports


def _content_key(race: dict) -> dict:
    """A race dict with volatile bookkeeping fields stripped, for change
    detection and for deciding whether to bump lastUpdatedAt.
    """
    clean = copy.deepcopy(race)
    clean.pop("firstSeenAt", None)
    clean.pop("lastUpdatedAt", None)
    for src in clean.get("sources", []):
        src.pop("lastSeenAt", None)
    return clean


def reconcile_timestamps(fresh_races: list[Race], previous: dict | None) -> list[Race]:
    """Preserve firstSeenAt across runs, and only bump lastUpdatedAt when a
    race's actual content (not just source lastSeenAt) changed.
    """
    previous_by_id: dict[str, dict] = {}
    if previous:
        previous_by_id = {r["id"]: r for r in previous.get("races", [])}

    reconciled: list[Race] = []
    for race in fresh_races:
        prev = previous_by_id.get(race.id)
        if prev is None:
            reconciled.append(race)
            continue

        fresh_dict = race.model_dump()
        if _content_key(fresh_dict) == _content_key(prev):
            fresh_dict["firstSeenAt"] = prev.get("firstSeenAt", fresh_dict["firstSeenAt"])
            fresh_dict["lastUpdatedAt"] = prev.get("lastUpdatedAt", fresh_dict["lastUpdatedAt"])
        else:
            fresh_dict["firstSeenAt"] = prev.get("firstSeenAt", fresh_dict["firstSeenAt"])
        reconciled.append(Race.model_validate(fresh_dict))

    return reconciled


def content_changed(previous: dict | None, races: list[dict]) -> bool:
    if previous is None:
        return True
    prev_races = [_content_key(r) for r in previous.get("races", [])]
    new_races = [_content_key(r) for r in races]
    return prev_races != new_races


def exceeds_drop_threshold(previous_count: int, new_count: int) -> bool:
    """True if new_count represents more than MAX_DROP_RATIO drop from
    previous_count (and there was a previous count to compare against).
    """
    if previous_count <= 0:
        return False
    return new_count < previous_count * (1 - MAX_DROP_RATIO)


def cleanup_old_snapshots(today: str) -> None:
    cutoff = vn_now().date() - timedelta(days=SNAPSHOT_RETENTION_DAYS)
    if not RACES_DIR.exists():
        return
    for path in RACES_DIR.glob("????-??-??.json"):
        stem = path.stem
        try:
            file_date = datetime.strptime(stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date < cutoff:
            path.unlink(missing_ok=True)


def main() -> int:
    RACES_DIR.mkdir(parents=True, exist_ok=True)
    previous = load_previous()

    with PoliteClient() as client:
        raw_races, source_reports = run_scrapers(client, previous)

    merged = merge(raw_races)
    merged = reconcile_timestamps(merged, previous)

    cutoff_date = (vn_now().date() - timedelta(days=1)).isoformat()
    filtered = sorted(
        (r for r in merged if r.startDate >= cutoff_date),
        key=lambda r: (r.startDate, r.name),
    )

    new_count = len(filtered)
    previous_count = len(previous.get("races", [])) if previous else 0

    if exceeds_drop_threshold(previous_count, new_count):
        print(
            f"ERROR: race count dropped from {previous_count} to {new_count} "
            f"(>{MAX_DROP_RATIO * 100:.0f}% drop) - refusing to overwrite latest.json",
            file=sys.stderr,
        )
        return 1

    output = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": now_iso(),
        "sources": source_reports,
        "races": [r.model_dump() for r in filtered],
    }

    changed = content_changed(previous, output["races"])

    LATEST_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    today_str = vn_now().date().isoformat()
    if changed:
        snapshot_path = RACES_DIR / f"{today_str}.json"
        snapshot_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    cleanup_old_snapshots(today_str)

    ok_sources = [s["name"] for s in source_reports if s["ok"]]
    failed_sources = [s["name"] for s in source_reports if not s["ok"]]
    print(f"Wrote {new_count} races to {LATEST_PATH}")
    print(f"Sources OK: {ok_sources}")
    if failed_sources:
        print(f"Sources FAILED (carried over previous data): {failed_sources}")
    print(f"Content changed vs previous run: {changed}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
