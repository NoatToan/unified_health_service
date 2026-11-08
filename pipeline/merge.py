"""Normalize, dedupe and merge Race objects scraped from multiple sources into
one canonical list.

Dedup strategy:
 1. Exact match on the stable id (`slugify(normalized name) + "-" + startDate`).
 2. Fuzzy fallback: races with the same startDate whose normalized names have
    a rapidfuzz ratio >= FUZZY_THRESHOLD are considered the same event (this
    catches cases like iRace appending "Powered by PUMA" to a name that
    VnExpress/VBM report cleanly).

Field precedence on merge (per docs_research/RACE_SOURCES_RESEARCH.md):
 - `priceFromVnd` is the min of the merged race's `distances[].priceVnd`
   (skipping null/0 entries) whenever at least one distance carries a price;
   only when none do (the case for every current scraper - none of them
   publish a per-distance price breakdown yet) does it fall back to iRace's
   own advertised "from" price. This matters once a race's distances can
   come from a source other than the one that originally advertised the
   price: copying that source's figure directly could leave it stale/wrong
   after a cheaper distance package is merged in from elsewhere.
 - iRace wins for registration status / registration URL.
 - VBM / VnExpress win for distances / terrain.
 - Name/province/location/organizer/imageUrl/description prefer VBM, then
   VnExpress, then iRace (falling back to whichever source has a non-empty
   value otherwise).
 - `sources` are the union of every contributing source's SourceRef.

`raceStatus` is intentionally not merged here - it is pure "startDate vs.
today" computation with no per-source opinion, so pipeline/main.py sets it on
the final race list right before writing output.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from scrapers.base import Race, SourceRef, make_id, normalize_name_for_id

FUZZY_THRESHOLD = 90

_NAME_PRIORITY = ["vbm", "vnexpress", "irace"]
_PRICE_PRIORITY = ["irace"]
_DISTANCE_PRIORITY = ["vbm", "vnexpress"]


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def merge(races: list[Race]) -> list[Race]:
    if not races:
        return []

    n = len(races)
    uf = _UnionFind(n)
    # token_set_ratio (space-separated tokens) tolerates word reordering and
    # extra sponsor/cup words that a plain Levenshtein ratio would punish
    # (e.g. "Cà Mau Marathon" vs "Giải chạy Marathon - Cà Mau 2026 Cúp
    # PETROVIETNAM" vs "Cà Mau Marathon - Cúp Petrovietnam").
    norm_names = [normalize_name_for_id(r.name).replace("-", " ") for r in races]

    by_id: dict[str, list[int]] = {}
    for i, r in enumerate(races):
        by_id.setdefault(r.id, []).append(i)
    for indices in by_id.values():
        for other in indices[1:]:
            uf.union(indices[0], other)

    # Fuzzy fallback: compare races sharing a startDate that are not already
    # grouped together.
    by_date: dict[str, list[int]] = {}
    for i, r in enumerate(races):
        by_date.setdefault(r.startDate, []).append(i)

    for indices in by_date.values():
        for a_pos in range(len(indices)):
            for b_pos in range(a_pos + 1, len(indices)):
                a, b = indices[a_pos], indices[b_pos]
                if uf.find(a) == uf.find(b):
                    continue
                score = fuzz.token_set_ratio(norm_names[a], norm_names[b])
                if score >= FUZZY_THRESHOLD:
                    uf.union(a, b)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    merged = [_merge_group([races[i] for i in idxs]) for idxs in groups.values()]
    merged.sort(key=lambda r: (r.startDate, r.name))
    return merged


def _by_source(group: list[Race], source_name: str) -> Race | None:
    for race in group:
        if any(s.name == source_name for s in race.sources):
            return race
    return None


def _pick(group: list[Race], priority: list[str], field: str):
    for source_name in priority:
        race = _by_source(group, source_name)
        if race is None:
            continue
        value = getattr(race, field)
        if value not in (None, "", [], "unknown"):
            return value
    # fall back to the first non-empty value from any source
    for race in group:
        value = getattr(race, field)
        if value not in (None, "", [], "unknown"):
            return value
    return getattr(group[0], field)


def _price_from_distances(distances: list) -> int | None:
    """min(distances[].priceVnd), skipping null/0 entries. None if no
    distance carries a usable price.
    """
    prices = [d.priceVnd for d in distances if d.priceVnd]
    return min(prices) if prices else None


def _merge_group(group: list[Race]) -> Race:
    name = _pick(group, _NAME_PRIORITY, "name")
    start_date = group[0].startDate
    province = _pick(group, _NAME_PRIORITY, "province")
    location = _pick(group, _NAME_PRIORITY, "location")
    organizer = _pick(group, _NAME_PRIORITY, "organizer")
    image_url = _pick(group, _NAME_PRIORITY, "imageUrl")
    description = _pick(group, _NAME_PRIORITY, "description")
    results = _pick(group, _NAME_PRIORITY, "results")

    terrain = _pick(group, _DISTANCE_PRIORITY, "terrain")
    distances = _pick(group, _DISTANCE_PRIORITY, "distances")

    # Compute from the merged race's own distances first (see module
    # docstring); only fall back to a source's advertised "from" price when
    # no distance actually carries a price yet.
    price_from = _price_from_distances(distances or []) or _pick(
        group, _PRICE_PRIORITY, "priceFromVnd"
    )
    reg_status = _pick(group, _PRICE_PRIORITY, "registrationStatus")
    reg_url = _pick(group, _PRICE_PRIORITY, "registrationUrl")

    sources: list[SourceRef] = []
    seen_source_names: dict[str, SourceRef] = {}
    for race in group:
        for s in race.sources:
            existing = seen_source_names.get(s.name)
            if existing is None or s.lastSeenAt > existing.lastSeenAt:
                seen_source_names[s.name] = s
    sources = list(seen_source_names.values())

    first_seen = min(r.firstSeenAt for r in group)
    last_updated = max(r.lastUpdatedAt for r in group)

    return Race(
        id=make_id(name, start_date),
        name=name,
        startDate=start_date,
        endDate=_pick(group, _NAME_PRIORITY, "endDate"),
        province=province,
        location=location,
        terrain=terrain or "road",
        distances=distances or [],
        priceFromVnd=price_from,
        registrationStatus=reg_status or "unknown",
        organizer=organizer,
        registrationUrl=reg_url,
        imageUrl=image_url,
        description=description,
        results=results,
        sources=sources,
        firstSeenAt=first_seen,
        lastUpdatedAt=last_updated,
    )
