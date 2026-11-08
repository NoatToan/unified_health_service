"""Tier-2 scraper: Finishers' Vietnam destination page.

https://www.finishers.com/en/destinations/asia/vietnam

This is a Next.js page; the useful data is not in the rendered DOM but in the
embedded `__NEXT_DATA__` JSON blob, under
`props.pageProps.calendarSection.events` (a dict keyed by "YYYY-MM" ->
list of event dicts with date/name/href/city/disciplines/distances/status).

Mostly major/international races with few entries, used as a Tier-2 cross-
check rather than a primary source - it is not part of the iRace/VBM/
VnExpress field-precedence rules in pipeline/merge.py, it just contributes
extra races/sources like any other input to merge().
"""
from __future__ import annotations

import json
import re

from scrapers.base import (
    Distance,
    PoliteClient,
    Race,
    SourceRef,
    guess_terrain,
    make_id,
    now_iso,
)

SOURCE_NAME = "finishers"
LISTING_URL = "https://www.finishers.com/en/destinations/asia/vietnam"
SITE_ROOT = "https://www.finishers.com"

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)

_WELL_KNOWN_METERS = {
    42195: "42km",
    21097: "21km",
    21098: "21km",
    10000: "10km",
    5000: "5km",
    1000: "1km",
}


def scrape(client: PoliteClient) -> list[Race]:
    resp = client.get(LISTING_URL)
    data = _extract_next_data(resp.text)
    if data is None:
        return []

    try:
        events_by_month = data["props"]["pageProps"]["calendarSection"]["events"]
    except (KeyError, TypeError):
        return []

    seen_at = now_iso()
    races: list[Race] = []
    for month_events in events_by_month.values():
        for event in month_events:
            race = _parse_event(event, seen_at)
            if race is not None:
                races.append(race)
    return races


def _extract_next_data(html: str) -> dict | None:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _parse_event(event: dict, seen_at: str) -> Race | None:
    name = (event.get("name") or "").strip()
    date_str = event.get("date")
    if not name or not date_str:
        return None

    city = event.get("city")
    province = city

    disciplines = event.get("disciplines") or []
    explicit_terrain = disciplines[0] if disciplines else None
    terrain = guess_terrain(name, explicit_terrain)

    distances: list[Distance] = []
    for d in event.get("distances") or []:
        meters = d.get("distance")
        if meters is None:
            continue
        km = meters / 1000
        label = _WELL_KNOWN_METERS.get(round(meters), f"{km:g}km")
        distances.append(Distance(label=label, km=km))

    href = event.get("href") or ""
    detail_url = f"{SITE_ROOT}{href}" if href.startswith("/") else (href or LISTING_URL)

    return Race(
        id=make_id(name, date_str),
        name=name,
        startDate=date_str,
        province=province,
        location=province,
        terrain=terrain,
        distances=distances,
        registrationUrl=detail_url,
        sources=[SourceRef(name=SOURCE_NAME, url=detail_url, lastSeenAt=seen_at)],
        firstSeenAt=seen_at,
        lastUpdatedAt=seen_at,
    )
