"""Filtres simples sur les champs chiffrés : zone, prix total, surface, pièces."""

from __future__ import annotations

from ..config import Config, Zone
from ..models import Facts, Listing


def classify_zone(listing: Listing, zones: list[Zone]) -> Zone | None:
    """Code postal d'abord (fiable), puis mots-clés dans le quartier, l'adresse, le titre."""
    for z in zones:
        if z.matches_postal(listing.postal_code):
            return z
    haystack = " ".join(filter(None, [listing.area, listing.address, listing.title]))
    # Les zones exclues sont testées en premier (cf. parse_zones) : "frederiksberg c"
    # doit gagner sur "frederiksberg".
    for z in zones:
        if z.matches_text(haystack):
            return z
    return None


def estimate_total(listing: Listing, facts: Facts, cfg: Config) -> tuple[int | None, bool]:
    """Total mensuel (loyer + charges). Renvoie (total, est_une_estimation)."""
    if listing.rent is None:
        return None, True
    if facts.utilities_included:
        return listing.rent, False
    if listing.utilities is not None:
        return listing.rent + listing.utilities, False
    return listing.rent + int(cfg.budget["utilities_estimate"]), True
