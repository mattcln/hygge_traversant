"""Tests du parser BoligPortal : à compléter avec de vraies pages.

Sauvegarder des pages depuis le VPS :
    hygge save-page "<url de recherche>" tests/fixtures/boligportal/search.html
    hygge save-page "<url d'annonce>"    tests/fixtures/boligportal/listing_1.html
"""

from pathlib import Path

import pytest

from hygge_traversant.sources.boligportal import find_embedded_json, parse_search_page

FIXTURES = Path(__file__).parent / "fixtures" / "boligportal"


def test_find_embedded_json():
    html = ('<html><script id="__NEXT_DATA__" type="application/json">'
            '{"props": {"ads": [{"id": 1}]}}</script></html>')
    assert find_embedded_json(html) == [{"props": {"ads": [{"id": 1}]}}]


@pytest.mark.skipif(not (FIXTURES / "search.html").exists(), reason="fixture de recherche absente")
def test_parse_search_page():
    listings = parse_search_page((FIXTURES / "search.html").read_text(encoding="utf-8"))
    assert listings, "aucune annonce trouvée dans la page de recherche"
    assert all(l.source_id and l.url.startswith("https://") for l in listings)
