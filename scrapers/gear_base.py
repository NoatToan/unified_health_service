"""Shared building blocks for the runner-gear scrapers: the GearItem/GearVariant
models and a stable-id helper.

This is a METADATA + LINK-OUT catalog, never a store and never a full
reproduction of a product page: every item always keeps `productUrl` as the
only way to actually buy it, `description` is a short factual restatement in
this project's own words (never copy-pasted marketing copy), and nothing here
ever touches a cart/checkout/payment endpoint or collects user data.

See docs_research/GEAR_SOURCES_RESEARCH.md for the source research and the
rationale behind every field, especially `variants` (per-color data, only
ever populated when a source genuinely exposes it - never fabricated).
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field
from unidecode import unidecode

VALID_CATEGORIES = {"shoes", "apparel", "accessories"}


class GearVariant(BaseModel):
    color: str
    imageUrl: str | None = None
    productUrl: str


class GearItem(BaseModel):
    id: str
    name: str
    brand: str
    category: str
    sourceName: str
    priceVnd: int | None = None
    description: str | None = None
    imageUrl: str | None = None
    productUrl: str
    variants: list[GearVariant] = Field(default_factory=list)
    crawledAt: str


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
