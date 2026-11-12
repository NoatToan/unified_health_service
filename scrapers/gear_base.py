"""Shared building blocks for the runner-gear scrapers: the GearItem/GearVariant
models, HTML/text helpers used to parse product-detail pages (PDPs), and a
stable-id helper.

This is a METADATA + LINK-OUT catalog, never a store and never a full
reproduction of a product page: every item always keeps `productUrl` as the
only way to actually buy it, and nothing here ever touches a
cart/checkout/payment endpoint or collects user data.

**2026-11-12 detail-enrichment policy** (see docs_research/GEAR_SOURCES_RESEARCH.md
for the source-by-source rationale): `description` used to be deliberately
reduced to a thin "<Brand> <category>." placeholder out of caution about
reproducing marketing copy. That's superseded now - this pipeline instead
stores **factual detail genuinely published by the vendor's own product
page**: a stripped/truncated real description, structured specs (weight,
drop, material, ...) pulled from the PDP's own spec table/bullet list, a
short factual features list when the PDP has one, sizes/stock when the
source states it, and the full image gallery. None of this is fabricated or
guessed - every field is either copied verbatim from a structured field the
source itself exposes, or (same spirit as `truncate_text`) mechanically
trimmed/whitespace-normalized from the source's own text. `productUrl`
remains the only way to actually buy the item, and a detail fetch never
touches a cart/checkout/account endpoint (see `scrapers/base.py`'s
`PoliteClient`, which still does the robots.txt check and rate limiting for
every one of these extra requests).

See docs_research/GEAR_SOURCES_RESEARCH.md for the source research, including
the "2026-11-12 detail enrichment" section listing exactly which fields each
source fills and where they come from, and the rationale behind `variants`
(per-color data, only ever populated when a source genuinely exposes it -
never fabricated).
"""
from __future__ import annotations

import html as _html
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Callable

from pydantic import BaseModel, Field
from unidecode import unidecode

from scrapers.base import now_iso, truncate_text

VALID_CATEGORIES = {"shoes", "apparel", "accessories"}
VALID_GENDERS = {"men", "women", "unisex", "kids"}

# Cap on PDP (detail) fetches per source per run - a detail fetch is one
# *extra* request per product on top of the listing fetch(es), so this keeps
# a from-scratch run (no usable cache yet) bounded: Puma has ~204 items,
# Coolmate ~59, so 120/source keeps the whole gear step well under the CI
# budget even on a cold cache. `pipeline.gear_main`'s cache (below) means
# later runs only need to fetch products that are new or whose cached detail
# has aged out, so coverage reaches 100% over a small number of runs rather
# than requiring one single very long run.
MAX_DETAIL_FETCHES_PER_SOURCE = 120

# How long a previously-fetched detail is trusted before a source is asked
# again - these storefronts' product pages (spec tables, descriptions,
# stock) don't change minute to minute, so a week-old detail is still
# genuinely representative and reusing it is both honest (same real data,
# just not re-fetched today) and the whole reason the cache keeps this
# pipeline's politeness budget sustainable.
DETAIL_CACHE_MAX_AGE_DAYS = 7

MAX_FEATURES = 8
MAX_DETAIL_DESCRIPTION_LENGTH = 500

# Fields a detail-page parse can fill, reused by every scraper's cache-reuse
# logic (`should_reuse_cached_detail` / `apply_cached_detail` below) so
# "which fields count as detail" is defined in exactly one place.
DETAIL_FIELDS = [
    "description",
    "images",
    "originalPriceVnd",
    "sizes",
    "inStock",
    "gender",
    "sku",
    "specs",
    "features",
    "detailFetchedAt",
]


class GearSize(BaseModel):
    label: str
    available: bool | None = None


class GearVariant(BaseModel):
    color: str
    imageUrl: str | None = None
    productUrl: str
    # Per-variant detail, only ever populated when the source genuinely
    # exposes per-color data for it (e.g. a Shopify/Haravan option set with
    # `Color` *and* `Size`, where each color has its own size/price rows) -
    # left empty/null otherwise, same "never fabricate" rule as the rest of
    # this schema.
    priceVnd: int | None = None
    images: list[str] = Field(default_factory=list)
    sizes: list[GearSize] = Field(default_factory=list)


