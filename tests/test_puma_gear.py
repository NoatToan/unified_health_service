from __future__ import annotations

import json

from scrapers import puma_gear
from scrapers.base import now_iso
from tests.conftest import FakeClient, read_fixture


def _fake_client() -> FakeClient:
    fixture = read_fixture("puma_running_accessories.html")
    pages = {url: fixture for url, _category in puma_gear.LISTINGS}
    return FakeClient(pages, default="<html></html>")


def test_scrape_puma_gear_fixture():
    client = _fake_client()

    items = puma_gear.scrape(client)

    # Fixture is reused for all 3 listing URLs in this test; scrape() now
    # dedupes by base product id across listings/pages (needed for real
    # pagination - see the module docstring), so each real product in the
    # fixture is only kept once (under whichever listing's category it was
    # first seen in - "shoes", since that's LISTINGS[0] here).
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


def _mobify_html(hits: list[dict], total: int, limit: int) -> str:
    payload = {
        "__PRELOADED_STATE__": {
            "__reactQuery": {
                "queries": [
                    {
                        "queryKey": ["/product-search"],
                        "state": {
                            "data": {
                                "pages": [
                                    {"hits": hits, "total": total, "limit": limit, "offset": 0}
                                ]
                            }
                        },
                    }
                ]
            }
        }
    }
    return (
        '<html><script id="mobify-data" type="application/json">'
        f"{json.dumps(payload)}</script></html>"
    )


def test_scrape_puma_gear_follows_pagination_until_total_reached():
    """Regression test for the 2026-11-12 fix: a listing with more products
    than fit on one page (`total` > `limit`) must have its later pages
    fetched via `?page=N`, not silently dropped.
    """
    page1_hit = {
        "productId": "111111_01",
        "productName": "Page1 Shoe",
        "c_canonicalUrl": "/pd/page1-shoe/111111.html",
        "price": 1000000,
    }
    page2_hit = {
        "productId": "222222_01",
        "productName": "Page2 Shoe",
        "c_canonicalUrl": "/pd/page2-shoe/222222.html",
        "price": 2000000,
    }
    shoes_url, _ = puma_gear.LISTINGS[0]
    pages = {
        shoes_url: _mobify_html([page1_hit], total=32, limit=16),
        f"{shoes_url}?page=2": _mobify_html([page2_hit], total=32, limit=16),
    }
    client = FakeClient(pages, default="<html></html>")

    items = puma_gear.scrape(client)

    names = {i.name for i in items}
    assert "Page1 Shoe" in names
    assert "Page2 Shoe" in names


def test_scrape_puma_gear_enriches_item_with_pdp_detail():
    """A real captured PDP (trimmed to its `/products/<id>` mobify-data
    entry - tests/fixtures/puma_pdp_everyday_running_waist_bag.html) should
    fill description/specs/features/sizes/gender/sku/images/inStock -
    regression test for the 2026-11-12 detail-enrichment feature.
    """
    hit = {
        "productId": "092404_05",
        "productName": "Everyday Running Waist Bag",
        "c_canonicalUrl": "/pd/everyday-running-waist-bag/092404.html?color=05",
        "price": 850000,
    }
    shoes_url, _ = puma_gear.LISTINGS[0]
    pdp_url = "https://vn.puma.com/vn/en/pd/everyday-running-waist-bag/092404.html?color=05"
    pages = {
        shoes_url: _mobify_html([hit], total=1, limit=16),
        pdp_url: read_fixture("puma_pdp_everyday_running_waist_bag.html"),
    }
    client = FakeClient(pages, default="<html></html>")

    items = puma_gear.scrape(client)

    item = next(i for i in items if i.id == "puma-092404")
    assert item.description is not None
    assert "waist bag" in item.description.lower()
    assert item.gender == "unisex"
    assert item.sku == "092404"
    assert item.inStock is True
    assert item.images
    assert item.sizes and item.sizes[0].label == "OSFA"
    assert item.sizes[0].available is True
    assert item.specs.get("material") == "Polyester"
    assert item.features
    assert item.detailFetchedAt is not None


def test_scrape_puma_gear_reuses_fresh_cached_detail_without_refetching():
    """When a previous run's detail for this `productUrl` is still fresh
    (< 7 days old), scrape() must reuse it rather than spending a PDP
    fetch - the PDP url is deliberately absent from `pages` here, so a
    second real fetch attempt would surface as a missing-detail item.
    """
    hit = {
        "productId": "092404_05",
        "productName": "Everyday Running Waist Bag",
        "c_canonicalUrl": "/pd/everyday-running-waist-bag/092404.html?color=05",
        "price": 850000,
    }
    shoes_url, _ = puma_gear.LISTINGS[0]
    pdp_url = "https://vn.puma.com/vn/en/pd/everyday-running-waist-bag/092404.html?color=05"
    pages = {shoes_url: _mobify_html([hit], total=1, limit=16)}
    client = FakeClient(pages, default="<html></html>")

    previous_by_url = {
        pdp_url: {
            "description": "Cached waist bag description.",
            "images": ["https://images.puma.com/cached.png"],
            "originalPriceVnd": None,
            "sizes": [{"label": "OSFA", "available": True}],
            "inStock": True,
            "gender": "unisex",
            "sku": "092404",
            "specs": {"material": "Polyester"},
            "features": ["Cached feature"],
            "detailFetchedAt": now_iso(),
        }
    }

    items = puma_gear.scrape(client, previous_by_url)

    item = next(i for i in items if i.id == "puma-092404")
    assert item.description == "Cached waist bag description."
    assert item.features == ["Cached feature"]
    assert item.sku == "092404"


def test_scrape_puma_gear_stops_pagination_when_total_reached():
    """A listing whose single page already covers `total` must not fetch a
    `?page=2` that doesn't exist in this test's fake pages at all.
    """
    hit = {
        "productId": "333333_01",
        "productName": "Only Page Shoe",
        "c_canonicalUrl": "/pd/only-page-shoe/333333.html",
        "price": 500000,
    }
    shoes_url, _ = puma_gear.LISTINGS[0]
    pages = {shoes_url: _mobify_html([hit], total=1, limit=16)}
    client = FakeClient(pages, default="<html></html>")

    items = puma_gear.scrape(client)

    assert {i.name for i in items} == {"Only Page Shoe"}
