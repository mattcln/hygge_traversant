"""Interface commune des sources d'annonces."""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod

import httpx

from ..models import Listing

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0 Safari/537.36"
)


def make_client() -> httpx.Client:
    return httpx.Client(
        timeout=20,
        follow_redirects=True,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        },
    )


class Source(ABC):
    name: str = "source"

    @abstractmethod
    def search(self) -> list[Listing]:
        """Annonces de la (des) page(s) de résultats, les plus récentes d'abord.
        Champs minimum : source_id et url. Le reste si la page le donne."""

    def enrich(self, listing: Listing) -> Listing:
        """Complète une nouvelle annonce avec sa page détail. Par défaut : rien."""
        return listing

    @staticmethod
    def polite_pause(bounds: tuple[float, float]) -> None:
        time.sleep(random.uniform(*bounds))
