from __future__ import annotations

from datetime import date

from pipeline.main import (
    apply_race_status,
    content_changed,
    enrich_images_and_descriptions,
    exceeds_drop_threshold,
    reconcile_timestamps,
    refine_terrain_from_description,
)
from scrapers.base import Race, SourceRef, make_id
from tests.conftest import FakeClient


def _race(name: str, start_date: str, source: str, seen_at: str) -> Race:
    return Race(
        id=make_id(name, start_date),
        name=name,
        startDate=start_date,
        sources=[SourceRef(name=source, url="https://example.com", lastSeenAt=seen_at)],
        firstSeenAt=seen_at,
        lastUpdatedAt=seen_at,
    )


def test_exceeds_drop_threshold():
    assert exceeds_drop_threshold(100, 40) is True  # -60%
    assert exceeds_drop_threshold(100, 60) is False  # -40%, within tolerance
    assert exceeds_drop_threshold(0, 0) is False  # no previous data yet
    assert exceeds_drop_threshold(100, 100) is False


def test_content_changed_true_when_no_previous():
    assert content_changed(None, [{"id": "a"}]) is True


def test_content_changed_ignores_last_seen_at_and_generated_at():
    previous = {
        "generatedAt": "2026-11-07T00:00:00Z",
        "races": [
            {
                "id": "a",
                "name": "A",
                "lastUpdatedAt": "2026-11-07T00:00:00Z",
                "sources": [{"name": "vbm", "url": "x", "lastSeenAt": "2026-11-07T00:00:00Z"}],
            }
        ],
    }
    new_races = [
        {
            "id": "a",
            "name": "A",
            "lastUpdatedAt": "2026-11-08T00:00:00Z",
            "sources": [{"name": "vbm", "url": "x", "lastSeenAt": "2026-11-08T00:00:00Z"}],
        }
    ]
    assert content_changed(previous, new_races) is False


def test_content_changed_true_when_a_real_field_changes():
    previous = {"races": [{"id": "a", "name": "A", "sources": []}]}
    new_races = [{"id": "a", "name": "A renamed", "sources": []}]
    assert content_changed(previous, new_races) is True


def test_reconcile_timestamps_preserves_first_seen_and_last_updated_when_unchanged():
    fresh = _race("Cà Mau Marathon", "2026-11-15", "vbm", "2026-11-08T00:00:00Z")
    previous = {
        "races": [
            {
                **fresh.model_dump(),
                "firstSeenAt": "2026-01-01T00:00:00Z",
                "lastUpdatedAt": "2026-01-01T00:00:00Z",
                "sources": [{"name": "vbm", "url": "https://example.com", "lastSeenAt": "2026-01-01T00:00:00Z"}],
            }
        ]
    }

    [reconciled] = reconcile_timestamps([fresh], previous)

    assert reconciled.firstSeenAt == "2026-01-01T00:00:00Z"
    assert reconciled.lastUpdatedAt == "2026-01-01T00:00:00Z"
    # the source's lastSeenAt is still bumped to today's scrape time
    assert reconciled.sources[0].lastSeenAt == "2026-11-08T00:00:00Z"


def test_reconcile_timestamps_bumps_last_updated_when_content_changes():
    fresh = _race("Cà Mau Marathon", "2026-11-15", "vbm", "2026-11-08T00:00:00Z")
    previous_dict = fresh.model_dump()
    previous_dict["name"] = "Cà Mau Marathon (old name)"
    previous_dict["firstSeenAt"] = "2026-01-01T00:00:00Z"
    previous_dict["lastUpdatedAt"] = "2026-01-01T00:00:00Z"
    previous = {"races": [previous_dict]}

    [reconciled] = reconcile_timestamps([fresh], previous)

    assert reconciled.firstSeenAt == "2026-01-01T00:00:00Z"  # discovery date preserved
    assert reconciled.lastUpdatedAt == "2026-11-08T00:00:00Z"  # bumped: content changed


# --------------------------------------------------------------------------- #
# Terrain refinement from a (possibly detail-page-sourced) description
# --------------------------------------------------------------------------- #

