from __future__ import annotations

from pipeline.main import content_changed, exceeds_drop_threshold, reconcile_timestamps
from scrapers.base import Race, SourceRef, make_id


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
