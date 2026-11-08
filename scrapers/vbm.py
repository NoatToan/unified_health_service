"""Tier-1 scraper: Vietnam's Best Marathons (VBM) race-info listing.

https://bestmarathon.vn/race-info/

Static WordPress page (heavy, ~900 KB) that embeds every race as an
`<article class="row-link race-row ...">` with rich `data-*` attributes
(name, province, organizer, year, distances, status). This is the widest
coverage of the three Tier-1 sources, so it owns distances/terrain in the
merge, not price/status (see pipeline/merge.py). No per-distance price is
published here.
"""
from __future__ import annotations

import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from scrapers.base import (
    Distance,
    PoliteClient,
    Race,
    SourceRef,
    guess_terrain,
    label_to_km,
    make_id,
    now_iso,
    parse_dd_mm_yyyy,
    truncate_text,
)

SOURCE_NAME = "vbm"
LISTING_URL = "https://bestmarathon.vn/race-info/"

_DATE_RE = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")


def scrape(client: PoliteClient) -> list[Race]:
    resp = client.get(LISTING_URL)
    tree = HTMLParser(resp.text)
    seen_at = now_iso()

    races: list[Race] = []
    for article in tree.css("article.race-row"):
        if article.attributes.get("data-status") != "upcoming":
            continue
        race = _parse_article(article, seen_at)
        if race is not None:
            races.append(race)
    return races


def _parse_article(article, seen_at: str) -> Race | None:
    title_link = article.css_first("a.title-link")
    raw_name = (
        title_link.text(strip=True)
        if title_link is not None
        else (article.attributes.get("data-name") or "")
    )
    name = _normalize_name(raw_name)
    if not name:
        return None

    detail_url = title_link.attributes.get("href") if title_link is not None else None

    info_spans = article.css(".col-content span.inline-flex")
    date_text = None
    province_text = None
    for span in info_spans:
        text = " ".join(span.text(strip=True).split())
        if _DATE_RE.search(text) and date_text is None:
            date_text = text
        elif text and province_text is None:
            province_text = text

    start = parse_dd_mm_yyyy(date_text) if date_text else None
    if start is None:
        return None

    province = province_text or _normalize_name(article.attributes.get("data-province") or "") or None

    organizer = (article.attributes.get("data-organizer") or "").strip() or None

    distances: list[Distance] = []
    raw_distances = article.attributes.get("data-distances") or ""
    for label in raw_distances.split(","):
        label = label.strip().lower()
        if not label:
            continue
        distances.append(Distance(label=label, km=label_to_km(label)))

    # Each row carries its own banner image (falls back to a generic SVG
    # badge when the organizer hasn't supplied one yet - no <img> then), and a
    # short one-line blurb, both already on the listing page - no need to
    # fetch the detail page just for these.
    banner_img = article.css_first(".banner img.banner-img")
    image_url = (banner_img.attributes.get("src") or "").strip() or None if banner_img is not None else None

    description = None
    desc_p = article.css_first(".col-content p")
    if desc_p is not None:
        desc_text = " ".join(desc_p.text(strip=True).split())
        if desc_text:
            description = truncate_text(desc_text)

    # VBM doesn't publish an explicit terrain field, so fall back to keyword
    # detection - on the name first, then (since we already have it) the
    # blurb, which often mentions "rừng"/"núi"/"jungle" for off-road races
    # that the name alone wouldn't give away (e.g. "Cuc Phuong Jungle Paths").
    terrain = guess_terrain(name, description=description)

    start_str = start.isoformat()
    return Race(
        id=make_id(name, start_str),
        name=name,
        startDate=start_str,
        province=province,
        location=province,
        terrain=terrain,
        distances=distances,
        organizer=organizer,
        registrationUrl=detail_url,
        imageUrl=image_url,
        description=description,
        sources=[SourceRef(name=SOURCE_NAME, url=detail_url or LISTING_URL, lastSeenAt=seen_at)],
        firstSeenAt=seen_at,
        lastUpdatedAt=seen_at,
    )


def _normalize_name(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return raw
    # VBM renders names in ALL CAPS; title-case them for a nicer display name.
    if raw == raw.upper():
        return raw.title()
    return raw
