"""Notifications ntfy : alerte (notif 1), message à copier (notif 2), santé, récap.

Publication en JSON sur la racine du serveur (https://docs.ntfy.sh/publish/#publish-as-json),
ce qui évite les soucis d'encodage des emojis dans les en-têtes HTTP.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..analysis.verdict import fmt_date, fmt_dkk
from ..config import Config
from ..models import Analysis, Listing

log = logging.getLogger(__name__)


@dataclass
class Notification:
    topic: str
    title: str
    message: str
    priority: int = 3
    tags: list[str] = field(default_factory=list)
    click: str | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        p: dict[str, Any] = {
            "topic": self.topic,
            "title": self.title,
            "message": self.message,
            "priority": self.priority,
        }
        if self.tags:
            p["tags"] = self.tags
        if self.click:
            p["click"] = self.click
        if self.actions:
            p["actions"] = self.actions
        return p


# --- Construction des notifications -----------------------------------------------


def topic_for(cfg: Config, verdict: str) -> str:
    s = cfg.secrets
    if cfg.mode != "live":
        return s.topic_test
    return s.topic_alerts if verdict == "green" else s.topic_quiet


def short_place(listing: Listing, analysis: Analysis) -> str:
    return listing.area or analysis.zone or "Zone ?"


def alert_title(listing: Listing, analysis: Analysis) -> str:
    parts: list[str] = []
    if analysis.facts.traversant:
        parts.append("☀️ Traversant")
    parts.append(short_place(listing, analysis))
    if listing.size_m2:
        parts.append(f"{listing.size_m2:g} m²")
    furnished = analysis.facts.furnished
    parts.append("meublé" if furnished else ("meublé ?" if furnished is None else "non meublé"))
    if analysis.total_estimate is not None:
        approx = "~" if analysis.total_is_estimate else ""
        parts.append(f"{approx}{fmt_dkk(analysis.total_estimate)} DKK")
    return " · ".join(parts)


def alert_body(listing: Listing, analysis: Analysis) -> str:
    lines: list[str] = []
    if analysis.verdict == "green":
        lines.append("🟢 Dans les critères")
    else:
        lines.append(f"{analysis.emoji} " + " ; ".join(analysis.reasons))

    if listing.rent is not None:
        if analysis.facts.utilities_included:
            charges = "charges incluses"
        elif listing.utilities is not None:
            charges = f"+ {fmt_dkk(listing.utilities)} charges"
        else:
            charges = "+ charges ? (estimées)"
        lines.append(f"Loyer {fmt_dkk(listing.rent)} DKK {charges}")

    f = analysis.facts
    lines.append(f"Entrée : {fmt_date(f.available_from) if f.available_from else 'non précisée'}")
    if f.floor is not None:
        lines.append(f"Étage : {'RDC' if f.floor == 0 else f.floor}")
    bail = [x for x, ok in (("sous-location", f.sublet), ("durée limitée", f.time_limited)) if ok]
    if bail:
        lines.append("Bail : " + ", ".join(bail))
    if analysis.bonuses:
        lines.append("Bonus : " + ", ".join(analysis.bonuses))
    if analysis.checks:
        lines.append("À vérifier : " + ", ".join(analysis.checks))
    return "\n".join(lines)


def build_alert(listing: Listing, analysis: Analysis, cfg: Config) -> Notification:
    live_green = cfg.mode == "live" and analysis.verdict == "green"
    return Notification(
        topic=topic_for(cfg, analysis.verdict),
        title=alert_title(listing, analysis),
        message=alert_body(listing, analysis),
        priority=5 if live_green else (4 if analysis.verdict == "green" else 3),
        tags=["house"],
        click=listing.url,
        actions=[{"action": "view", "label": "Annonce", "url": listing.url, "clear": False}],
    )


def build_message(listing: Listing, analysis: Analysis, cfg: Config, text: str) -> Notification:
    size = f" {listing.size_m2:g} m²" if listing.size_m2 else ""
    return Notification(
        topic=topic_for(cfg, analysis.verdict),
        title=f"✉️ Message · {short_place(listing, analysis)}{size}",
        message=text,
        priority=2,  # pas de son : la notif 1 a déjà sonné
    )


# --- Envoi ---------------------------------------------------------------------------


class Notifier:
    def __init__(self, cfg: Config, dry_run: bool = False, client: httpx.Client | None = None):
        self.cfg = cfg
        self.dry_run = dry_run
        self.client = client or httpx.Client(timeout=15)

    def send(self, n: Notification) -> bool:
        if not n.topic:
            log.warning("Canal ntfy vide (vérifier le .env) : notification ignorée : %s", n.title)
            return False
        if self.dry_run:
            print(f"\n--- [{n.topic}] priorité {n.priority} ---\n{n.title}\n{n.message}")
            if n.actions:
                print("Boutons :", ", ".join(a["label"] for a in n.actions))
            return True
        try:
            r = self.client.post(
                self.cfg.secrets.ntfy_server + "/",
                content=json.dumps(n.payload(), ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            r.raise_for_status()
            return True
        except httpx.HTTPError as e:
            log.error("Échec d'envoi ntfy (%s) : %s", n.title, e)
            return False

    def system(self, title: str, message: str, priority: int = 4) -> bool:
        """Alertes techniques (santé, erreurs) : toujours sur le canal de test,
        pour ne pas les envoyer à tout le foyer."""
        return self.send(Notification(topic=self.cfg.secrets.topic_test, title=title, message=message,
                                      priority=priority, tags=["warning"]))
