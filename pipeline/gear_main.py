"""Entry point: `python -m pipeline.gear_main`.

Runs every runner-gear scraper (each isolated in its own try/except, same
philosophy as pipeline/main.py and pipeline/news_main.py - one broken source
never fails the whole run), de-duplicates by `productUrl`, and writes
`docs/gear/latest.json`.

This is a metadata + link-out catalog, not a store: every item keeps
`productUrl` as the only way to actually buy it. See
docs_research/GEAR_SOURCES_RESEARCH.md for the full source research and the
schema rationale, including which sources were checked and held back
(Decathlon, Nike, Adidas, Asics, ...) and why.

Safety rule, same spirit as the other two pipelines: if every source fails
(zero items total) while a previous run had items, don't overwrite
latest.json and exit non-zero instead of silently publishing an empty catalog.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import ValidationError

from scrapers import coolmate_gear, lining_gear, puma_gear, salomon_gear
from scrapers.base import PoliteClient, now_iso
from scrapers.gear_base import GearItem

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
GEAR_DIR = DOCS_DIR / "gear"
LATEST_PATH = GEAR_DIR / "latest.json"

SCRAPERS = [
    ("puma", puma_gear.scrape),
    ("salomon", salomon_gear.scrape),
    ("lining", lining_gear.scrape),
    ("coolmate", coolmate_gear.scrape),
]


def load_previous() -> dict | None:
    if not LATEST_PATH.exists():
        return None
    try:
        return json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def run_scrapers(client: PoliteClient, previous: dict | None) -> tuple[list[GearItem], list[dict]]:
    previous_by_source: dict[str, list[dict]] = {}
    previous_by_url: dict[str, dict] = {}
    if previous:
        for raw in previous.get("items", []):
            previous_by_source.setdefault(raw.get("sourceName", ""), []).append(raw)
            product_url = raw.get("productUrl")
            if product_url:
                previous_by_url[product_url] = raw

    all_items: list[GearItem] = []
    source_reports: list[dict] = []

    for name, fn in SCRAPERS:
        try:
            # `previous_by_url` lets each scraper's detail-enrichment step
            # (scrapers.gear_base.enrich_with_detail) reuse a still-fresh
            # cached detail instead of spending its PDP-fetch budget on a
            # product whose detail hasn't gone stale - see
            # MAX_DETAIL_FETCHES_PER_SOURCE/DETAIL_CACHE_MAX_AGE_DAYS.
            items = fn(client, previous_by_url)
            if not items:
                raise ValueError("scraper returned zero items")
            all_items.extend(items)
            source_reports.append({"name": name, "ok": True, "count": len(items), "error": None})
        except Exception as exc:  # noqa: BLE001 - one bad source must not kill the run
            carried_raw = previous_by_source.get(name, [])
            carried: list[GearItem] = []
            for raw in carried_raw:
                try:
                    carried.append(GearItem.model_validate(raw))
                except ValidationError:
                    continue
            all_items.extend(carried)
            source_reports.append(
                {"name": name, "ok": False, "count": len(carried), "error": str(exc)[:500]}
            )

    return all_items, source_reports


def dedupe_by_url(items: list[GearItem]) -> list[GearItem]:
    """Exact de-dup by `productUrl` (a grouped multi-color item's
    `productUrl` is its default variant's URL, already unique per base
    product). If the same URL appears twice in one run, the later one wins.
    """
    by_url: dict[str, GearItem] = {}
    for item in items:
        by_url[item.productUrl] = item
    return list(by_url.values())


def main() -> int:
    GEAR_DIR.mkdir(parents=True, exist_ok=True)
    previous = load_previous()

    with PoliteClient() as client:
        raw_items, source_reports = run_scrapers(client, previous)

    deduped = dedupe_by_url(raw_items)
    deduped.sort(key=lambda i: (i.category, i.brand, i.name))

    new_count = len(deduped)
    previous_count = len(previous.get("items", [])) if previous else 0

    if new_count == 0 and previous_count > 0:
        print(
            "ERROR: every gear source failed and produced zero items - "
            "refusing to overwrite latest.json",
            file=sys.stderr,
        )
        return 1

    output = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": now_iso(),
        "sources": source_reports,
        "items": [i.model_dump() for i in deduped],
    }

    LATEST_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    ok_sources = [s["name"] for s in source_reports if s["ok"]]
    failed_sources = [s["name"] for s in source_reports if not s["ok"]]
    print(f"Wrote {new_count} gear items to {LATEST_PATH}")
    print(f"Sources OK: {ok_sources}")
    if failed_sources:
        print(f"Sources FAILED (carried over previous data): {failed_sources}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
