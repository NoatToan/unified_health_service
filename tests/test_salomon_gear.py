from __future__ import annotations

from scrapers import salomon_gear
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
