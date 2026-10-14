"""Source BoligPortal.

Le téléchargement des pages est en place. Le parsing (parse_search_page,
parse_listing_page) reste à écrire à partir de vraies pages sauvegardées dans
tests/fixtures/boligportal/ (commande : hygge save-page <url> <fichier>).

Piste probable : BoligPortal est une application web moderne, les données de
la page sont souvent dans un bloc JSON embarqué (script __NEXT_DATA__ ou
équivalent). find_embedded_json() aide à le repérer.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from ..models import Listing
from .base import Source, make_client

BASE_URL = "https://www.boligportal.dk"


class ParserNotReady(NotImplementedError):
    pass


# --- Aides au parsing --------------------------------------------------------------


def find_embedded_json(html: str) -> list[Any]:
    """Tous les blocs JSON embarqués dans la page (script type JSON ou __NEXT_DATA__)."""
    soup = BeautifulSoup(html, "html.parser")
    blobs: list[Any] = []
    for script in soup.find_all("script"):
        content = script.string or ""
        if script.get("type") in ("application/json", "application/ld+json") or script.get("id") == "__NEXT_DATA__":
            try:
                blobs.append(json.loads(content))
            except json.JSONDecodeError:
                pass
            continue
        m = re.search(r"window\.__[A-Z_]+__\s*=\s*(\{.*\})\s*;?\s*$", content, re.S)
        if m:
            try:
                blobs.append(json.loads(m.group(1)))
            except json.JSONDecodeError:
                pass
    return blobs


def walk(obj: Any):
    """Parcourt récursivement un JSON (pour chercher les objets qui ressemblent à des annonces)."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def parse_search_page(html: str) -> list[Listing]:
    raise ParserNotReady(
        "Parser BoligPortal pas encore écrit : sauvegarder une page de résultats "
        "avec `hygge save-page` et l'ajouter aux fixtures."
    )


def parse_listing_page(html: str, listing: Listing) -> Listing:
    raise ParserNotReady(
        "Parser de page détail BoligPortal pas encore écrit : sauvegarder une page "
        "d'annonce avec `hygge save-page` et l'ajouter aux fixtures."
    )


# --- Source --------------------------------------------------------------------------


class BoligPortalSource(Source):
    name = "boligportal"

    def __init__(self, search_urls: list[str], detail_delay: tuple[float, float] = (1.5, 4.0),
                 client: httpx.Client | None = None):
        self.search_urls = search_urls
        self.detail_delay = detail_delay
        self.client = client or make_client()

    def fetch(self, url: str) -> str:
        r = self.client.get(url)
        r.raise_for_status()
        return r.text

    def search(self) -> list[Listing]:
        seen: dict[str, Listing] = {}
        for url in self.search_urls:
            for listing in parse_search_page(self.fetch(url)):
                seen.setdefault(listing.source_id, listing)
        return list(seen.values())

    def enrich(self, listing: Listing) -> Listing:
        self.polite_pause(self.detail_delay)
        return parse_listing_page(self.fetch(listing.url), listing)
