"""Analyse par mots-clés (danois et anglais) du texte d'une annonce.

Les champs structurés fournis par la source ont priorité sur le texte.
Tout est volontairement prudent : en cas de doute, on renvoie None
et l'annonce passe en "à vérifier" plutôt que d'être rejetée.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from ..models import Facts, Listing


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    return re.sub(r"\s+", " ", text)


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


# --- Meublé -------------------------------------------------------------------

UNFURNISHED = [
    r"\bumøbler", r"\bikke møbleret", r"\bunfurnished\b", r"\bnot furnished\b",
    r"\bwithout furniture\b", r"\buden møbler\b",
]
FURNISHED = [
    r"\bmøbleret\b", r"\bfuldt møbleret\b", r"\bdelvist møbleret\b", r"\bmøbleres\b",
    r"\bfurnished\b", r"\bfully furnished\b", r"\bmed møbler\b",
]

# --- Charges -------------------------------------------------------------------

UTILITIES_INCLUDED = [
    r"inkl\.? (?:alt )?forbrug", r"inklusiv(?:e)? (?:alt )?forbrug", r"forbrug (?:er )?inkluderet",
    r"utilities (?:are )?included", r"including (?:all )?utilities", r"bills (?:are )?included",
    r"all inclusive", r"incl\.? (?:all )?utilities",
]
UTILITIES_EXCLUDED = [
    r"ekskl\.? forbrug", r"eksklusiv(?:e)? forbrug", r"\+ ?forbrug", r"plus forbrug",
    r"utilities (?:are )?not included", r"excluding utilities", r"\+ ?utilities",
    r"excl\.? utilities", r"aconto",
]

# --- Bail ------------------------------------------------------------------------

SUBLET = [r"\bfremlej", r"\bsublet", r"\bsub-let", r"\bsublease", r"\bsub-lease"]
TIME_LIMITED = [
    r"tidsbegræns", r"\bbegrænset periode\b", r"limited (?:period|time)", r"fixed[- ]term",
    r"temporary rental",
    r"(?:lejeperiode|rental period|lease|period|for|i|en periode på) (?:of |på |er )?\d{1,2} (?:måneder|months)",
]

# --- Domiciliation (CPR) -----------------------------------------------------------

DOMICILE_NO = [
    r"ikke (?:muligt at )?(?:blive )?(?:til|ind)meld", r"kan ikke (?:blive )?(?:til|ind)meld",
    r"ingen (?:folkeregister|cpr)", r"uden (?:folkeregister|cpr)",
    r"not possible to (?:get a |register|have).{0,20}(?:cpr|address)",
    r"(?:cannot|can't|can not) (?:be )?regist", r"no (?:cpr|address registration)",
    r"without (?:cpr|registration)",
]
DOMICILE_YES = [
    r"mulighed for (?:at blive )?(?:tilmeld|folkeregister|cpr)", r"kan (?:blive )?tilmeld",
    r"folkeregisteradresse (?:er )?mulig", r"cpr[- ]?(?:registrering|adresse) (?:er )?mulig",
    r"possible to register", r"(?:cpr|address) registration (?:is )?(?:possible|allowed)",
    r"you can register", r"can (?:get|have) (?:a )?cpr",
]

# --- Bonus ---------------------------------------------------------------------------

TRAVERSANT = [
    r"gennemlys", r"lys fra (?:to|begge) sider", r"vinduer (?:til|mod|i|på) begge sider",
    r"lys ind fra (?:to|begge) sider", r"dobbelt ?orienter",
    r"light from (?:two|both) sides", r"windows (?:on|to|facing) (?:two|both) sides",
    r"dual[- ]aspect", r"bright from (?:two|both) sides", r"double[- ]aspect",
]
OPEN_KITCHEN = [
    r"åbent køkken", r"køkken-?alrum", r"køkken i (?:direkte )?forbindelse med stue",
    r"køkken og stue i (?:et|ét)", r"open (?:plan )?kitchen", r"open[- ]plan",
    r"kitchen (?:open to|connected to) the living",
]
BALCONY = [r"\baltan", r"\bfransk altan\b", r"\bbalcon", r"\bterrasse\b", r"\bterrace\b"]

# --- Arnaques ---------------------------------------------------------------------

SCAM = {
    "paiement Western Union ou MoneyGram": [r"western union", r"moneygram"],
    "propriétaire à l'étranger": [
        r"(?:i am|i'm|we are|we're) (?:currently )?(?:living |working )?(?:abroad|out of the country|in (?:the )?(?:uk|usa|us|england|spain))",
        r"jeg (?:er|bor) (?:i )?(?:udlandet|i england|i spanien)",
    ],
    "clés envoyées par courrier": [r"keys? (?:will be )?(?:sent|send) (?:by|via) (?:mail|post|dhl)", r"nøgler.{0,20}(?:sendes|med posten)"],
    "paiement avant visite": [r"(?:deposit|payment).{0,40}before (?:the )?(?:viewing|visit|seeing)", r"betal.{0,40}før (?:fremvisning|du ser)"],
    "intermédiaire type Airbnb pour le paiement": [r"airbnb.{0,30}(?:payment|deposit|hold|handle)"],
}

# --- Étage --------------------------------------------------------------------------

FLOOR_PATTERNS = [
    (r"\bstueetage\b|\bground floor\b|\bst\.? ?(?:tv|th|mf)\b", 0),
    (r"\bkælder|\bbasement\b|\bsouterrain", -1),
]
FLOOR_NUM = [
    r"\b(\d{1,2})\.? ?sal\b", r"\b(\d{1,2})(?:st|nd|rd|th) floor\b", r"\bfloor (\d{1,2})\b",
    r"\b(\d{1,2})\. (?:tv|th|mf)\b",
]


def extract_floor(text: str) -> int | None:
    for pat, val in FLOOR_PATTERNS:
        if re.search(pat, text):
            return val
    for pat in FLOOR_NUM:
        m = re.search(pat, text)
        if m:
            return int(m.group(1))
    return None


# --- Date d'entrée ------------------------------------------------------------------

MONTHS = {
    "januar": 1, "january": 1, "jan": 1,
    "februar": 2, "february": 2, "feb": 2,
    "marts": 3, "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "maj": 5, "may": 5,
    "juni": 6, "june": 6, "jun": 6,
    "juli": 7, "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "october": 10, "okt": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
MOVE_IN_CONTEXT = (
    r"(?:ledig|overtagelse|indflytning|tiltrædelse|lejestart|fra den|fra d\.|"
    r"available|move[- ]in|moving in|from the|starting|start date|from)"
)
NOW_PATTERNS = [r"ledig (?:nu|straks|hurtigst)", r"available (?:now|immediately|asap)", r"straks"]


def _infer_year(month: int, day: int, ref: date) -> date:
    candidate = date(ref.year, month, day)
    if (ref - candidate).days > 60:
        candidate = date(ref.year + 1, month, day)
    return candidate


def extract_available_from(text: str, ref: date) -> date | None:
    for m in re.finditer(MOVE_IN_CONTEXT, text):
        window = text[m.end(): m.end() + 40]
        # 1. februar 2027 / 1 february / 1st of february
        d = re.search(rf"(\d{{1,2}})(?:\.|st|nd|rd|th)?(?: of)? ({_MONTH_RE})\.?(?: (\d{{4}}))?", window)
        if d:
            day, month = int(d.group(1)), MONTHS[d.group(2)]
            try:
                return date(int(d.group(3)), month, day) if d.group(3) else _infer_year(month, day, ref)
            except ValueError:
                continue
        # february 1st, 2027
        d = re.search(rf"({_MONTH_RE}) (\d{{1,2}})(?:st|nd|rd|th)?,?(?: (\d{{4}}))?", window)
        if d:
            month, day = MONTHS[d.group(1)], int(d.group(2))
            try:
                return date(int(d.group(3)), month, day) if d.group(3) else _infer_year(month, day, ref)
            except ValueError:
                continue
        # 01.02.2027, 1/2-2027, 2027-02-01
        d = re.search(r"(\d{4})-(\d{2})-(\d{2})", window)
        if d:
            try:
                return date(int(d.group(1)), int(d.group(2)), int(d.group(3)))
            except ValueError:
                continue
        d = re.search(r"(\d{1,2})[./](\d{1,2})[./-](\d{2,4})", window)
        if d:
            y = int(d.group(3))
            y = y + 2000 if y < 100 else y
            try:
                return date(y, int(d.group(2)), int(d.group(1)))
            except ValueError:
                continue
    if _any(NOW_PATTERNS, text):
        return ref
    return None


# --- Langue ----------------------------------------------------------------------------

DA_WORDS = {"og", "er", "til", "med", "lejlighed", "på", "det", "der", "af", "ikke", "værelse",
            "værelser", "stue", "køkken", "bad", "ledig", "husleje", "fra", "vi", "jeg", "kan"}
EN_WORDS = {"the", "and", "is", "to", "with", "apartment", "flat", "of", "not", "room", "rooms",
            "living", "kitchen", "bathroom", "available", "rent", "from", "we", "i", "can"}


def detect_language(text: str) -> str:
    words = re.findall(r"[a-zæøå]+", text)
    da = sum(w in DA_WORDS for w in words)
    en = sum(w in EN_WORDS for w in words)
    return "da" if da > en else "en"


# --- Point d'entrée ----------------------------------------------------------------------


def extract_facts(listing: Listing, today: date | None = None) -> Facts:
    text = normalize(listing.text)
    ref = (listing.published_at.date() if listing.published_at else None) or today or date.today()

    furnished = listing.furnished
    if furnished is None:
        if _any(UNFURNISHED, text):
            furnished = False
        elif _any(FURNISHED, text):
            furnished = True

    utilities_included = listing.utilities_included
    if utilities_included is None:
        if _any(UTILITIES_INCLUDED, text):
            utilities_included = True
        elif _any(UTILITIES_EXCLUDED, text):
            utilities_included = False

    domicile = None
    if _any(DOMICILE_NO, text):
        domicile = False
    elif _any(DOMICILE_YES, text):
        domicile = True

    scam_flags = [label for label, pats in SCAM.items() if _any(pats, text)]

    return Facts(
        furnished=furnished,
        utilities_included=utilities_included,
        sublet=_any(SUBLET, text),
        time_limited=_any(TIME_LIMITED, text) or bool(
            listing.rental_period and not re.search(r"unlimited|ubegrænset", listing.rental_period.lower())
        ),
        domicile_allowed=domicile,
        traversant=_any(TRAVERSANT, text),
        open_kitchen=_any(OPEN_KITCHEN, text),
        balcony=_any(BALCONY, text),
        floor=listing.floor if listing.floor is not None else extract_floor(text),
        available_from=listing.available_from or extract_available_from(text, ref),
        scam_flags=scam_flags,
        language=detect_language(text),
    )
