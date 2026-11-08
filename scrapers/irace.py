"""Tier-1 scraper: iRace ticket portal, marathon category.

https://ticket.irace.vn/categories/marathon

Static HTML, paginated via `?page=N`. This is the main Vietnamese race
ticketing platform, so it owns price/registration-status in the merge (see
pipeline/merge.py). It does not expose a clean per-distance breakdown on the
listing page (that lives behind each event's detail page), so this scraper
only reports an overall `priceFromVnd` / `registrationStatus` and leaves
`distances`/`terrain` for the other sources to fill in.
"""
from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from scrapers.base import (
    MAX_PAGES_PER_SOURCE,
    PoliteClient,
    Race,
    SourceRef,
    guess_terrain,
    make_id,
    now_iso,
    parse_dd_mm_yyyy,
    parse_vnd_price,
)

SOURCE_NAME = "irace"
BASE_URL = "https://ticket.irace.vn/categories/marathon"

# Pagination here is effectively unbounded (it includes years of past events),
# so we cap the number of pages fetched per run for politeness. The pipeline
# filters out past races anyway, so missing deep pages just means missing
# older/unrelated listings, not current ones.
MAX_PAGES = min(10, MAX_PAGES_PER_SOURCE)


def scrape(client: PoliteClient) -> list[Race]:
    seen_at = now_iso()
    races: list[Race] = []
    seen_urls: set[str] = set()

    for page in range(1, MAX_PAGES + 1):
        url = BASE_URL if page == 1 else f"{BASE_URL}?page={page}"
        resp = client.get(url)
        tree = HTMLParser(resp.text)
        cards = tree.css(".wrap-item-event .card.item-event")
        if not cards:
            break

        new_on_page = 0
        for card in cards:
            race = _parse_card(card, seen_at)
            if race is None:
                continue
            source_url = race.sources[0].url
            if source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            races.append(race)
            new_on_page += 1

        if new_on_page == 0:
            # Pagination looped back / ran out of new content.
            break

    return races


def _parse_card(card, seen_at: str) -> Race | None:
    title_a = card.css_first(".card-title")
    if title_a is None:
        return None
    name = title_a.text(strip=True)
    if not name:
        return None
    detail_url = title_a.attributes.get("href") or BASE_URL

    infos = card.css(".card-info .item-info")
    date_text = infos[0].text(strip=True) if len(infos) > 0 else ""
    location_text = infos[1].text(strip=True) if len(infos) > 1 else None

    start = parse_dd_mm_yyyy(date_text)
    if start is None:
        return None

    price_vnd, status = _parse_price_and_status(card)

    terrain = guess_terrain(name)

    # The listing page already carries a banner image per card, so we use it
    # directly instead of fetching the detail page just for the image.
    img_node = card.css_first(".card-img-wrap img")
    image_url = (img_node.attributes.get("src") or "").strip() or None if img_node is not None else None

    start_str = start.isoformat()
    return Race(
        id=make_id(name, start_str),
        name=name,
        startDate=start_str,
        province=location_text,
        location=location_text,
        terrain=terrain,
        priceFromVnd=price_vnd,
        registrationStatus=status,
        registrationUrl=detail_url,
        imageUrl=image_url,
        sources=[SourceRef(name=SOURCE_NAME, url=detail_url, lastSeenAt=seen_at)],
        firstSeenAt=seen_at,
        lastUpdatedAt=seen_at,
    )


def _parse_price_and_status(card) -> tuple[int | None, str]:
    price_node = card.css_first(".card-footer .price")
    if price_node is None:
        return None, "unknown"

    text = price_node.text(strip=True).lower()
    if "đóng" in text:
        return None, "closed"
    if "hết" in text or "sold" in text:
        return None, "sold_out"

    price = parse_vnd_price(price_node.text(strip=True))
    if price is not None:
        return price, "open"
    return None, "unknown"
