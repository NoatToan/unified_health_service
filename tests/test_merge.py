from __future__ import annotations

from pipeline.merge import merge
from scrapers.base import Distance, Race, SourceRef, make_id


def _race(
    name: str,
    start_date: str,
    source: str,
    *,
    terrain: str = "road",
    distances: list[Distance] | None = None,
    price: int | None = None,
    status: str = "unknown",
    seen_at: str = "2026-11-08T00:00:00Z",
) -> Race:
    return Race(
        id=make_id(name, start_date),
        name=name,
        startDate=start_date,
        terrain=terrain,
        distances=distances or [],
        priceFromVnd=price,
        registrationStatus=status,
        sources=[SourceRef(name=source, url=f"https://example.com/{source}", lastSeenAt=seen_at)],
        firstSeenAt=seen_at,
        lastUpdatedAt=seen_at,
    )


def test_merge_exact_id_match_combines_sources():
    a = _race("Cà Mau Marathon", "2026-11-15", "vnexpress")
    b = _race("Cà Mau Marathon", "2026-11-15", "vbm")

    result = merge([a, b])

    assert len(result) == 1
    names = {s.name for s in result[0].sources}
    assert names == {"vnexpress", "vbm"}


def test_merge_fuzzy_match_combines_variant_names_same_date():
    a = _race("Cà Mau Marathon", "2026-11-15", "vnexpress")
    b = _race(
        "Giải chạy Marathon - Cà Mau 2026 Cúp PETROVIETNAM",
        "2026-11-15",
        "irace",
        price=450_000,
        status="open",
    )

    result = merge([a, b])

    assert len(result) == 1
    names = {s.name for s in result[0].sources}
    assert names == {"vnexpress", "irace"}


def test_merge_does_not_combine_unrelated_races_on_same_date():
    a = _race("Hanoi Marathon Heritage Race", "2026-11-08", "vnexpress")
    b = _race("Cà Mau Marathon", "2026-11-08", "vnexpress")

    result = merge([a, b])

    assert len(result) == 2


def test_merge_field_precedence_irace_price_vbm_distances():
    irace_race = _race(
        "Cà Mau Marathon",
        "2026-11-15",
        "irace",
        price=450_000,
        status="open",
        terrain="road",
        distances=[],
    )
    vbm_race = _race(
        "Cà Mau Marathon",
        "2026-11-15",
        "vbm",
        price=None,
        status="unknown",
        terrain="ultra",
        distances=[Distance(label="42km", km=42.195)],
    )

    result = merge([irace_race, vbm_race])

    assert len(result) == 1
    merged = result[0]
    # iRace wins price/status.
    assert merged.priceFromVnd == 450_000
    assert merged.registrationStatus == "open"
    # VBM wins distances/terrain.
    assert merged.terrain == "ultra"
    assert [d.label for d in merged.distances] == ["42km"]


def test_merge_empty_input():
    assert merge([]) == []