class GearItem(BaseModel):
    id: str
    name: str
    brand: str
    category: str
    sourceName: str
    priceVnd: int | None = None
    # List price when the item is on sale (`priceVnd` is always the current
    # selling price). Null when the source shows no discount.
    originalPriceVnd: int | None = None
    description: str | None = None
    imageUrl: str | None = None
    # Full gallery; `imageUrl` stays the primary/first image for a consumer
    # that doesn't care about the rest.
    images: list[str] = Field(default_factory=list)
    productUrl: str
    sizes: list[GearSize] = Field(default_factory=list)
    inStock: bool | None = None
    # "men" | "women" | "unisex" | "kids" | null. Resolved in priority order:
    # (1) an explicit source field/tag (normalize_gender/
    # gender_from_shopify_tags, from each scraper's PDP detail fetch), (2)
    # per-gender listing membership for sources whose own collections are
    # explicitly gendered (resolve_listing_gender, applied by
    # lining_gear.py/coolmate_gear.py before detail enrichment runs), (3)
    # a name/title keyword fallback (gender_from_text, applied once
    # centrally in pipeline/gear_main.py) - never a blind guess beyond
    # those three signals; null when none of them found anything.
    gender: str | None = None
    sku: str | None = None
    # Factual specs (weight, drop/offset, material, technology, ...) taken
    # from a structured field or a spec table/bullet list on the PDP - the
    # source's own label is kept as the dict key (no fabricated/translated
    # taxonomy imposed on top of what the source actually published).
    specs: dict[str, str] = Field(default_factory=dict)
    # Short factual bullet points from a PDP features/highlights list, each
    # trimmed, capped at MAX_FEATURES.
    features: list[str] = Field(default_factory=list)
    variants: list[GearVariant] = Field(default_factory=list)
    # UTC timestamp of the last successful PDP (detail) fetch for this item,
    # or null if it has only ever been seen at listing level. Drives the
    # detail-cache reuse window (DETAIL_CACHE_MAX_AGE_DAYS).
    detailFetchedAt: str | None = None
    crawledAt: str


# --------------------------------------------------------------------------- #
# Gender normalization
# --------------------------------------------------------------------------- #

_GENDER_MAP = {
    "nam": "men",
    "men": "men",
    "man": "men",
    "male": "men",
    "nu": "women",
    "women": "women",
    "woman": "women",
    "female": "women",
    "unisex": "unisex",
    "tre em": "kids",
    "kid": "kids",
    "kids": "kids",
    "children": "kids",
    "child": "kids",
    "boys": "kids",
    "girls": "kids",
    "junior": "kids",
}


def normalize_gender(raw: str | None) -> str | None:
    """Map a source's own gender label (English or Vietnamese, any casing -
    "Nam", "Nữ", "Men", "MALE", "Unisex", ...) to one of VALID_GENDERS.
    Returns None for anything unrecognized rather than guessing.
    """
    if not raw:
        return None
    lowered = unidecode(raw).strip().lower()
    return _GENDER_MAP.get(lowered)


def resolve_listing_gender(genders: set[str] | None) -> str | None:
    """Collapse the set of gender tags a product was seen under across a
    source's own per-gender *listing* pages (e.g. Li-Ning's
    `giay-chay-bo-nam-2`/`giay-chay-bo-nu-2`, Coolmate's
    `quan-ao-chay-bo-nu`) into a single `GearItem.gender` value: the one tag
    if there's only one, `"unisex"` if the product was genuinely seen under
    more than one distinct gender's listing (e.g. both the men's and
    women's collection), or `None` if it wasn't seen under any gendered
    listing at all. Never guesses beyond what the source's own listing
    structure actually showed.
    """
    if not genders:
        return None
    if len(genders) == 1:
        return next(iter(genders))
    return "unisex"


# --------------------------------------------------------------------------- #
# Keyword fallback (name/title only) - the last resort when a source has no
# explicit gender field/tag/listing at all (see normalize_gender,
# gender_from_shopify_tags, resolve_listing_gender above, which are always
# preferred and checked first). Diacritics-insensitive, whole-word matching
# only, so this never fires on a gender word that's merely a substring of a
# different word (e.g. "nam" inside "Việt Nam"/"Vietnam", "nu" inside
# "nude") - see `gender_from_text`'s docstring for the exact false-positive
# cases this was built to avoid.
# --------------------------------------------------------------------------- #

