"""Verdict vert / orange / rouge, avec les raisons et les bonus.

Rouge   : bloquant certain (trop cher, trop petit, non meublé, zone exclue,
          domiciliation impossible, entrée trop tardive). Pas de notification.
Orange  : à regarder, un doute ou un critère limite. Canal silencieux.
Vert    : tout est dans les critères connus. Canal prioritaire.
"""

from __future__ import annotations

from datetime import date

from ..config import Config
from ..models import Analysis, Facts, Listing
from . import keywords
from .hard_filters import classify_zone, estimate_total


def fmt_dkk(n: int | float | None) -> str:
    return "?" if n is None else f"{int(n):,}".replace(",", " ")


def fmt_date(d: date | None) -> str:
    months = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août",
              "sept.", "oct.", "nov.", "déc."]
    return "?" if d is None else f"{d.day} {months[d.month - 1]} {d.year}"


def analyze(listing: Listing, cfg: Config, facts: Facts | None = None,
            today: date | None = None) -> Analysis:
    facts = facts or keywords.extract_facts(listing, today=today)
    red: list[str] = []
    orange: list[str] = []
    checks: list[str] = []
    bonuses: list[str] = []

    # --- Zone ---------------------------------------------------------------
    zone = classify_zone(listing, cfg.zones)
    tier = zone.tier if zone else "unknown"
    if tier == "excluded":
        red.append(f"zone exclue ({zone.name})")
    elif tier == "open":
        orange.append(f"zone hors liste mais point ouvert ({zone.name})")
    elif tier == "unknown":
        orange.append("zone non reconnue")
    if tier in ("secondary", "open", "unknown"):
        checks.append("trajet jusqu'à Christiansborg")

    # --- Prix -----------------------------------------------------------------
    b = cfg.budget
    total, is_estimate = estimate_total(listing, facts, cfg)
    if total is None:
        orange.append("loyer non trouvé")
    else:
        if total > b["absolute_max_total"]:
            red.append(f"trop cher (~{fmt_dkk(total)} DKK/mois)")
        elif total > b["target_max_total"]:
            orange.append(f"au-dessus de la cible (~{fmt_dkk(total)} DKK/mois)")
        if is_estimate:
            checks.append("charges non précisées (total estimé)")
        size = listing.size_m2 or 0
        if size >= cfg.listing["hard_min_size_m2"] and total < b["suspicious_low_total"]:
            facts.scam_flags.append("prix anormalement bas")

    # --- Surface et pièces ------------------------------------------------------
    L = cfg.listing
    if listing.size_m2 is not None:
        if listing.size_m2 < L["hard_min_size_m2"]:
            red.append(f"trop petit ({listing.size_m2:g} m²)")
        elif listing.size_m2 < L["min_size_m2"]:
            orange.append(f"surface limite ({listing.size_m2:g} m²)")
    else:
        checks.append("surface")
    if listing.rooms is not None and listing.rooms < L["min_rooms"]:
        red.append(f"{listing.rooms} pièce(s) seulement")

    # --- Meublé -------------------------------------------------------------------
    if facts.furnished is False:
        red.append("non meublé")
    elif facts.furnished is None:
        orange.append("meublé non précisé")

    # --- Étage --------------------------------------------------------------------
    if facts.floor is None:
        checks.append("étage")
    elif facts.floor in L.get("avoid_floors", []):
        label = "rez-de-chaussée" if facts.floor == 0 else ("sous-sol" if facts.floor < 0 else f"{facts.floor}{'er' if facts.floor == 1 else 'e'} étage")
        orange.append(f"{label} (lumière)")
    elif facts.floor < 0:
        orange.append("sous-sol")

    # --- Date d'entrée ---------------------------------------------------------------
    d = facts.available_from
    if d is None:
        checks.append("date d'entrée")
    elif d > cfg.move_in_latest:
        red.append(f"entrée trop tardive ({fmt_date(d)})")
    elif d < cfg.move_in_earliest:
        orange.append(f"entrée avant la date visée ({fmt_date(d)})")

    # --- Bail et domiciliation -----------------------------------------------------------
    if facts.domicile_allowed is False:
        red.append("domiciliation impossible (pas de CPR)")
    elif facts.domicile_allowed is None:
        checks.append("domiciliation possible (CPR)")
    if facts.sublet:
        checks.append("sous-location : accord écrit du propriétaire")
    if facts.time_limited:
        checks.append("durée du bail")

    # --- Arnaque -------------------------------------------------------------------------------
    for flag in facts.scam_flags:
        orange.append(f"⚠️ arnaque possible : {flag}")

    # --- Bonus ----------------------------------------------------------------------------------
    if facts.traversant:
        bonuses.append("☀️ Traversant")
    if facts.open_kitchen:
        bonuses.append("Cuisine ouverte")
    if facts.balcony:
        bonuses.append("Balcon ou terrasse")

    verdict = "red" if red else ("orange" if orange else "green")
    return Analysis(
        verdict=verdict,
        reasons=red + orange,
        checks=checks,
        bonuses=bonuses,
        zone=zone.name if zone else (listing.area or None),
        zone_tier=tier,
        total_estimate=total,
        total_is_estimate=is_estimate,
        facts=facts,
    )
