"""Ligne de commande : hygge <commande>.

  hygge run                 boucle infinie (ce que fait le conteneur Docker)
  hygge once                un seul passage, puis s'arrête
  hygge demo [--dry-run]    envoie 3 annonces inventées (vert, orange, rouge) pour tester ntfy
  hygge recap [--dry-run]   envoie le récap des dernières 24 h maintenant
  hygge stats               résumé de la base dans le terminal
  hygge save-page URL FILE  sauvegarde une page (pour écrire le parser et ses tests)
"""

from __future__ import annotations

import argparse
import logging
import random
import signal
import sys
import time
from pathlib import Path

from . import recap
from .config import Config, load_config
from .db import Database
from .notify import Notifier
from .pipeline import check_health, run_source
from .sources import BoligPortalSource, DemoSource, Source
from .sources.base import make_client

log = logging.getLogger("hygge")


def build_sources(cfg: Config) -> list[Source]:
    sources: list[Source] = []
    bp = cfg.section("sources").get("boligportal", {})
    if bp.get("enabled", True):
        sources.append(BoligPortalSource(
            search_urls=bp["search_urls"],
            detail_delay=tuple(cfg.raw.get("detail_delay_seconds", [1.5, 4.0])),
        ))
    return sources


def one_pass(cfg: Config, db: Database, notifier: Notifier) -> None:
    for source in build_sources(cfg):
        res = run_source(source, cfg, db, notifier)
        log.info("%s : %d trouvées, %d nouvelles, %d notifiées%s", source.name, res.found,
                 res.new, res.notified, f", erreur : {res.error}" if res.error else "")
        check_health(source.name, cfg, db, notifier)
    if recap.recap_due(cfg, db):
        if recap.send_recap(cfg, db, notifier):
            recap.mark_recap_sent(cfg, db)


def cmd_run(cfg: Config, args) -> int:
    db, notifier = Database(cfg.database_path), Notifier(cfg, dry_run=args.dry_run)
    stop = {"flag": False}

    def _stop(*_):
        stop["flag"] = True
        log.info("Arrêt demandé, fin après ce passage.")

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    lo, hi = cfg.raw.get("interval_seconds", [120, 240])
    log.info("Démarrage en mode %s, passage toutes les %s à %s s", cfg.mode, lo, hi)
    while not stop["flag"]:
        one_pass(cfg, db, notifier)
        wait = random.uniform(lo, hi)
        end = time.monotonic() + wait
        while not stop["flag"] and time.monotonic() < end:
            time.sleep(1)
    return 0


def cmd_once(cfg: Config, args) -> int:
    one_pass(cfg, Database(cfg.database_path), Notifier(cfg, dry_run=args.dry_run))
    return 0


def cmd_demo(cfg: Config, args) -> int:
    # Base en mémoire : la démo ne pollue pas la vraie base. Toujours sur le canal de test.
    cfg.raw["mode"] = "observe"
    res = run_source(DemoSource(), cfg, Database(":memory:"), Notifier(cfg, dry_run=args.dry_run))
    print(f"\nDémo : {res.new} annonces analysées, {res.notified} notifiées (la rouge est filtrée).")
    return 0 if res.error is None else 1


def cmd_recap(cfg: Config, args) -> int:
    db = Database(cfg.database_path)
    ok = recap.send_recap(cfg, db, Notifier(cfg, dry_run=args.dry_run))
    return 0 if ok else 1


def cmd_stats(cfg: Config, args) -> int:
    db = Database(cfg.database_path)
    c = db.conn
    total = c.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    print(f"Annonces en base : {total}")
    for row in c.execute("SELECT verdict, COUNT(*) n FROM listings GROUP BY verdict"):
        print(f"  {row['verdict']} : {row['n']}")
    print("Notifiées :", c.execute("SELECT COUNT(*) FROM listings WHERE notified_at IS NOT NULL").fetchone()[0])
    print("Derniers passages :")
    for r in c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 5"):
        print(f"  {r['started_at']} {r['source']} trouvées={r['n_found']} nouvelles={r['n_new']}"
              + (f" ERREUR {r['error']}" if r["error"] else ""))
    return 0


def cmd_save_page(cfg: Config, args) -> int:
    with make_client() as client:
        r = client.get(args.url)
    out = Path(args.file)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(r.text, encoding="utf-8")
    print(f"HTTP {r.status_code}, {len(r.text):,} caractères écrits dans {out}")
    return 0 if r.is_success else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hygge", description="Alertes logement Copenhague")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "once", "demo", "recap"):
        p = sub.add_parser(name)
        p.add_argument("--dry-run", action="store_true", help="affiche au lieu d'envoyer sur ntfy")
    sub.add_parser("stats")
    p = sub.add_parser("save-page")
    p.add_argument("url")
    p.add_argument("file")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s : %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"{cfg_path} introuvable : copier config.example.yaml en config.yaml", file=sys.stderr)
        return 2
    cfg = load_config(cfg_path)
    handlers = {"run": cmd_run, "once": cmd_once, "demo": cmd_demo, "recap": cmd_recap,
                "stats": cmd_stats, "save-page": cmd_save_page}
    return handlers[args.command](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
