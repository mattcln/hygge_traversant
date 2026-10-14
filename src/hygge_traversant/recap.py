"""Récap du soir : ce qui est passé dans la journée, et ce que le filtre a rejeté."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .analysis.verdict import fmt_dkk
from .config import Config
from .db import Database
from .notify import Notification, Notifier


def _reason_label(reason: str) -> str:
    """'trop cher (~15 200 DKK/mois)' -> 'trop cher' pour regrouper."""
    return reason.split(" (")[0]


def build_recap(cfg: Config, db: Database, hours: int = 24) -> tuple[str, str]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    rows = db.listings_since(since)
    runs = db.runs_since(since)
    counts = Counter(r["verdict"] for r in rows)

    title = (f"📋 Récap : {len(rows)} nouvelles annonces · "
             f"🟢 {counts['green']} · 🟠 {counts['orange']} · 🔴 {counts['red']}")
    lines: list[str] = []

    for verdict, emoji in (("green", "🟢"), ("orange", "🟠")):
        for r in [r for r in rows if r["verdict"] == verdict][:8]:
            size = f"{r['size_m2']:g} m²" if r["size_m2"] else "? m²"
            lines.append(f"{emoji} {r['area'] or r['zone'] or '?'} · {size} · "
                         f"~{fmt_dkk(r['total_estimate'])} DKK\n   {r['url']}")

    reds = Counter(_reason_label(json.loads(r["reasons"])[0]) for r in rows
                   if r["verdict"] == "red" and r["reasons"] and json.loads(r["reasons"]))
    if reds:
        lines.append("Rejets : " + ", ".join(f"{k} ({v})" for k, v in reds.most_common(5)))

    # Délai publication -> détection, quand la source donne l'heure de publication
    delays = []
    for r in rows:
        if r["published_at"]:
            try:
                pub = datetime.fromisoformat(r["published_at"])
                seen = datetime.fromisoformat(r["first_seen_at"])
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                delays.append((seen - pub).total_seconds() / 60)
            except ValueError:
                pass
    if delays:
        delays.sort()
        lines.append(f"Délai de détection médian : {delays[len(delays) // 2]:.0f} min")

    for p in db.price_changes_since(since):
        lines.append(f"💸 Prix changé {p['area'] or ''} : {fmt_dkk(p['old_rent'])} → "
                     f"{fmt_dkk(p['new_rent'])} DKK\n   {p['url']}")

    errors = sum(1 for r in runs if r["error"])
    lines.append(f"Passages : {len(runs)} (dont {errors} en erreur)")
    return title, "\n".join(lines) or "Rien de neuf aujourd'hui."


def send_recap(cfg: Config, db: Database, notifier: Notifier) -> bool:
    title, body = build_recap(cfg, db)
    s = cfg.secrets
    topic = s.topic_quiet if cfg.mode == "live" else s.topic_test
    return notifier.send(Notification(topic=topic, title=title, message=body, priority=2, tags=["clipboard"]))


def recap_due(cfg: Config, db: Database, now: datetime | None = None) -> bool:
    r = cfg.section("recap")
    if not r.get("enabled", True):
        return False
    tz = ZoneInfo(cfg.timezone)
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    return now.hour >= int(r.get("hour", 21)) and db.get_kv("recap_last_date") != now.date().isoformat()


def mark_recap_sent(cfg: Config, db: Database, now: datetime | None = None) -> None:
    tz = ZoneInfo(cfg.timezone)
    db.set_kv("recap_last_date", (now or datetime.now(timezone.utc)).astimezone(tz).date().isoformat())
