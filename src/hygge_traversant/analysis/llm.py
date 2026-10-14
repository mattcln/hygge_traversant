"""Analyse par LLM : branchée plus tard, même sortie que keywords.extract_facts.

Idée : envoyer le texte de l'annonce à un petit modèle (Claude Haiku) et lui
demander un JSON avec les champs de Facts (meublé, charges incluses, date
d'entrée, domiciliation, traversant, signaux d'arnaque...). L'analyse par
mots-clés reste le filet de sécurité si l'appel échoue.
"""

from __future__ import annotations

from ..models import Facts, Listing


def extract_facts(listing: Listing, api_key: str) -> Facts:  # pragma: no cover
    raise NotImplementedError("Analyse LLM pas encore branchée : utiliser analysis.engine = keywords")
