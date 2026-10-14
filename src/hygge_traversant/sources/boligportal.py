"""Source BoligPortal.

Les pages (résultats comme annonce) sont rendues côté serveur et embarquent
toutes leurs données dans un bloc <script id="store" type="application/json"> :
pas besoin de JavaScript.

- page de résultats : store.props.page_props.results (triés par date de
  publication, les plus récentes d'abord). Les similar_ads (autres villes)
  sont ignorées ;
- page d'annonce : store.props.page_props.ad, mêmes champs que dans les
  résultats, plus la description complète.

Pages de référence dans tests/fixtures/boligportal/ (hygge save-page <url> <fichier>).
"""

from __future__ import annotations

import json
import re
from dataclasses import fields
from datetime import date, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from ..models import Listing
from .base import Source, make_client

BASE_URL = "https://www.boligportal.dk"


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


class ParserError(ValueError):
    """La page ne contient pas les données attendues (site modifié, page d'erreur...)."""


def page_props(html: str) -> dict[str, Any]:
    """Le JSON embarqué de la page (store.props.page_props)."""
    script = BeautifulSoup(html, "html.parser").find("script", id="store")
    if script is None or not script.string:
        raise ParserError("bloc <script id=\"store\"> absent de la page")
    try:
        return json.loads(script.string)["props"]["page_props"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ParserError(f"bloc store illisible : {e}") from e


def _int(v: Any) -> int | None:
    return None if v is None else int(round(float(v)))


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(v) if v else None
    except (TypeError, ValueError):
        return None


def _datetime(v: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(v) if v else None
    except (TypeError, ValueError):
        return None


def _rental_period(months: Any) -> str | None:
    """BoligPortal donne la durée en mois, 0 pour illimitée."""
    if months is None:
        return None
    return "Unlimited" if int(months) == 0 else f"{int(months)} months"


# Champs de l'annonce gardés dans Listing.raw (non stockés en base, utiles au débogage).
RAW_KEYS = ("state", "rental_period", "features", "other_details", "created",
            "advertised_date", "location", "energy_rating", "is_owner", "social_housing")


def listing_from_ad(ad: dict[str, Any]) -> Listing:
    features = ad.get("features") or {}
    street = " ".join(filter(None, [ad.get("street_name"), ad.get("street_number")]))
    utilities = _int(ad.get("monthly_rent_extra_costs"))
    return Listing(
        source="boligportal",
        source_id=str(ad["id"]),
        url=BASE_URL + ad["url"],
        title=ad.get("title") or "",
        description=ad.get("description") or "",
        area=ad.get("city_area") or ad.get("city"),
        postal_code=_int(ad.get("postal_code")),
        address=street or None,
        rent=_int(ad.get("monthly_rent")),
        # 0 = non renseigné le plus souvent : on laisse l'analyse estimer les charges
        utilities=utilities or None,
        deposit=_int(ad.get("deposit")),
        size_m2=ad.get("size_m2"),
        rooms=_int(ad.get("rooms")),
        floor=_int(ad.get("floor")),
        furnished=features.get("furnished"),
        available_from=_date(ad.get("available_from")),
        rental_period=_rental_period(ad.get("rental_period")),
        published_at=_datetime(ad.get("advertised_date")),
        raw={k: ad.get(k) for k in RAW_KEYS},
    )


def parse_search_page(html: str) -> list[Listing]:
    props = page_props(html)
    if "results" not in props:
        raise ParserError("pas de liste de résultats dans la page")
    return [listing_from_ad(ad) for ad in props["results"] if not ad.get("deleted")]


def parse_listing_page(html: str, listing: Listing) -> Listing:
    """Complète l'annonce de la page de résultats avec sa page détail.
    Les valeurs de la page détail priment, sauf quand elles sont vides."""
    ad = page_props(html).get("ad")
    if not ad:
        raise ParserError("pas d'annonce dans la page")
    detail = listing_from_ad(ad)
    for f in fields(Listing):
        value = getattr(detail, f.name)
        if value is None or value == "" or value == {}:
            setattr(detail, f.name, getattr(listing, f.name))
    return detail


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
