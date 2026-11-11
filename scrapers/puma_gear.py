"""Runner-gear scraper: PUMA Vietnam's storefront.

https://vn.puma.com/vn/en/sports/running (+ running-apparel, running-accessories)

This storefront is a Salesforce Commerce Cloud PWA Kit app (React, server-
rendered for first load) rather than a classic SFCC template - its listing
pages don't have simple, stable CSS class names the way the rest of this
repo's scrapers rely on. Confirmed live on 2026-11-11 (see
docs_research/GEAR_SOURCES_RESEARCH.md §1/§3/§6): every listing page embeds a
single `<script id="mobify-data" type="application/json">` tag containing
the page's full server-fetched state, including a `/product-search` React
Query cache entry with structured hits - `productName`, `price`, canonical
URL, and (crucially) `c_colorSwatches`: a per-product array of every
available color, each with its own human-readable name ("Zen Blue", "Puma
Black", ...), swatch/product image, and group id. This is parsed directly
(no CSS-selector guessing, no JS execution) instead of the HTML markup.

Each product can appear as more than one `hit` in the same search response
(one per color, e.g. "Everyday Running Baseball Cap" id 026998 appeared as
both `026998_05` and `026998_06`) but every one of those hits already carries
the *same* full `c_colorSwatches` list for that product - so this scraper
only needs to process the first hit seen per base product id and build
`variants` straight from its `c_colorSwatches`, rather than grouping rows
itself.
"""
from __future__ import annotations

import json
import re

from scrapers.base import PoliteClient, now_iso
from scrapers.gear_base import GearItem, GearVariant, make_gear_id

SOURCE_NAME = "puma"
SITE_ROOT = "https://vn.puma.com/vn/en"
BRAND = "Puma"

LISTINGS: list[tuple[str, str]] = [
    ("https://vn.puma.com/vn/en/sports/running", "shoes"),
    ("https://vn.puma.com/vn/en/sports/running/running-apparel", "apparel"),
    ("https://vn.puma.com/vn/en/sports/running/running-accessories", "accessories"),
]

_MOBIFY_DATA_RE = re.compile(
    r'<script id="mobify-data" type="application/json">(.*?)</script>', re.DOTALL
)


def scrape(client: PoliteClient) -> list[GearItem]:
    items: list[GearItem] = []
    for listing_url, category in LISTINGS:
        resp = client.get(listing_url)
        for hit in _product_search_hits(resp.text):
            item = _parse_hit(hit, category)
            if item is not None:
                items.append(item)
    return items


def _product_search_hits(html: str) -> list[dict]:
    match = _MOBIFY_DATA_RE.search(html)
    if match is None:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    pre_state = data.get("__PRELOADED_STATE__") or {}
    queries = (pre_state.get("__reactQuery") or {}).get("queries") or []

    hits: list[dict] = []
    seen_base_ids: set[str] = set()
    for query in queries:
        key = query.get("queryKey")
        if not isinstance(key, list) or "/product-search" not in key:
            continue
        pages = ((query.get("state") or {}).get("data") or {}).get("pages") or []
        for page in pages:
            for hit in page.get("hits") or []:
                base_id = str(hit.get("productId", "")).split("_", 1)[0]
                if not base_id or base_id in seen_base_ids:
                    continue
                seen_base_ids.add(base_id)
                hits.append(hit)
    return hits


def _parse_hit(hit: dict, category: str) -> GearItem | None:
    product_id = str(hit.get("productId", ""))
    base_id = product_id.split("_", 1)[0]
    name = (hit.get("productName") or "").strip()
    canonical_url = hit.get("c_canonicalUrl") or ""
    if not base_id or not name or not canonical_url:
        return None

    path = canonical_url.split("?", 1)[0]
    default_url = SITE_ROOT + canonical_url

    price_vnd = hit.get("c_salePrice") or hit.get("price") or hit.get("c_listPrice")
    price_vnd = int(price_vnd) if isinstance(price_vnd, (int, float)) else None

    default_image = None
    image_groups = hit.get("imageGroups") or []
    if image_groups:
        images = image_groups[0].get("images") or []
        if images:
            default_image = images[0].get("link")

    swatches = hit.get("c_colorSwatches") or []
    variants: list[GearVariant] = []
    for swatch in swatches:
        color = (swatch.get("name") or "").strip()
        value = swatch.get("value")
        if not color or not value:
            continue
        image_url = (swatch.get("productImage") or {}).get("disBaseLink")
        variants.append(
            GearVariant(
                color=color,
                imageUrl=image_url,
                productUrl=f"{SITE_ROOT}{path}?color={value}",
            )
        )

    return GearItem(
        id=make_gear_id(SOURCE_NAME, base_id),
        name=name,
        brand=BRAND,
        category=category,
        sourceName=SOURCE_NAME,
        priceVnd=price_vnd,
        description=f"{BRAND} running {category}." if category else None,
        imageUrl=default_image,
        productUrl=default_url,
        variants=variants if len(variants) > 1 else [],
        crawledAt=now_iso(),
    )
