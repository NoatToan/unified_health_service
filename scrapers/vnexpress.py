"""Tier-1 scraper: VnExpress "Lịch giải chạy" (running race calendar).

https://vnexpress.net/the-thao/marathon/lich-giai-chay

Server-rendered static HTML. Shows name, start date, province, terrain and
distances for roughly the next two months. No price / registration link is
published here, so this source owns distances/terrain in the merge, not
price/status (see pipeline/merge.py).
"""
from __future__ import annotations

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
    parse_dd_mm,
    parse_vn_month_header,
)

SOURCE_NAME = "vnexpress"
LISTING_URL = "https://vnexpress.net/the-thao/marathon/lich-giai-chay"


def scrape(client: PoliteClient) -> list[Race]:
    resp = client.get(LISTING_URL)
    tree = HTMLParser(resp.text)
    container = tree.css_first("#content-list-tournament")
    if container is None:
        return []

    seen_at = now_iso()
    races: list[Race] = []
    current_year: int | None = None

    for node in container.iter(include_text=False):
        classes = (node.attributes.get("class") or "")
        if node.tag == "h2" and "date-month" in classes:
            parsed = parse_vn_month_header(node.text(strip=True))
            if parsed:
                _month, current_year = parsed
        elif node.tag == "div" and "list-run-plan" in classes:
            if current_year is None:
                continue
            for item in node.css(".item"):
                race = _parse_item(item, current_year, seen_at)
                if race is not None:
                    races.append(race)

    return races


def _parse_item(item, year: int, seen_at: str) -> Race | None:
    month_div = item.css_first(".date .month")
    title_p = item.css_first(".title-news p[title]")
    if month_div is None or title_p is None:
        return None

    start = parse_dd_mm(month_div.text(strip=True), year)
    if start is None:
        return None

    name = (title_p.attributes.get("title") or title_p.text(strip=True)).strip()
    if not name:
        return None

    addr = item.css_first(".location .address")
    province = addr.text(strip=True) if addr is not None else None

    terrain_span = item.css_first(".flex.note > span")
    terrain_text = terrain_span.text(strip=True) if terrain_span is not None else None
    terrain = guess_terrain(name, terrain_text)

    distances: list[Distance] = []
    for span in item.css(".distance span"):
        label = " ".join(span.text(strip=True).split())
        if not label:
            continue
        distances.append(Distance(label=label, km=label_to_km(label)))

    # The listing page already carries a banner thumbnail per item, so we use
    # it directly instead of fetching a detail page just for the image.
    thumb_img = item.css_first(".thumb-art img")
    image_url = (thumb_img.attributes.get("src") or "").strip() or None if thumb_img is not None else None

    start_str = start.isoformat()
    return Race(
        id=make_id(name, start_str),
        name=name,
        startDate=start_str,
        province=province,
        location=province,
        terrain=terrain,
        distances=distances,
        imageUrl=image_url,
        sources=[SourceRef(name=SOURCE_NAME, url=LISTING_URL, lastSeenAt=seen_at)],
        firstSeenAt=seen_at,
        lastUpdatedAt=seen_at,
    )
