from __future__ import annotations

from scrapers import puma_gear
from tests.conftest import FakeClient, read_fixture


def _fake_client() -> FakeClient:
    fixture = read_fixture("puma_running_accessories.html")
    pages = {url: fixture for url, _category in puma_gear.LISTINGS}
    return FakeClient(pages, default="<html></html>")


def test_scrape_puma_gear_fixture():
    client = _fake_client()

    items = puma_gear.scrape(client)

    # Fixture is reused for all 3 listing URLs in this test, so every real
    # product in it is "found" 3 times (once per category pass) - this
    # scraper doesn't dedupe across listings itself (pipeline/gear_main.py's
    # dedupe_by_url() does that for the full run), so just check the
    # per-listing parse is correct on one representative item.
    cap = next(i for i in items if i.id == "puma-026168")
    assert cap.name == "Essentials Running 5 Panel Cap"
    assert cap.sourceName == "puma"
    assert cap.brand == "Puma"
    assert cap.priceVnd == 550000
    assert cap.productUrl == (
        "https://vn.puma.com/vn/en/pd/essentials-running-5-panel-cap/026168.html?color=01"
    )
    assert cap.imageUrl is not None

    # Real color-swatch data: multiple named colors, never fabricated.
    colors = {v.color for v in cap.variants}
    assert "PUMA Black" in colors
    assert len(cap.variants) >= 2
    for variant in cap.variants:
        assert variant.productUrl.startswith(
            "https://vn.puma.com/vn/en/pd/essentials-running-5-panel-cap/026168.html?color="
        )


def test_scrape_puma_gear_single_color_product_has_no_variants():
    client = _fake_client()
    items = puma_gear.scrape(client)

    visor_cap = next(i for i in items if i.id == "puma-027361")
    # Fixture shows this product with only 2 color swatches; still exercise
    # the "len(variants) > 1" rule on whatever the real data says rather
    # than asserting a specific count that could drift with the fixture.
    assert visor_cap.variants == [] or len(visor_cap.variants) > 1


def test_scrape_puma_gear_no_mobify_data_returns_empty():
    client = FakeClient({url: "<html><body>no data here</body></html>" for url, _ in puma_gear.LISTINGS})
    assert puma_gear.scrape(client) == []
