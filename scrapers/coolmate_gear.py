"""Runner-gear scraper: Coolmate's Vietnamese D2C storefront.

https://www.coolmate.me/collection/quan-ao-chay-bo (+ quan-ao-chay-bo-nu,
phu-kien-chay-bo)

Coolmate is a Vietnamese menswear/activewear brand (own house brand, sold
only on its own site) with a dedicated "chạy bộ" (running) line: apparel
(shirts, shorts, tights, jackets) and accessories (socks, masks, bags) -
confirmed no running *shoes* collection exists anywhere in this storefront's
own `sitemap/collection0.xml` (checked live 2026-11-12), so this scraper only
ever emits `apparel`/`accessories` items - never a fabricated `shoes` entry.

This storefront is a Next.js **App Router** app (unlike Puma's older Pages
Router `mobify-data` blob or Salomon/Li-Ning's Shopify/Haravan JSON
endpoint). Its collection pages stream their server-rendered state as a
series of `self.__next_f.push([1, "<escaped JSON text>"])` calls in the raw
HTML (React Server Components, "RSC", payload) - each chunk is itself a JSON
string literal. Confirmed live on 2026-11-12 (see
docs_research/GEAR_SOURCES_RESEARCH.md §1 "Coolmate"): concatenating every
chunk's *decoded* text and locating the (non-empty) `"products":[...]` array
inside it recovers the exact same real, structured data
(title/href/id/regular_price/compare_price/mapped_variants/...) a browser
would hydrate from - no JS execution, just text parsing of what one plain
HTTP GET already returns, same spirit as Puma's `mobify-data` regex.

`robots.txt` (`User-agent: *`) only disallows `/account`, `/cart`,
`/profile`, `/blog/wp-admin/`, `/spotlight` - none of which this touches.
(A separate `meta-webindexer` user-agent group disallows a few `?price_range=`
/`?size=` query params, but that group doesn't apply to this bot, and this
scraper never requests those query strings anyway.)

Each color on a product (`mapped_variants`, keyed by color name) shares the
*same* product page - no `?color=`-style query param or distinct URL per
color was found on the PDP (confirmed: a live PDP only exposed `?color=den`/
`xam`/`xanh`-style *short* color-family slugs that don't correspond
1:1 to the full accented display names in `mapped_variants`, so guessing one
would be a fabrication). Every `GearVariant` for this source therefore
points `productUrl` at the same base product page - still a real,
dereferenceable link, just not color-specific - while `imageUrl` *is* real
per-color data (`colorImage`/`thumbnail`).

**2026-11-12 detail enrichment**: the PDP (`item.productUrl` itself) embeds
one more RSC chunk holding `"initialProduct":{...}` - the full product
record, confirmed live to carry genuinely structured facts well beyond the
listing row: `short_desc` (a real one-paragraph description, with a
site-wide "✓Giá tốt ✓COD toàn quốc ✓60 ngày đổi trả" promo badge suffix on
every product, stripped before use), `extra.p_extra_features` (clean
`{title, value}` spec pairs - "Chất liệu" (fabric), "Công nghệ"
(technology), "Kiểu dáng" (fit), "Phù hợp" (use/terrain), ...),
`extra.p_extra_attributes` (short checked-only fact chips -> `features`),
`gender_type` (`"MALE"`/`"FEMALE"`/...), `available`, `regular_price`/
`compare_price`, `options`/`variants` with a per-size `quantity`, and the
full `images` gallery. No per-product SKU field is exposed directly, but
every variant's own `sync_product[0].label` embeds one as a stable prefix
(e.g. "24CM.MAWRN.SOZ793.<color>.<size>_..." - confirmed shared across every
color/size of one real product) - recovered the same "common prefix of
real per-variant values" way `gear_base.common_variant_sku_prefix` does for
the Shopify/Haravan sources.
"""
from __future__ import annotations

import json
import os
import re

from scrapers.base import PoliteClient, now_iso
from scrapers.gear_base import (
    GearItem,
    GearSize,
    GearVariant,
    MAX_FEATURES,
    clean_description,
    enrich_with_detail,
    make_gear_id,
    normalize_gender,
    resolve_listing_gender,
)
from unidecode import unidecode

SOURCE_NAME = "coolmate"
BASE_URL = "https://www.coolmate.me"
IMAGE_CDN = "https://mcdn.coolmate.me"
BRAND = "Coolmate"

# Collection handle -> category. Confirmed real, broadest running-specific
# collections on this storefront (docs_research/GEAR_SOURCES_RESEARCH.md
# §1) - no running-shoes collection exists here, so `shoes` is never used.
COLLECTIONS: list[tuple[str, str]] = [
    ("quan-ao-chay-bo", "apparel"),
    ("quan-ao-chay-bo-nu", "apparel"),
    ("phu-kien-chay-bo", "accessories"),
]

