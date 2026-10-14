from datetime import date, datetime, timezone

import pytest

from hygge_traversant.analysis import analyze
from hygge_traversant.analysis.keywords import (
    detect_language, extract_available_from, extract_facts, extract_floor, normalize,
)
from hygge_traversant.models import Listing

TODAY = date(2026, 10, 13)


def make(**kw) -> Listing:
    base = dict(source="t", source_id="1", url="https://example.org/1", area="Vanløse",
                postal_code=2720, rent=12500, size_m2=60, rooms=2,
                published_at=datetime(2026, 10, 13, tzinfo=timezone.utc))
    base.update(kw)
    return Listing(**base)


# --- Mots-clés ---------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "Dejlig gennemlyst lejlighed", "lys fra begge sider", "vinduer mod begge sider",
    "Bright apartment with windows on both sides", "dual-aspect flat",
])
def test_traversant_detected(text):
    assert extract_facts(make(description=text), TODAY).traversant


def test_traversant_not_invented():
    assert not extract_facts(make(description="Lys lejlighed med altan mod gården"), TODAY).traversant


@pytest.mark.parametrize("text,expected", [
    ("Lejligheden udlejes møbleret", True),
    ("Fully furnished apartment", True),
    ("Lejligheden er umøbleret", False),
    ("Unfurnished 2-room flat", False),
    ("Stor stue og køkken", None),
])
def test_furnished(text, expected):
    assert extract_facts(make(description=text), TODAY).furnished is expected


def test_structured_field_wins_over_text():
    facts = extract_facts(make(description="møbleret", furnished=False), TODAY)
    assert facts.furnished is False


@pytest.mark.parametrize("text,expected", [
    ("Husleje inkl. forbrug", True),
    ("Rent including utilities", True),
    ("Husleje + forbrug (aconto 900 kr)", False),
    ("Nice flat", None),
])
def test_utilities(text, expected):
    assert extract_facts(make(description=text), TODAY).utilities_included is expected


@pytest.mark.parametrize("text,expected", [
    ("Det er ikke muligt at blive tilmeldt folkeregisteret", False),
    ("Not possible to register for CPR at the address", False),
    ("Mulighed for at blive tilmeldt folkeregisteret", True),
    ("CPR registration is possible", True),
    ("Hyggelig lejlighed", None),
])
def test_domicile(text, expected):
    assert extract_facts(make(description=text), TODAY).domicile_allowed is expected


@pytest.mark.parametrize("text,expected", [
    ("lejligheden ligger på 3. sal", 3),
    ("stueetage med have", 0),
    ("apartment on the 4th floor", 4),
    ("stor stue og køkken", None),   # "stue" = séjour, pas rez-de-chaussée
])
def test_floor(text, expected):
    assert extract_floor(normalize(text)) == expected


@pytest.mark.parametrize("text,expected", [
    ("ledig fra 1. februar 2027", date(2027, 2, 1)),
    ("ledig fra 1. februar", date(2027, 2, 1)),
    ("available from February 1st", date(2027, 2, 1)),
    ("indflytning 01.03.2027", date(2027, 3, 1)),
    ("move-in 2027-02-15", date(2027, 2, 15)),
    ("ledig straks", TODAY),
    ("tæt på metroen", None),
])
def test_available_from(text, expected):
    assert extract_available_from(normalize(text), TODAY) == expected


def test_language():
    assert detect_language("dejlig lejlighed med altan og stort køkken, ledig fra februar") == "da"
    assert detect_language("lovely apartment with a balcony and a large kitchen, available") == "en"


def test_scam_flags():
    facts = extract_facts(make(description="I am currently abroad, payment via Western Union"), TODAY)
    assert len(facts.scam_flags) == 2


# --- Verdicts ----------------------------------------------------------------------------


GOOD = ("Møbleret og gennemlyst lejlighed på 3. sal. Husleje inkl. forbrug. "
        "Ledig fra 1. februar 2027.")


def test_green(cfg):
    a = analyze(make(description=GOOD), cfg, today=TODAY)
    assert a.verdict == "green", a.reasons
    assert "☀️ Traversant" in a.bonuses
    assert a.total_estimate == 12500 and not a.total_is_estimate


def test_red_excluded_zone(cfg):
    a = analyze(make(description=GOOD, area="Østerbro", postal_code=2100), cfg, today=TODAY)
    assert a.verdict == "red"
    assert any("zone exclue" in r for r in a.reasons)


def test_red_too_expensive_with_estimated_utilities(cfg):
    # 13 200 + 1 500 de charges estimées = 14 700 > 14 500
    a = analyze(make(description="møbleret, 3. sal, ledig fra 1. februar 2027", rent=13200), cfg, today=TODAY)
    assert a.verdict == "red"
    assert a.total_is_estimate


def test_orange_above_target(cfg):
    a = analyze(make(description=GOOD, rent=14200), cfg, today=TODAY)
    assert a.verdict == "orange"


def test_orange_unknown_furnished_and_low_floor(cfg):
    a = analyze(make(description="Inkl. forbrug. 1. sal. Ledig fra 1. februar 2027"), cfg, today=TODAY)
    assert a.verdict == "orange"
    assert "meublé non précisé" in a.reasons
    assert any("1er étage" in r for r in a.reasons)


def test_red_unfurnished(cfg):
    a = analyze(make(description="Umøbleret lejlighed, inkl. forbrug"), cfg, today=TODAY)
    assert a.verdict == "red"


def test_red_no_domicile(cfg):
    a = analyze(make(description=GOOD + " Det er ikke muligt at blive tilmeldt folkeregisteret."),
                cfg, today=TODAY)
    assert a.verdict == "red"


def test_red_too_late(cfg):
    a = analyze(make(description="Møbleret, inkl. forbrug, 3. sal. Ledig fra 1. maj 2027"), cfg, today=TODAY)
    assert a.verdict == "red"


def test_size_limits(cfg):
    assert analyze(make(description=GOOD, size_m2=52), cfg, today=TODAY).verdict == "orange"
    assert analyze(make(description=GOOD, size_m2=45), cfg, today=TODAY).verdict == "red"


def test_frederiksberg_c_beats_frederiksberg(cfg):
    a = analyze(make(description=GOOD, area="Frederiksberg C", postal_code=None), cfg, today=TODAY)
    assert a.zone_tier == "excluded"


def test_suspiciously_cheap(cfg):
    a = analyze(make(description=GOOD, rent=6000), cfg, today=TODAY)
    assert a.verdict == "orange"
    assert any("arnaque" in r for r in a.reasons)


# --- Ajouts après le premier passage sur de vraies annonces ---------------------------


@pytest.mark.parametrize("text", [
    "Gennemgående 3-værelses i stueplan med terrasse", "Lys og gennemgående lejlighed",
])
def test_traversant_gennemgaaende(text):
    assert extract_facts(make(description=text), TODAY).traversant


def test_gennemgaaende_other_meaning_not_traversant():
    text = "Materialevalget er gennemgående – pænt at se på"
    assert not extract_facts(make(description=text), TODAY).traversant


@pytest.mark.parametrize("text", ["Max 2 CPR can be registered.", "CPR can be registered at the address"])
def test_domicile_cpr_registered(text):
    assert extract_facts(make(description=text), TODAY).domicile_allowed is True


def test_move_in_disabled(cfg):
    cfg.raw["move_in"]["enabled"] = False
    for d in ("2026-11-01", "2027-06-01"):
        a = analyze(make(available_from=date.fromisoformat(d), furnished=True, floor=3), cfg, today=TODAY)
        assert not any("entrée" in r for r in a.reasons)
        assert "date d'entrée" not in a.checks
