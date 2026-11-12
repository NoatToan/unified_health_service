from __future__ import annotations

from scrapers import salomon_gear
from scrapers.base import now_iso
from tests.conftest import FakeClient, read_fixture


def _fake_client() -> FakeClient:
    fixture = read_fixture("salomon_phu_kien_products.json")
    pages = {
        f"{salomon_gear.BASE_URL}/collections/{handle}/products.json?limit={salomon_gear.PRODUCTS_PER_PAGE}": fixture
        for handle, _category in salomon_gear.COLLECTIONS
    }
    return FakeClient(pages, default='{"products": []}')


def test_scrape_salomon_gear_fixture():
    client = _fake_client()

    items = salomon_gear.scrape(client)

    # Same fixture is returned for every collection handle, but scrape()
    # dedupes by product handle within one run, so each real product in the
    # fixture should appear exactly once despite being "found" 4 times.
    urls = [i.productUrl for i in items]
    assert len(urls) == len(set(urls))
    assert len(items) > 0

    backpack = next(i for i in items if "Cross 12" in i.name)
    assert backpack.sourceName == "salomon"
    assert backpack.brand == "Salomon"
    assert backpack.priceVnd == 3199000
    assert backpack.productUrl == (
        "https://vn.salomon.com/products/balo-hiking-salomon-cross-12-black-lc2185700"
    )
    assert backpack.imageUrl is not None
    # No sibling-color navigation exists on this storefront (confirmed in
    # docs_research/GEAR_SOURCES_RESEARCH.md) - variants must never be
    # fabricated for a source that doesn't expose them.
    assert backpack.variants == []


def test_scrape_salomon_gear_empty_collection_returns_empty():
    client = FakeClient({}, default='{"products": []}')
    assert salomon_gear.scrape(client) == []


_DETAIL_HANDLE = "giay-chay-the-thao-nam-salomon-alphacross-5-l47313300-grey"


def _listing_payload_for_handle(handle: str) -> str:
    import json

    return json.dumps(
        {
            "products": [
                {
                    "title": "Giày Chạy Thể Thao Nam Salomon Alphacross 5 L47313300 Grey",
                    "handle": handle,
                    "images": [{"src": "https://product.hstatic.net/listing.png"}],
                    "variants": [{"price": "1600000.00"}],
                    "product_type": "Giày Running",
                }
            ]
        }
    )


def test_scrape_salomon_gear_enriches_item_with_pdp_detail():
    """A real captured `/products/<handle>.json` detail payload (trimmed
    fixture tests/fixtures/salomon_product_detail.json) should fill
    description/specs/sizes/gender/sku/originalPriceVnd/images -
    regression test for the 2026-11-12 detail-enrichment feature.
    """
    shoes_url, _ = salomon_gear.COLLECTIONS[0]
    listing_url = (
        f"{salomon_gear.BASE_URL}/collections/{shoes_url}/products.json"
        f"?limit={salomon_gear.PRODUCTS_PER_PAGE}"
    )
    product_url = f"{salomon_gear.BASE_URL}/products/{_DETAIL_HANDLE}"
    pages = {
        listing_url: _listing_payload_for_handle(_DETAIL_HANDLE),
        f"{product_url}.json": read_fixture("salomon_product_detail.json"),
    }
    client = FakeClient(pages, default='{"products": []}')

    items = salomon_gear.scrape(client)

    item = next(i for i in items if i.productUrl == product_url)
    assert item.description is not None
    assert "salomon alphacross" in item.description.lower() or "chạy địa hình" in item.description
    assert item.gender == "men"
    assert item.sku == "L47313300"
    assert item.inStock is True
    assert item.originalPriceVnd == 3999000
    assert item.specs.get("Trọng lượng") == "265g"
    assert any(s.label == "9 / 43⅓" and s.available for s in item.sizes)
    assert item.detailFetchedAt is not None


def test_scrape_salomon_gear_reuses_fresh_cached_detail_without_refetching():
    shoes_url, _ = salomon_gear.COLLECTIONS[0]
    listing_url = (
        f"{salomon_gear.BASE_URL}/collections/{shoes_url}/products.json"
        f"?limit={salomon_gear.PRODUCTS_PER_PAGE}"
    )
    product_url = f"{salomon_gear.BASE_URL}/products/{_DETAIL_HANDLE}"
    # Deliberately no `.json` detail page in `pages` - a cache miss here
    # would surface as a missing-detail item, not a crash.
    pages = {listing_url: _listing_payload_for_handle(_DETAIL_HANDLE)}
    client = FakeClient(pages, default='{"products": []}')

    previous_by_url = {
        product_url: {
            "description": "Cached shoe description.",
            "gender": "men",
            "sku": "L47313300",
            "specs": {"Trọng lượng": "265g"},
            "features": [],
            "images": [],
            "sizes": [],
            "inStock": True,
            "originalPriceVnd": None,
            "detailFetchedAt": now_iso(),
        }
    }

    items = salomon_gear.scrape(client, previous_by_url)

    item = next(i for i in items if i.productUrl == product_url)
    assert item.description == "Cached shoe description."
    assert item.sku == "L47313300"
