"""Entry point: `python -m pipeline.news_main`.

Runs every news scraper (each isolated in its own try/except, same
philosophy as pipeline/main.py - one broken source never fails the whole
run), de-duplicates by article URL (exact match, newest-wins on conflicting
fields), sorts newest-first by `publishedAt`, and writes
`docs/news/latest.json`.

This is a metadata/snippet aggregator, not a full-text republisher: every
item keeps `sourceUrl` as the only way to read the full article. No dated
snapshots (unlike docs/races/) - the news feed is fast-moving and a
snapshot history isn't needed for v1.

Safety rule, same spirit as pipeline/main.py: if every source fails (zero
items total) while a previous run had items, don't overwrite latest.json
and exit non-zero instead of silently publishing an empty feed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import ValidationError

from scrapers import tuoitre_news, vnexpress_news, vnrun_news
from scrapers.base import PoliteClient, now_iso
from scrapers.news_base import NewsItem

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
NEWS_DIR = DOCS_DIR / "news"
LATEST_PATH = NEWS_DIR / "latest.json"

SCRAPERS = [
    ("vnexpress", vnexpress_news.scrape),
    ("tuoitre", tuoitre_news.scrape),
    ("vnrun", vnrun_news.scrape),
]


def load_previous() -> dict | None:
    if not LATEST_PATH.exists():
        return None
    try:
        return json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def run_scrapers(client: PoliteClient, previous: dict | None) -> tuple[list[NewsItem], list[dict]]:
    previous_by_source: dict[str, list[dict]] = {}
    if previous:
        for raw in previous.get("items", []):
            previous_by_source.setdefault(raw.get("sourceName", ""), []).append(raw)

    all_items: list[NewsItem] = []
    source_reports: list[dict] = []

    for name, fn in SCRAPERS:
        try:
            items = fn(client)
            if not items:
                raise ValueError("scraper returned zero items")
            all_items.extend(items)
            source_reports.append({"name": name, "ok": True, "count": len(items), "error": None})
        except Exception as exc:  # noqa: BLE001 - one bad source must not kill the run
            carried_raw = previous_by_source.get(name, [])
            carried: list[NewsItem] = []
            for raw in carried_raw:
                try:
                    carried.append(NewsItem.model_validate(raw))
                except ValidationError:
                    continue
            all_items.extend(carried)
            source_reports.append(
                {"name": name, "ok": False, "count": len(carried), "error": str(exc)[:500]}
            )

    return all_items, source_reports


def dedupe_by_url(items: list[NewsItem]) -> list[NewsItem]:
    """Exact de-dup by `sourceUrl` - unlike the races pipeline, no fuzzy
    cross-source name matching: a news article is a single page from a
    single publisher, so the URL alone is the natural dedup key. If the
    same URL ever appears twice in one run (shouldn't happen across
    different sources, but could if a scraper runs twice), the later one
    wins.
    """
    by_url: dict[str, NewsItem] = {}
    for item in items:
        by_url[item.sourceUrl] = item
    return list(by_url.values())


def main() -> int:
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    previous = load_previous()

    with PoliteClient() as client:
        raw_items, source_reports = run_scrapers(client, previous)

    deduped = dedupe_by_url(raw_items)
    deduped.sort(key=lambda i: i.publishedAt, reverse=True)

    new_count = len(deduped)
    previous_count = len(previous.get("items", [])) if previous else 0

    if new_count == 0 and previous_count > 0:
        print(
            "ERROR: every news source failed and produced zero items - "
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
    print(f"Wrote {new_count} news items to {LATEST_PATH}")
    print(f"Sources OK: {ok_sources}")
    if failed_sources:
        print(f"Sources FAILED (carried over previous data): {failed_sources}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