def test_refine_terrain_upgrades_generic_road_default_when_description_says_trail():
    race = _race("Legacy Marathon", "2026-11-15", "irace", "2026-11-08T00:00:00Z")
    race = race.model_copy(update={"description": "Chạy xuyên rừng sâu và núi cao."})

    [refined] = refine_terrain_from_description([race])

    assert refined.terrain == "trail"


def test_refine_terrain_leaves_non_road_terrain_alone():
    race = _race("Some Ultra", "2026-11-15", "vbm", "2026-11-08T00:00:00Z")
    race = race.model_copy(
        update={"terrain": "ultra", "description": "Chạy xuyên rừng sâu và núi cao."}
    )

    [refined] = refine_terrain_from_description([race])

    assert refined.terrain == "ultra"


def test_refine_terrain_leaves_road_alone_without_trail_keywords():
    race = _race("Legacy Marathon", "2026-11-15", "irace", "2026-11-08T00:00:00Z")
    race = race.model_copy(update={"description": "Giải chạy đường phố trung tâm thành phố."})

    [refined] = refine_terrain_from_description([race])

    assert refined.terrain == "road"


# --------------------------------------------------------------------------- #
# raceStatus
# --------------------------------------------------------------------------- #

def test_apply_race_status_sets_past_and_upcoming():
    past = _race("Old Race", "2026-11-07", "vbm", "2026-11-08T00:00:00Z")
    future = _race("Future Race", "2026-11-09", "vbm", "2026-11-08T00:00:00Z")

    [past_result, future_result] = apply_race_status([past, future], date(2026, 11, 8))

    assert past_result.raceStatus == "past"
    assert future_result.raceStatus == "upcoming"


# --------------------------------------------------------------------------- #
# Detail-page enrichment
# --------------------------------------------------------------------------- #

_DETAIL_HTML = """
<html><head>
  <meta property="og:image" content="https://example.com/race.jpg">
  <meta property="og:description" content="Giải chạy bộ với nhiều cự ly hấp dẫn, tổ chức tại trung tâm thành phố.">
</head><body></body></html>
"""


def _race_with(**overrides) -> Race:
    base = _race("Some Race", "2026-11-15", "irace", "2026-11-08T00:00:00Z")
    return base.model_copy(update={"registrationUrl": "https://ticket.irace.vn/some-race", **overrides})


def test_enrich_skips_races_that_already_have_both_fields():
    race = _race_with(imageUrl="https://already.example.com/x.jpg", description="Already have one.")
    client = FakeClient({})  # would raise/return default if actually called

    [result] = enrich_images_and_descriptions(client, [race])

    assert result.imageUrl == "https://already.example.com/x.jpg"
    assert result.description == "Already have one."


def test_enrich_fetches_detail_page_and_fills_missing_fields():
    race = _race_with()
    client = FakeClient({"https://ticket.irace.vn/some-race": _DETAIL_HTML})

    [result] = enrich_images_and_descriptions(client, [race])

    assert result.imageUrl == "https://example.com/race.jpg"
    assert result.description == "Giải chạy bộ với nhiều cự ly hấp dẫn, tổ chức tại trung tâm thành phố."


def test_enrich_skips_cart_like_registration_url_but_uses_source_url_instead():
    race = _race_with(registrationUrl="https://ticket.irace.vn/cart/checkout")
    race = race.model_copy(
        update={"sources": [SourceRef(name="irace", url="https://ticket.irace.vn/some-race", lastSeenAt="2026-11-08T00:00:00Z")]}
    )
    client = FakeClient({"https://ticket.irace.vn/some-race": _DETAIL_HTML})

    [result] = enrich_images_and_descriptions(client, [race])

    assert result.imageUrl == "https://example.com/race.jpg"


def test_enrich_leaves_fields_none_when_no_detail_url_available():
    race = _race_with(registrationUrl=None)
    race = race.model_copy(update={"sources": []})
    client = FakeClient({})

    [result] = enrich_images_and_descriptions(client, [race])

    assert result.imageUrl is None
    assert result.description is None


def test_enrich_is_resilient_to_a_failing_fetch():
    class RaisingClient:
        def get(self, url):
            raise RuntimeError("boom")

    race = _race_with()
    [result] = enrich_images_and_descriptions(RaisingClient(), [race])

    assert result.imageUrl is None
    assert result.description is None