# Collection handle -> gender, for the one handle here that's explicitly
# gendered by the storefront itself ("quần áo chạy bộ nữ" = women's running
# apparel). `quan-ao-chay-bo` is this brand's general/default running
# apparel listing - not confirmed to be men-exclusive (Coolmate is a
# menswear-first brand, but that's a house-brand characterization, not a
# per-collection gender statement the storefront itself makes) - so it
# carries no gender tag of its own, same spirit as normalize_gender's
# "never guess" rule. `phu-kien-chay-bo` (accessories) isn't gendered either.
GENDER_BY_HANDLE: dict[str, str] = {
    "quan-ao-chay-bo-nu": "women",
}

_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.DOTALL)
_PRODUCTS_ARRAY_RE = re.compile(r'"products":\[\{')


def scrape(
    client: PoliteClient, previous_by_url: dict[str, dict] | None = None
) -> list[GearItem]:
    items: list[GearItem] = []
    item_ids: list[str] = []
    seen_ids: set[str] = set()
    genders_by_id: dict[str, set[str]] = {}

    for handle, category in COLLECTIONS:
        gender_tag = GENDER_BY_HANDLE.get(handle)
        resp = client.get(f"{BASE_URL}/collection/{handle}")
        for product in _extract_products(resp.text):
            product_id = product.get("id")
            if not product_id:
                continue
            if gender_tag:
                genders_by_id.setdefault(product_id, set()).add(gender_tag)
            if product_id in seen_ids:
                continue
            item = _parse_product(product, category)
            if item is not None:
                items.append(item)
                item_ids.append(product_id)
                seen_ids.add(product_id)

    for index, product_id in enumerate(item_ids):
        resolved = resolve_listing_gender(genders_by_id.get(product_id))
        if resolved:
            items[index] = items[index].model_copy(update={"gender": resolved})

    return enrich_with_detail(client, items, previous_by_url, _fetch_detail, SOURCE_NAME)


def _decode_chunks(html: str) -> str:
    """Each `self.__next_f.push([1, "..."])` call's second element is a JSON
    string literal (its own escaping, independent of the others) - decoding
    each one individually with `json.loads` (rather than naively unescaping
    the whole concatenated blob) is what correctly recovers non-ASCII text
    (Vietnamese diacritics) rather than mangling it.
    """
    parts: list[str] = []
    for raw in _CHUNK_RE.findall(html):
        try:
            parts.append(json.loads('"' + raw + '"'))
        except json.JSONDecodeError:
            continue
    return "".join(parts)


def _find_balanced_array(text: str, start: int) -> str | None:
    """`start` must point at the opening `[` of a JSON array within `text`.
    Returns the substring up to (and including) its matching `]`, tracking
    quoted strings so a `]` inside a string value doesn't end the scan early.
    """
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_products(html: str) -> list[dict]:
    decoded = _decode_chunks(html)
    for match in _PRODUCTS_ARRAY_RE.finditer(decoded):
        array_start = match.end() - 2  # index of the matched '[' (the regex
        # itself ends on the following '{', so back up one more character)
        array_text = _find_balanced_array(decoded, array_start)
        if array_text is None:
            continue
        try:
            products = json.loads(array_text)
        except json.JSONDecodeError:
            continue
        if products:
            return products
    return []


def _parse_product(product: dict, category: str) -> GearItem | None:
    title = (product.get("title") or "").strip()
    href = (product.get("href") or "").strip()
    product_id = product.get("id")
    if not title or not href or not product_id:
        return None

    product_url = BASE_URL + href

    image_path = product.get("default_thumbnail")
    image_url = f"{IMAGE_CDN}{image_path}" if image_path else None

    price = product.get("regular_price")
    price_vnd = int(price) if isinstance(price, (int, float)) else None

    variants: list[GearVariant] = []
    mapped_variants = product.get("mapped_variants") or {}
    if len(mapped_variants) > 1:
        for color, sizes in mapped_variants.items():
            if not color or not sizes:
                continue
            color_image = sizes[0].get("colorImage") or sizes[0].get("thumbnail")
            variants.append(
                GearVariant(
                    color=color,
                    imageUrl=f"{IMAGE_CDN}{color_image}" if color_image else None,
                    # No per-color URL exists on this storefront (see module
                    # docstring) - link to the real product page rather
                    # than guessing a `?color=` slug from the display name.
                    productUrl=product_url,
                )
            )

    return GearItem(
        id=make_gear_id(SOURCE_NAME, str(product_id)),
        name=title,
        brand=BRAND,
        category=category,
        sourceName=SOURCE_NAME,
        priceVnd=price_vnd,
        description=None,  # filled by detail enrichment - see module
        # docstring's "2026-11-12 detail enrichment"; never the old
        # "<Brand> running <category>." placeholder.
        imageUrl=image_url,
        productUrl=product_url,
        variants=variants,
        crawledAt=now_iso(),
    )


# --------------------------------------------------------------------------- #
# Detail (PDP) enrichment
# --------------------------------------------------------------------------- #

_INITIAL_PRODUCT_MARKER = '"initialProduct":{'
_PROMO_BADGE_MARKER = "✓"  # "✓" - starts the site-wide "✓Giá tốt ✓COD
# toàn quốc ✓60 ngày đổi trả" promo suffix every product's short_desc ends
# with; not product-specific, so it's cut before using short_desc as the
# description.