# "Việt Nam"/"Vietnam" is stripped before scanning so its own "Nam" is never
# mistaken for the men's keyword - this is the one false positive the task
# brief explicitly calls out ("'nam' inside other words").
_VIET_NAM_RE = re.compile(r"\bviet\s*nam\b")
_WORD_RE = re.compile(r"[a-z0-9]+")
_KIDS_PHRASE_RE = re.compile(r"\btre\s+em\b")  # "trẻ em", diacritics stripped

_MEN_WORDS = {"men", "mens", "nam"}
_WOMEN_WORDS = {"women", "womens", "wmns", "nu"}
_UNISEX_WORDS = {"unisex"}
_KIDS_WORDS = {"kids", "kid", "junior"}


def gender_from_text(text: str | None) -> str | None:
    """Best-effort `men`/`women`/`unisex`/`kids` guess from a product's own
    name/title - VN ("nam", "nữ", "trẻ em") and EN ("men's"/"mens", "women's"
    /"womens"/"wmns", "unisex", "kids"/"junior") keywords, diacritics-
    insensitive, matched as whole words only (never a substring match, so
    "nu" never matches inside "nude", "nam" never matches inside "Vietnam"/
    "Việt Nam" - that phrase is stripped out first). A name that mentions
    both a men's and a women's keyword (e.g. "Women's & Men's Running Tee")
    resolves to `"unisex"` rather than arbitrarily picking one side. Returns
    `None` - never a guess - when nothing recognizable is present. This is
    only ever a last resort: callers should always try a source's own
    explicit gender field/tag/listing first.
    """
    if not text:
        return None
    normalized = _VIET_NAM_RE.sub(" ", unidecode(text).lower())
    words = set(_WORD_RE.findall(normalized))

    has_unisex = bool(words & _UNISEX_WORDS)
    has_kids = bool(words & _KIDS_WORDS) or _KIDS_PHRASE_RE.search(normalized) is not None
    has_men = bool(words & _MEN_WORDS)
    has_women = bool(words & _WOMEN_WORDS)

    if has_unisex or (has_men and has_women):
        return "unisex"
    if has_kids:
        return "kids"
    if has_men:
        return "men"
    if has_women:
        return "women"
    return None


def fill_missing_gender_from_text(items: list[GearItem]) -> list[GearItem]:
    """Apply `gender_from_text` to every item whose `gender` is still `None`
    after every source-provided signal (explicit field/tag, per-gender
    listing membership) has already had its chance - the pipeline-wide last
    resort for rule 2 of the gender feature (see
    docs_research/GEAR_SOURCES_RESEARCH.md). Items that already have a
    gender are returned unchanged.
    """
    result: list[GearItem] = []
    for item in items:
        if item.gender is None:
            guessed = gender_from_text(item.name)
            if guessed:
                item = item.model_copy(update={"gender": guessed})
        result.append(item)
    return result


# --------------------------------------------------------------------------- #
# HTML/text helpers for parsing vendor PDP body text (descriptions, spec
# tables, bullet lists) - deliberately simple regex-based parsing, same
# "no JS execution, no heavyweight HTML framework needed" spirit as the
# scrapers themselves. These are reused by puma_gear.py, salomon_gear.py,
# lining_gear.py and coolmate_gear.py's own small _parse_* detail functions.
# --------------------------------------------------------------------------- #

