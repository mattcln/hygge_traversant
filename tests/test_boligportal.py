"""Tests du parser BoligPortal, sur de vraies pages sauvegardées le 14/10/2026.

Sauvegarder des pages depuis le VPS :
    hygge save-page "<url de recherche>" data/search.html
    hygge save-page "<url d'annonce>"    data/listing_xxx.html
puis les copier dans tests/fixtures/boligportal/.

- search.html               : København, 55 m² min, 14 000 kr max
- listing_furnished_da.html : København S, meublée, en danois, 12 mois
- listing_furnished_en.html : Rødovre, meublée, en anglais
- listing_limited.html      : København S, meublée, 1er étage, 12 mois
- listing_unfurnished.html  : Taastrup, non meublée, durée illimitée
"""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from hygge_traversant.analysis.keywords import extract_facts
from hygge_traversant.models import Listing
from hygge_traversant.sources.boligportal import (
    ParserError,
    find_embedded_json,
    parse_listing_page,
    parse_search_page,
)

FIXTURES = Path(__file__).parent / "fixtures" / "boligportal"


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def stub(source_id: str) -> Listing:
    """L'annonce telle que trouvée dans la page de résultats."""
    return next(l for l in parse_search_page(read("search.html")) if l.source_id == source_id)


def test_find_embedded_json():
    html = ('<html><script id="__NEXT_DATA__" type="application/json">'
            '{"props": {"ads": [{"id": 1}]}}</script></html>')
    assert find_embedded_json(html) == [{"props": {"ads": [{"id": 1}]}}]


# --- Page de résultats ---------------------------------------------------------------


def test_parse_search_page():
    listings = parse_search_page(read("search.html"))
    assert len(listings) == 18
    assert all(l.source == "boligportal" and l.source_id for l in listings)
    assert all(l.url.startswith("https://www.boligportal.dk/en/rental-apartments/") for l in listings)
    assert len({l.source_id for l in listings}) == 18


def test_search_page_newest_first():
    published = [l.published_at for l in parse_search_page(read("search.html"))]
    assert all(published)
    assert published == sorted(published, reverse=True)


def test_search_page_ignores_similar_ads():
    """Les annonces « similaires » (Birkerød, Hørsholm) ne font pas partie de la recherche."""
    areas = {l.area for l in parse_search_page(read("search.html"))}
    assert not areas & {"Birkerød", "Hørsholm"}


def test_search_page_fields():
    l = stub("5677881")
    assert l.url == "https://www.boligportal.dk/en/rental-apartments/k%C3%B8benhavn/68m2-2-room-id-5677881"
    assert l.area == "København S"
    assert l.postal_code == 2300
    assert l.rent == 13000
    assert l.utilities == 1100
    assert l.size_m2 == 68
    assert l.rooms == 2
    assert l.floor == 2
    assert l.furnished is True
    assert l.available_from == date(2026, 12, 1)
    assert l.rental_period == "12 months"
    assert l.published_at == datetime(2026, 10, 13, 14, 48, 4, 566625, tzinfo=timezone.utc)
    assert l.description == ""  # seulement sur la page détail


def test_parse_search_page_without_store():
    with pytest.raises(ParserError):
        parse_search_page("<html><body>Access denied</body></html>")


# --- Pages d'annonce -----------------------------------------------------------------


def test_listing_furnished_da():
    l = parse_listing_page(read("listing_furnished_da.html"), stub("5677881"))
    assert l.source_id == "5677881"
    assert l.title.startswith("Lys 68 m² lejlighed til leje på Amager")
    assert "Boligen er møbleret" in l.description
    assert l.address == "Sundholmsvej 109"
    assert (l.area, l.postal_code) == ("København S", 2300)
    assert (l.rent, l.utilities, l.deposit) == (13000, 1100, 26000)
    assert (l.size_m2, l.rooms, l.floor) == (68, 2, 2)
    assert l.furnished is True
    assert l.available_from == date(2026, 12, 1)
    assert l.rental_period == "12 months"
    assert l.raw["features"]["balcony"] is True

    facts = extract_facts(l)
    assert facts.language == "da"
    assert facts.time_limited


def test_listing_furnished_en():
    l = parse_listing_page(read("listing_furnished_en.html"), stub("5377731"))
    assert l.title == "70 m2 fully furnished 2-rooms apartment in Rødovre"
    assert "Max 2 CPR can be registered" in l.description
    assert (l.area, l.postal_code) == ("Rødovre", 2610)
    assert (l.rent, l.utilities) == (10000, 900)
    assert l.furnished is True
    assert extract_facts(l).language == "en"


def test_listing_limited():
    l = parse_listing_page(read("listing_limited.html"), stub("5679467"))
    assert "Lejeperiode: 1 år" in l.description
    assert (l.rent, l.utilities, l.floor) == (9000, 1000, 1)
    assert l.rental_period == "12 months"


def test_listing_unfurnished():
    l = parse_listing_page(read("listing_unfurnished.html"), stub("5679846"))
    assert (l.area, l.postal_code) == ("Taastrup", 2630)
    assert l.furnished is False
    assert l.available_from == date(2027, 3, 1)
    assert l.rental_period == "Unlimited"
    assert not extract_facts(l).time_limited


def test_listing_page_keeps_stub_values_when_missing():
    l = stub("5677881")
    html = ('<script id="store" type="application/json">{"props": {"page_props": {"ad": '
            '{"id": 5677881, "url": "/x-id-5677881", "description": "Ny tekst", '
            '"monthly_rent": null, "features": {}}}}}</script>')
    merged = parse_listing_page(html, l)
    assert merged.description == "Ny tekst"
    assert merged.rent == 13000
    assert merged.furnished is True
    assert merged.area == "København S"


def test_listing_page_without_ad():
    html = '<script id="store" type="application/json">{"props": {"page_props": {}}}</script>'
    with pytest.raises(ParserError):
        parse_listing_page(html, stub("5677881"))
