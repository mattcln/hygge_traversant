"""Message de présentation à copier-coller, dans la langue de l'annonce.

Les vrais textes sont dans private/messages/{fr,da,en}.txt (ignoré par git).
À défaut, on utilise les exemples génériques de messages.example/.

Variables disponibles dans les textes : {area} (quartier de l'annonce),
{phone} (CONTACT_PHONE du .env).
"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..models import Analysis, Listing

FALLBACK_AREA = {"da": "området", "en": "the area", "fr": "ce quartier"}


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def template_path(cfg: Config, lang: str) -> Path:
    for folder in (cfg.base_dir / "private" / "messages", cfg.base_dir / "messages.example"):
        p = folder / f"{lang}.txt"
        if p.exists():
            return p
    raise FileNotFoundError(f"Aucun modèle de message pour la langue '{lang}'")


def pick_language(analysis: Analysis, available: tuple[str, ...] = ("da", "en")) -> str:
    lang = analysis.facts.language
    return lang if lang in available else "en"


def render_message(listing: Listing, analysis: Analysis, cfg: Config, lang: str | None = None) -> str:
    lang = lang or pick_language(analysis)
    text = template_path(cfg, lang).read_text(encoding="utf-8").strip()
    area = listing.area or FALLBACK_AREA.get(lang, "")
    return text.format_map(_SafeDict(area=area, phone=cfg.secrets.contact_phone))
