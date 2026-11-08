from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, text: str):
        self.text = text


class FakeClient:
    """Stands in for PoliteClient in tests: maps URLs to canned HTML so
    scrapers can be exercised end-to-end without hitting the network.
    """

    def __init__(self, pages: dict[str, str], default: str = ""):
        self._pages = pages
        self._default = default

    def get(self, url: str) -> FakeResponse:
        return FakeResponse(self._pages.get(url, self._default))


def read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")
