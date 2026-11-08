"""Shared building blocks for all scrapers: the Race/Distance/Source models, a polite
HTTP client (User-Agent, robots.txt check, per-host rate limiting, retries), and
Vietnamese date/price parsing helpers.
"""
from __future__ import annotations

import re
import time
import urllib.robotparser
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field
from unidecode import unidecode

USER_AGENT = (
    "UnifiedHealthRaceBot/1.0 "
    "(+https://noattoan.github.io/unified_health_service/bot.html)"
)

# Cap on pages fetched from any single source in one run (politeness).
MAX_PAGES_PER_SOURCE = 30

# Delay between requests to the same host, in seconds.
REQUEST_DELAY_SECONDS = 2.5

VALID_TERRAINS = {"road", "trail", "city_trail", "ultra", "triathlon", "virtual"}
VALID_STATUSES = {"open", "closed", "sold_out", "unknown"}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Distance(BaseModel):
    label: str
    km: float | None = None
    priceVnd: int | None = None
    status: str = "unknown"


class SourceRef(BaseModel):
    name: str
    url: str
    lastSeenAt: str


class Race(BaseModel):
    id: str
    name: str
    startDate: str
    endDate: str | None = None
    province: str | None = None
    location: str | None = None
    terrain: str = "road"
    distances: list[Distance] = Field(default_factory=list)
    priceFromVnd: int | None = None
    registrationStatus: str = "unknown"
    organizer: str | None = None
    registrationUrl: str | None = None
    imageUrl: str | None = None
    sources: list[SourceRef]
    firstSeenAt: str
    lastUpdatedAt: str


# --------------------------------------------------------------------------- #
# Polite HTTP client
# --------------------------------------------------------------------------- #

class RobotsBlocked(Exception):
    """Raised when robots.txt disallows fetching a URL."""


class PoliteClient:
    """A small httpx wrapper that:
    - sends a descriptive User-Agent
    - checks robots.txt once per host before the first request to that host
    - waits REQUEST_DELAY_SECONDS between requests to the same host
    - retries once on 429/5xx with backoff, then gives up
    """

    def __init__(self, delay: float = REQUEST_DELAY_SECONDS, timeout: float = 20.0):
        self._delay = delay
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_request_at: dict[str, float] = {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PoliteClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _robot_parser(self, host: str, scheme: str) -> urllib.robotparser.RobotFileParser:
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = f"{scheme}://{host}/robots.txt"
            try:
                resp = self._client.get(robots_url)
                if resp.status_code < 400:
                    rp.parse(resp.text.splitlines())
                else:
                    rp.allow_all = True  # no robots.txt -> assume allowed
            except httpx.HTTPError:
                rp.allow_all = True
            self._robots[host] = rp
        return self._robots[host]

    def _respect_rate_limit(self, host: str) -> None:
        last = self._last_request_at.get(host)
        if last is not None:
            elapsed = time.monotonic() - last
            wait = self._delay - elapsed
            if wait > 0:
                time.sleep(wait)
        self._last_request_at[host] = time.monotonic()

    def get(self, url: str) -> httpx.Response:
        parsed = urlparse(url)
        host = parsed.netloc
        rp = self._robot_parser(host, parsed.scheme)
        if not getattr(rp, "allow_all", False) and not rp.can_fetch(USER_AGENT, url):
            raise RobotsBlocked(f"robots.txt disallows fetching {url}")

        self._respect_rate_limit(host)

        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                resp = self._client.get(url)
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_exc = httpx.HTTPStatusError(
                        f"status {resp.status_code}", request=resp.request, response=resp
                    )
                    time.sleep(2 * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp
            except httpx.HTTPError as exc:
                last_exc = exc
                time.sleep(2 * (attempt + 1))
        assert last_exc is not None
        raise last_exc


# --------------------------------------------------------------------------- #
# Vietnamese date parsing
# --------------------------------------------------------------------------- #

_VN_MONTH_HEADER_RE = re.compile(r"Th[aá]ng\s*(\d{1,2})\D+(\d{4})", re.IGNORECASE)


def parse_vn_month_header(text: str) -> tuple[int, int] | None:
    """Parse a header like 'Tháng 11 2026' -> (11, 2026)."""
    m = _VN_MONTH_HEADER_RE.search(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def parse_dd_mm(text: str, year: int) -> date | None:
    """Parse 'dd/MM' (e.g. '08/11') given an external year."""
    m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})", text)
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_dd_mm_yyyy(text: str) -> date | None:
    """Parse 'dd/MM/yyyy' (e.g. '15/11/2026')."""
    m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", text)
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(year, month, day)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# VN price parsing
# --------------------------------------------------------------------------- #

def parse_vnd_price(text: str) -> int | None:
    """Parse a Vietnamese-formatted price like '450.000đ' or 'Từ 450.000đ' -> 450000.
    Returns None if no digits are found (e.g. 'Đóng đăng ký').
    """
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    return int(digits)


# --------------------------------------------------------------------------- #
# Stable id / slugging
# --------------------------------------------------------------------------- #

_STRIP_WORDS = [
    "giai chay",
    "giải chạy",
    "powered by",
    "cup",
    "cúp",
]
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def slugify(text: str) -> str:
    text = unidecode(text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text


def normalize_name_for_id(name: str) -> str:
    """Strip year/sponsor-ish boilerplate words before slugging, so the same race
    listed slightly differently across sources still slugs to the same thing.
    """
    lowered = unidecode(name).lower()
    lowered = _YEAR_RE.sub("", lowered)
    for word in _STRIP_WORDS:
        lowered = lowered.replace(unidecode(word).lower(), "")
    return slugify(lowered)


def make_id(name: str, start_date: str) -> str:
    return f"{normalize_name_for_id(name)}-{start_date}"


def label_to_km(label: str) -> float | None:
    """Turn a distance label like '42km' or '21KM' into a km float, using the
    conventional official race distances for marathon (42.195) and half (21.0975).
    """
    m = re.search(r"(\d+(?:[.,]\d+)?)", label)
    if not m:
        return None
    val = float(m.group(1).replace(",", "."))
    if val == 42:
        return 42.195
    if val == 21:
        return 21.0975
    return val


def guess_terrain(name: str, explicit: str | None = None) -> str:
    """Infer terrain from an explicit label (VnExpress gives one) or from
    keywords in the race name as a fallback (used by VBM).
    """
    if explicit:
        label = explicit.strip().lower()
        if "city" in label:
            return "city_trail"
        if "trail" in label:
            return "trail"
        if "road" in label:
            return "road"

    lowered = unidecode(name).lower()
    if "ironman" in lowered or "triathlon" in lowered or "3 mon phoi hop" in lowered:
        return "triathlon"
    if "ultra" in lowered:
        return "ultra"
    if "city trail" in lowered:
        return "city_trail"
    if "trail" in lowered:
        return "trail"
    if "virtual" in lowered or "ao" in lowered and "chay ao" in lowered:
        return "virtual"
    return "road"