def _find_balanced_object(text: str, start: int) -> str | None:
    """Same balanced-scan idea as `_find_balanced_array`, for a JSON object
    (`{...}`) instead of an array.
    """
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_initial_product(html: str) -> dict | None:
    """Same RSC-chunk-decoding idea `_extract_products` already uses for a
    listing page's `"products":[...]` array, here for a PDP's own
    `"initialProduct":{...}` object (confirmed live to be fully
    self-contained within one `self.__next_f.push` chunk's decoded text).
    """
    decoded = _decode_chunks(html)
    idx = decoded.find(_INITIAL_PRODUCT_MARKER)
    if idx == -1:
        return None
    start = idx + len('"initialProduct":')
    obj_text = _find_balanced_object(decoded, start)
    if obj_text is None:
        return None
    try:
        product = json.loads(obj_text)
    except json.JSONDecodeError:
        return None
    return product if isinstance(product, dict) else None


def _fetch_detail(client: PoliteClient, item: GearItem) -> dict | None:
    resp = client.get(item.productUrl)
    product = _extract_initial_product(resp.text)
    if not product:
        return None
    return _parse_product_detail(product)


def _parse_product_detail(product: dict) -> dict:
    """Pure parse of one PDP's `initialProduct` object into the subset of
    GearItem fields a detail fetch can fill. See the module docstring's
    "2026-11-12 detail enrichment" for where each field comes from.
    """
    name = (product.get("title") or "").strip()

    description = None
    short_desc = product.get("short_desc") or ""
    if short_desc:
        badge_idx = short_desc.find(_PROMO_BADGE_MARKER)
        core = short_desc[:badge_idx] if badge_idx != -1 else short_desc
        description = clean_description(core, name)

    specs: dict[str, str] = {}
    extra = product.get("extra") or {}
    for entry in extra.get("p_extra_features") or []:
        label = (entry.get("title") or "").strip()
        values = [
            v.get("title", "").strip()
            for v in entry.get("value") or []
            if (v.get("title") or "").strip()
        ]
        if label and values:
            specs.setdefault(label, ", ".join(values))

    features: list[str] = []
    for chip in extra.get("p_extra_attributes") or []:
        title = (chip.get("title") or "").strip()
        if chip.get("checked") and title and len(features) < MAX_FEATURES:
            features.append(title)

    images: list[str] = []
    seen_images: set[str] = set()
    for image in product.get("images") or []:
        path = image.get("src")
        if not path or path in seen_images:
            continue
        seen_images.add(path)
        images.append(path if path.startswith("http") else f"{IMAGE_CDN}{path}")

    regular_price = product.get("regular_price")
    compare_price = product.get("compare_price")
    original_price_vnd = None
    if (
        isinstance(regular_price, (int, float))
        and isinstance(compare_price, (int, float))
        and compare_price > regular_price
    ):
        original_price_vnd = int(compare_price)

    options = product.get("options") or []
    size_option_index = None
    for index, option in enumerate(options):
        title_lower = unidecode(option.get("title") or "").lower()
        if "size" in title_lower or "kich thuoc" in title_lower or "kich co" in title_lower:
            size_option_index = index
            break

    sizes: list[GearSize] = []
    if size_option_index is not None:
        option_key = f"option{size_option_index + 1}"
        order: list[str] = []
        available_by_label: dict[str, bool] = {}
        for variant in product.get("variants") or []:
            label = (variant.get(option_key) or "").strip()
            if not label:
                continue
            available = bool(variant.get("quantity") or 0)
            if label not in available_by_label:
                order.append(label)
                available_by_label[label] = available
            else:
                available_by_label[label] = available_by_label[label] or available
        sizes = [GearSize(label=label, available=available_by_label[label]) for label in order]

    in_stock = product.get("available")
    if not isinstance(in_stock, bool):
        in_stock = None

    gender = normalize_gender(product.get("gender_type"))

    sku = _extract_sku(product)

    return {
        "description": description,
        "images": images,
        "originalPriceVnd": original_price_vnd,
        "sizes": sizes,
        "inStock": in_stock,
        "gender": gender,
        "sku": sku,
        "specs": specs,
        "features": features,
        "detailFetchedAt": now_iso(),
    }


def _extract_sku(product: dict) -> str | None:
    """No clean per-product SKU field is exposed directly, but every
    variant's own `sync_product[0].label` embeds the real style code as a
    stable prefix shared across every color/size of the same product (e.g.
    "24CM.MAWRN.SOZ793.<color>.<size>_<name>" - confirmed live), recovered
    the same "common prefix, trimmed back to the last '.'" way
    `gear_base.common_variant_sku_prefix` does for the Shopify/Haravan
    sources' per-size SKUs.
    """
    labels: list[str] = []
    for variant in product.get("variants") or []:
        sync_product = variant.get("sync_product") or []
        if sync_product and sync_product[0].get("label"):
            labels.append(sync_product[0]["label"])
    if not labels:
        return None
    prefix = os.path.commonprefix(labels)
    if "." in prefix:
        prefix = prefix.rsplit(".", 1)[0]
    return prefix or None
