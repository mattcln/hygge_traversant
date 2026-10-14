"""Un passage complet sur une source : chercher, dédoublonner, analyser, stocker, notifier."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .analysis import analyze
from .config import Config
from .db import Database
from .messaging import render_message
from .models import Analysis, Listing
from .notify import Notifier, build_alert, build_message
from .sources.base import Source

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    found: int = 0
    new: int = 0
    notified: int = 0
    error: str | None = None


def should_notify(analysis: Analysis) -> bool:
    return analysis.verdict in ("green", "orange")


def notify_listing(listing: Listing, analysis: Analysis, cfg: Config, notifier: Notifier) -> bool:
    ok = notifier.send(build_alert(listing, analysis, cfg))
    n = cfg.notify
    wants_message = n.get("send_message", True) and (
        analysis.verdict == "green" or n.get("send_orange_message", True)
    )
    if ok and wants_message:
        try:
            text = render_message(listing, analysis, cfg)
            notifier.send(build_message(listing, analysis, cfg, text))
        except FileNotFoundError as e:
            log.warning("Message non envoyé : %s", e)
    return ok


def run_source(source: Source, cfg: Config, db: Database, notifier: Notifier,
               today: date | None = None) -> RunResult:
    res = RunResult()
    run_id = db.start_run(source.name)
    max_notifs = int(cfg.notify.get("max_per_run", 10))
    try:
        listings = source.search()
        res.found = len(listings)
        for stub in listings:
            if db.is_known(stub):
                old_rent = db.touch(stub)
                if old_rent is not None:
                    log.info("Prix changé : %s %s -> %s", stub.url, old_rent, stub.rent)
                continue
            res.new += 1
            try:
                listing = source.enrich(stub)
            except NotImplementedError:
                raise
            except Exception as e:  # une page détail cassée ne bloque pas les autres
                log.warning("Page détail illisible (%s) : %s", stub.url, e)
                listing = stub
            analysis = analyze(listing, cfg, today=today)
            db.save(listing, analysis)
            log.info("%s %s : %s", analysis.emoji, listing.url, ", ".join(analysis.reasons) or "ok")
            if should_notify(analysis) and res.notified < max_notifs:
                if notify_listing(listing, analysis, cfg, notifier):
                    db.mark_notified(listing)
                    res.notified += 1
    except Exception as e:
        res.error = f"{type(e).__name__}: {e}"
        log.error("Passage %s en erreur : %s", source.name, res.error)
    db.end_run(run_id, res.found, res.new, res.error)
    return res


def check_health(source_name: str, cfg: Config, db: Database, notifier: Notifier) -> None:
    """Prévient si la source ne renvoie plus rien ou enchaîne les erreurs. Une alerte par incident."""
    h = cfg.section("health")
    key = f"health_alerted:{source_name}"
    problem = None

    errors = db.consecutive_errors(source_name)
    if errors >= int(h.get("alert_after_errors", 5)):
        last = db.last_error(source_name)
        problem = f"{errors} passages en erreur d'affilée. Dernière erreur : {last}"
    else:
        last_find = db.last_successful_find(source_name)
        limit = timedelta(hours=float(h.get("alert_after_hours", 6)))
        if last_find and datetime.now(timezone.utc) - datetime.fromisoformat(last_find) > limit:
            problem = (f"Aucune annonce trouvée depuis plus de {limit.total_seconds() / 3600:g} h. "
                       "Le site a peut-être changé de structure.")

    already = db.get_kv(key) == "1"
    if problem and not already:
        notifier.system(f"⚠️ hygge_traversant : souci sur {source_name}", problem)
        db.set_kv(key, "1")
    elif not problem and already:
        notifier.system(f"✅ hygge_traversant : {source_name} refonctionne", "Tout est rentré dans l'ordre.", priority=2)
        db.set_kv(key, "0")
