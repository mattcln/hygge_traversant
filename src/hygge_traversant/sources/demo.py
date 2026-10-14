"""Annonces inventées, pour tester les notifications sans dépendre de BoligPortal."""

from __future__ import annotations

from datetime import date, datetime, timezone

from ..models import Listing
from .base import Source


def demo_listings() -> list[Listing]:
    now = datetime.now(timezone.utc)
    return [
        Listing(
            source="demo", source_id="demo-vert", url="https://www.boligportal.dk/",
            title="Lys og møbleret 2-værelses lejlighed i Vanløse",
            description=(
                "Dejlig gennemlyst lejlighed på 3. sal med åbent køkken og altan. "
                "Fuldt møbleret. Husleje inkl. forbrug. Ledig fra 1. februar 2027. "
                "Mulighed for at blive tilmeldt folkeregisteret."
            ),
            area="Vanløse", postal_code=2720, rent=13200, size_m2=62, rooms=2,
            published_at=now,
        ),
        Listing(
            source="demo", source_id="demo-orange", url="https://www.boligportal.dk/",
            title="2-room apartment in Ørestad, sublet",
            description=(
                "Nice apartment on the 1st floor close to the metro. Sublet for 12 months, "
                "available from February 1st. Rent excl. utilities (aconto 1,200 DKK)."
            ),
            area="Ørestad", postal_code=2300, rent=12400, utilities=1200, size_m2=58, rooms=2,
            published_at=now,
        ),
        Listing(
            source="demo", source_id="demo-rouge", url="https://www.boligportal.dk/",
            title="Umøbleret lejlighed på Østerbro",
            description="Stor lejlighed, umøbleret. Ledig straks.",
            area="Østerbro", postal_code=2100, rent=15500, size_m2=75, rooms=3,
            available_from=date(2026, 11, 1), published_at=now,
        ),
    ]


class DemoSource(Source):
    name = "demo"

    def search(self) -> list[Listing]:
        return demo_listings()
