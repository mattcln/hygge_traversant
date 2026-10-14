"""Formats communs à toutes les sources et à l'analyse."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class Listing:
    """Une annonce, quelle que soit la source.

    Les champs structurés (rent, size_m2, furnished...) viennent de la source
    quand elle les fournit. Sinon l'analyse essaie de les déduire du texte.
    """

    source: str
    source_id: str
    url: str
    title: str = ""
    description: str = ""
    area: str | None = None            # quartier ou ville affichés
    postal_code: int | None = None
    address: str | None = None
    rent: int | None = None            # loyer mensuel affiché, DKK
    utilities: int | None = None       # charges (aconto) si connues, DKK
    utilities_included: bool | None = None
    deposit: int | None = None
    size_m2: float | None = None
    rooms: int | None = None
    floor: int | None = None
    furnished: bool | None = None
    available_from: date | None = None
    rental_period: str | None = None   # texte brut, ex. "Unlimited", "12 months"
    published_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.source_id)

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.description}"


@dataclass
class Facts:
    """Ce que l'analyse a compris de l'annonce (structuré + texte)."""

    furnished: bool | None = None
    utilities_included: bool | None = None
    sublet: bool = False
    time_limited: bool = False
    domicile_allowed: bool | None = None
    traversant: bool = False
    open_kitchen: bool = False
    balcony: bool = False
    floor: int | None = None
    available_from: date | None = None
    scam_flags: list[str] = field(default_factory=list)
    language: str = "en"


@dataclass
class Analysis:
    verdict: str                              # "green" | "orange" | "red"
    reasons: list[str] = field(default_factory=list)   # pourquoi orange ou rouge
    checks: list[str] = field(default_factory=list)    # à vérifier en ouvrant l'annonce
    bonuses: list[str] = field(default_factory=list)   # traversant, cuisine ouverte...
    zone: str | None = None
    zone_tier: str = "unknown"   # priority | secondary | open | excluded | unknown
    total_estimate: int | None = None
    total_is_estimate: bool = True
    facts: Facts = field(default_factory=Facts)

    @property
    def emoji(self) -> str:
        return {"green": "🟢", "orange": "🟠", "red": "🔴"}[self.verdict]