_WHITESPACE_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"(?is)<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_BR_RE = re.compile(r"(?i)<br\b[^>]*>")
_BLOCK_END_RE = re.compile(r"(?i)</(p|div|li|tr|h[1-6])>")
_TABLE_RE = re.compile(r"(?is)<table\b[^>]*>(.*?)</table>")
_ROW_RE = re.compile(r"(?is)<tr\b[^>]*>(.*?)</tr>")
_CELL_RE = re.compile(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>")
_LIST_ITEM_RE = re.compile(r"(?is)<li\b[^>]*>(.*?)</li>")


def strip_html_text(fragment: str) -> str:
    """Strip HTML tags from a fragment (a PDP's `body_html`/`longDescription`,
    not a full page) into whitespace-normalized plain text, for use as a
    `description` candidate. Tags are replaced with a space (not removed
    outright) so words straddling a removed tag don't get glued together.
    """
    text = _SCRIPT_STYLE_RE.sub(" ", fragment)
    text = _TAG_RE.sub(" ", text)
    text = _html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _strip_one_line(fragment: str) -> str:
    text = _TAG_RE.sub(" ", fragment)
    text = _html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def extract_table_pairs(fragment: str) -> dict[str, str]:
    """Extract `{label: value}` pairs from the first 2-column `<table>` found
    in `fragment` (e.g. Salomon's "Thông tin chi tiết" spec table). Rows
    that don't have exactly 2 cells, or where either cell is empty once
    stripped, are skipped.
    """
    pairs: dict[str, str] = {}
    table_match = _TABLE_RE.search(fragment)
    if table_match is None:
        return pairs
    for row_match in _ROW_RE.finditer(table_match.group(1)):
        cells = [_strip_one_line(c) for c in _CELL_RE.findall(row_match.group(1))]
        if len(cells) != 2:
            continue
        label, value = cells[0].strip(" :"), cells[1].strip()
        if label and value:
            pairs.setdefault(label, value)
    return pairs


def split_label_value(line: str) -> tuple[str, str] | None:
    """Split a "Label: Value" / "Label : Value" text line into (label,
    value). Returns None if there's no colon, or the part before it is too
    long to plausibly be a label (i.e. it's prose with an incidental colon,
    not a fact line) - a deliberately conservative heuristic so this never
    misclassifies a marketing sentence as a spec.
    """
    if ":" not in line:
        return None
    label, _, value = line.partition(":")
    label = label.strip()
    value = value.strip()
    if not label or not value:
        return None
    if len(label) > 40 or len(label.split()) > 6:
        return None
    return label, value


def extract_bullet_facts(fragment: str) -> tuple[dict[str, str], list[str]]:
    """Extract facts from every `<li>` in `fragment` (e.g. Li-Ning's
    "Chất liệu vải : Vải + TPU" bullets, or Puma's "FEATURES & BENEFITS"/
    "DETAILS" lists). Each bullet is classified by `split_label_value`:
    `"Label: Value"` bullets become spec entries, plain short bullets
    become `features` entries (capped at MAX_FEATURES, in document order).
    Returns `(specs, features)`.
    """
    specs: dict[str, str] = {}
    features: list[str] = []
    for li_match in _LIST_ITEM_RE.finditer(fragment):
        line = _strip_one_line(li_match.group(1))
        if not line:
            continue
        pair = split_label_value(line)
        if pair:
            specs.setdefault(*pair)
        elif len(features) < MAX_FEATURES and len(line) <= 150:
            features.append(line)
    return specs, features


def extract_line_specs(fragment: str) -> dict[str, str]:
    """Like `extract_bullet_facts`'s spec half, but for "Label: Value" lines
    inside plain `<p>`/`<br>`-separated text rather than a `<ul>`/`<table>`
    (e.g. Salomon's backpack PDPs, which put "Chiều dài lưng (cm): 44<br>..."
    straight inside a `<p>`). Table rows and `<li>` bullets should be
    stripped from `fragment` before calling this (see each scraper's detail
    parser) so a value isn't double-counted.
    """
    text = _BR_RE.sub("\n", fragment)
    text = _BLOCK_END_RE.sub("\n", text)
    specs: dict[str, str] = {}
    for raw_line in text.split("\n"):
        line = _strip_one_line(raw_line)
        if not line:
            continue
        pair = split_label_value(line)
        if pair:
            specs.setdefault(*pair)
    return specs


_HEADING_RE = re.compile(r"(?is)<h[1-6]\b[^>]*>.*?</h[1-6]>")


def extract_description_candidate(fragment: str) -> str:
    """Prose-only candidate text for `description`, from a PDP's
    `body_html`/`longDescription` fragment: strips out `<table>`/`<ul>`/`<li>`
    blocks (those become `specs`/`features`, not prose) and heading tags'
    own text (section headers like "PRODUCT STORY" or a repeated
    `<h4>`-wrapped product title), then returns the remaining text stripped
    of markup and whitespace-normalized. Not guaranteed to be only the
    "real" marketing paragraph - just a reasonable, mechanical reduction of
    the source's own text, same spirit as the rest of this module.
    """
    text = remove_tag_blocks(fragment, "table")
    text = remove_tag_blocks(text, "li")
    text = remove_tag_blocks(text, "ul")
    text = remove_tag_blocks(text, "ol")
    text = _HEADING_RE.sub(" ", text)
    return strip_html_text(text)


# Garment/shoe "how to wash/store this" care instructions (Li-Ning puts
# these in the *same* `<ul>` as its real material/tech bullets, under a
# "Hướng dẫn bảo quản" heading) are real text but not a product "feature" -
# cut the fragment before this heading so they're never misclassified as
# one. A plain case-insensitive substring search on "bảo quản" is enough
# (it's always part of a "Hướng dẫn bảo quản"/"Cách bảo quản" heading in
# practice) and safe to apply even when the marker isn't present at all.
_CARE_SECTION_MARKER = "bảo quản"

# Legal/manufacturer boilerplate rows that show up in some sources' own spec
# tables (e.g. Salomon's "Thông tin chi tiết" table always ends with the
# importer's name/address) - real table data, but not a *gear* spec, so it's
# filtered out of `specs` rather than kept as factual-but-irrelevant noise.
_BOILERPLATE_SPEC_LABELS = {
    "nha nhap khau va phan phoi",
    "dia chi",
    "nha san xuat",
}


def cut_before_care_section(fragment: str) -> str:
    """Return `fragment` truncated right before its first "bảo quản" (care
    instructions) marker, or unchanged if there isn't one.
    """
    idx = fragment.lower().find(_CARE_SECTION_MARKER)
    if idx == -1:
        return fragment
    return fragment[:idx]


def drop_boilerplate_specs(specs: dict[str, str]) -> dict[str, str]:
    """Filter legal/manufacturer-address rows (see _BOILERPLATE_SPEC_LABELS)
    out of a parsed specs dict - same label regardless of accenting/casing.
    """
    return {
        key: value
        for key, value in specs.items()
        if unidecode(key).strip().lower() not in _BOILERPLATE_SPEC_LABELS
    }


def remove_tag_blocks(fragment: str, tag: str) -> str:
    """Remove every `<tag>...</tag>` block (non-greedy, case-insensitive)
    from `fragment` - used to strip a `<table>` or every `<li>` out before
    extracting the surrounding prose/line-level specs, so content already
    captured by `extract_table_pairs`/`extract_bullet_facts` isn't also
    picked up by `extract_line_specs` or re-included in `description`.
    """
    return re.sub(rf"(?is)<{tag}\b[^>]*>.*?</{tag}>", " ", fragment)


def clean_description(text: str | None, name: str) -> str | None:
    """Trim a product name accidentally duplicated at the very start of a
    description (common when a PDP's body text opens with its own title,
    e.g. a `<h4><strong>Giày ... </strong></h4>` heading) and truncate to
    MAX_DETAIL_DESCRIPTION_LENGTH. Returns None for empty/whitespace-only
    input rather than an empty string, matching GearItem.description's
    "null when nothing real exists" contract.
    """
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.lower().startswith(name.strip().lower()):
        stripped = stripped[len(name.strip()):].strip(" -:|–—")
    if not stripped:
        return None
    return truncate_text(stripped, MAX_DETAIL_DESCRIPTION_LENGTH)


# --------------------------------------------------------------------------- #
# Detail cache (reuse a previous run's PDP fields for an unchanged product)
# --------------------------------------------------------------------------- #

def should_reuse_cached_detail(
    previous_raw: dict | None, max_age_days: int = DETAIL_CACHE_MAX_AGE_DAYS
) -> bool:
    """True if `previous_raw` (a previous run's raw dict for this same
    `productUrl`, from the last latest.json) has a `detailFetchedAt` younger
    than `max_age_days`. False (never reuse) if there's no previous data, no
    detail was ever fetched for it, or the timestamp can't be parsed.
    """
    if not previous_raw:
        return False
    fetched_at = previous_raw.get("detailFetchedAt")
    if not fetched_at:
        return False
    try:
        fetched = datetime.strptime(fetched_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - fetched) < timedelta(days=max_age_days)


def apply_cached_detail(item: GearItem, previous_raw: dict) -> GearItem:
    """Copy the detail fields (DETAIL_FIELDS) from a previous run's raw item
    dict onto a freshly-scraped `item`, keeping every listing-level field
    (name/price/imageUrl/variants/...) from the fresh scrape. Used when
    `should_reuse_cached_detail` says the cached detail is still fresh
    enough, so this run doesn't need its own extra PDP request for it.
    """
    data = item.model_dump()
    for field in DETAIL_FIELDS:
        if field not in previous_raw:
            continue
        if field == "gender" and not previous_raw.get("gender") and data.get("gender"):
            # The cached detail fetch never found a gender tag, but this
            # item already carries one from its source's own per-gender
            # listing (resolve_listing_gender) - keep that rather than
            # clobbering it with the cache's null.
            continue
        data[field] = previous_raw[field]
    return GearItem.model_validate(data)


def enrich_with_detail(
    client,
    items: list[GearItem],
    previous_by_url: dict[str, dict] | None,
    fetch_detail: Callable[[object, GearItem], dict | None],
    source_name: str,
) -> list[GearItem]:
    """Shared detail-enrichment loop used by every gear scraper's `scrape()`:
    for each item, reuse a cached detail if it's still fresh
    (`should_reuse_cached_detail`); otherwise spend one of this source's
    `MAX_DETAIL_FETCHES_PER_SOURCE` budget fetching+parsing it fresh via
    `fetch_detail(client, item) -> dict | None` (a per-source function that
    does the one extra HTTP request and returns a dict of GearItem fields
    to merge in, or None/raises if the PDP didn't yield anything usable).
    A failed fetch, an exhausted budget, or a PDP with nothing parseable
    never drops the item - it's kept with whatever listing-level data it
    already had.
    """
    previous_by_url = previous_by_url or {}
    fetches_used = 0
    enriched: list[GearItem] = []
    for item in items:
        previous_raw = previous_by_url.get(item.productUrl)
        if should_reuse_cached_detail(previous_raw):
            item = apply_cached_detail(item, previous_raw)
        elif fetches_used < MAX_DETAIL_FETCHES_PER_SOURCE:
            fetches_used += 1
            try:
                detail = fetch_detail(client, item)
            except Exception as exc:  # noqa: BLE001 - a bad PDP must never drop the item
                print(
                    f"{source_name}_gear: detail fetch failed for {item.productUrl}: {exc}",
                    file=sys.stderr,
                )
                detail = None
            if detail:
                if not detail.get("gender") and item.gender:
                    # The PDP fetch didn't find a gender tag, but this item
                    # already carries one from its source's own per-gender
                    # listing (resolve_listing_gender) - don't clobber it
                    # with the fetch's null.
                    detail = {k: v for k, v in detail.items() if k != "gender"}
                item = item.model_copy(update=detail)
        enriched.append(item)
    return enriched


# --------------------------------------------------------------------------- #
# Shopify/Haravan product-detail parsing (shared by salomon_gear.py and
# lining_gear.py - both storefronts are the same platform family and
# `/products/<handle>.json` returns an identical shape on both, confirmed
# live 2026-11-12, see each scraper's module docstring).
# --------------------------------------------------------------------------- #

_GT_TAG_RE = re.compile(r"(?i)^GT_(.+)$")
_TAG_WORD_RE = re.compile(r"[a-z]+")
_TITLE_CODE_RE = re.compile(r"\b[A-Z][A-Z0-9-]{3,}\b")


def gender_from_shopify_tags(tags_field: str | None) -> str | None:
    """Both Salomon and Li-Ning's storefronts tag products with gender, just
    in different conventions, confirmed live on real products: Li-Ning uses
    an explicit `GT_Nam`/`GT_Nữ` tag (checked two real products, one of
    each); Salomon doesn't use that convention but does tag plain
    Vietnamese words like "Giày Nam"/"... Nam" into its tag list. Tries the
    explicit `GT_` convention first (unambiguous), then a whole-word
    nam/nữ/unisex check per tag (each tag here is a short discrete phrase,
    e.g. "Giày Nam" or "Trail Running Nam" - not free text, so this doesn't
    have the "Việt Nam" false-positive risk a title-wide scan would).
    """
    if not tags_field:
        return None
    tags = [t.strip() for t in tags_field.split(",") if t.strip()]
    for tag in tags:
        match = _GT_TAG_RE.match(tag)
        if match:
            gender = normalize_gender(match.group(1))
            if gender:
                return gender
    for tag in tags:
        words = set(_TAG_WORD_RE.findall(unidecode(tag).lower()))
        if "nam" in words:
            return "men"
        if "nu" in words:
            return "women"
        if "unisex" in words:
            return "unisex"
    return None


def extract_code_from_title(title: str) -> str | None:
    """Both storefronts' real product titles embed the vendor's own SKU/style
    code as an ALL-CAPS alphanumeric token (confirmed live: "... Salomon
    Alphacross 5 L47313300 Grey", "... Super Light 23 Nam ARBW017-17V") -
    returns the last such token (the trailing color name, if any, never
    matches: it has no digits), or None if the title has nothing matching.
    """
    candidates = [c for c in _TITLE_CODE_RE.findall(title) if any(ch.isdigit() for ch in c)]
    return candidates[-1] if candidates else None


def common_variant_sku_prefix(skus: list[str | None]) -> str | None:
    """Fallback product-code guess when the title doesn't embed one: every
    variant's own `sku` on these storefronts is `{code}{size}` (e.g.
    "ARBW017-17V6.5", "ARBW017-17V7", ... all share the literal prefix
    "ARBW017-17V"), so the real code is recoverable as their longest common
    prefix with the trailing size-ish characters trimmed off. Still a
    structured-field derivation, not an invented value.
    """
    cleaned = [s for s in skus if s]
    if not cleaned:
        return None
    prefix = os.path.commonprefix(cleaned)
    prefix = prefix.rstrip("0123456789./ -")
    return prefix or None


def parse_shopify_decimal_price(raw: object) -> int | None:
    """Shopify/Haravan's `products.json` prices VND as a decimal string
    (e.g. "2400000.00") - VND has no sub-unit, so this just rounds to int.
    """
    if raw is None:
        return None
    try:
        return int(round(float(raw)))
    except (TypeError, ValueError):
        return None


def parse_shopify_product_detail(product: dict) -> dict:
    """Parse a Shopify/Haravan product's full detail payload (the same
    `/products/<handle>.json` shape `salomon_gear.py` and `lining_gear.py`
    both fetch) into the subset of GearItem fields a detail fetch can fill.
    See docs_research/GEAR_SOURCES_RESEARCH.md's "2026-11-12 detail
    enrichment" section for exactly which source field backs each one.
    """
    title = (product.get("title") or "").strip()
    body_html = product.get("body_html") or ""
    facts_html = cut_before_care_section(body_html)

    table_specs = extract_table_pairs(facts_html)
    without_table = remove_tag_blocks(facts_html, "table")
    li_specs, features = extract_bullet_facts(without_table)
    without_li = remove_tag_blocks(without_table, "li")
    without_li = remove_tag_blocks(without_li, "ul")
    without_li = remove_tag_blocks(without_li, "ol")
    line_specs = extract_line_specs(without_li)

    specs: dict[str, str] = dict(table_specs)
    for extra in (li_specs, line_specs):
        for key, value in extra.items():
            specs.setdefault(key, value)
    specs = drop_boilerplate_specs(specs)

    description = None
    if body_html:
        description = clean_description(extract_description_candidate(body_html), title)

    images: list[str] = []
    seen_images: set[str] = set()
    for image in product.get("images") or []:
        src = image.get("src")
        if src and src not in seen_images:
            seen_images.add(src)
            images.append(src)

    options = product.get("options") or []
    size_option_index = None
    for index, option in enumerate(options):
        name = unidecode(option.get("name") or "").lower()
        if "size" in name or "kich thuoc" in name or "kich co" in name:
            size_option_index = index
            break

    variants = product.get("variants") or []
    sizes: list[GearSize] = []
    seen_labels: set[str] = set()
    if size_option_index is not None:
        option_key = f"option{size_option_index + 1}"
        for variant in variants:
            label = (variant.get(option_key) or "").strip()
            if not label or label in seen_labels:
                continue
            seen_labels.add(label)
            sizes.append(GearSize(label=label, available=variant.get("available")))

    in_stock = product.get("available")
    if not isinstance(in_stock, bool):
        in_stock = None

    original_price_vnd = None
    if variants:
        price_vnd = parse_shopify_decimal_price(variants[0].get("price"))
        compare_at = parse_shopify_decimal_price(variants[0].get("compare_at_price"))
        if price_vnd and compare_at and compare_at > price_vnd:
            original_price_vnd = compare_at

    gender = normalize_gender(specs.get("Giới tính")) or gender_from_shopify_tags(
        product.get("tags")
    )

    sku = specs.get("Mã SKU") or specs.get("SKU") or extract_code_from_title(title)
    if not sku:
        sku = common_variant_sku_prefix([v.get("sku") for v in variants])

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


# --------------------------------------------------------------------------- #
# Stable id
# --------------------------------------------------------------------------- #

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    text = unidecode(text).lower()
    text = _SLUG_RE.sub("-", text).strip("-")
    return text


def make_gear_id(source_name: str, key: str) -> str:
    """A stable id derived from the source name and a per-source key that is
    already unique and stable on that source (Puma: the numeric product id
    shared by every color row; Salomon: the Shopify product handle).
    """
    return f"{source_name}-{slugify(key)}"
