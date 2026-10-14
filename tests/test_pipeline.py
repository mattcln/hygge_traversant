import json
from datetime import date

from hygge_traversant.db import Database
from hygge_traversant.notify import Notifier, build_alert
from hygge_traversant.pipeline import check_health, run_source
from hygge_traversant.recap import build_recap
from hygge_traversant.sources import DemoSource
from hygge_traversant.sources.base import Source

TODAY = date(2026, 10, 13)


class RecordingNotifier(Notifier):
    def __init__(self, cfg):
        super().__init__(cfg, dry_run=True)
        self.sent = []

    def send(self, n):
        self.sent.append(n)
        return True


def test_demo_run_notifies_green_and_orange_with_messages(cfg):
    db, notifier = Database(), RecordingNotifier(cfg)
    res = run_source(DemoSource(), cfg, db, notifier, today=TODAY)
    assert (res.found, res.new, res.notified, res.error) == (3, 3, 2, None)
    titles = [n.title for n in notifier.sent]
    assert len(notifier.sent) == 4                     # 2 alertes + 2 messages
    assert titles[0].startswith("☀️ Traversant · Vanløse")
    assert titles[1].startswith("✉️ Message")
    assert all(n.topic == "t-test" for n in notifier.sent)  # mode observe


def test_second_pass_does_not_renotify(cfg):
    db, notifier = Database(), RecordingNotifier(cfg)
    run_source(DemoSource(), cfg, db, notifier, today=TODAY)
    notifier.sent.clear()
    res = run_source(DemoSource(), cfg, db, notifier, today=TODAY)
    assert res.new == 0 and notifier.sent == []


def test_live_mode_routes_by_verdict(cfg):
    cfg.raw["mode"] = "live"
    notifier = RecordingNotifier(cfg)
    run_source(DemoSource(), cfg, Database(), notifier, today=TODAY)
    alerts = [n for n in notifier.sent if not n.title.startswith("✉️")]
    assert [n.topic for n in alerts] == ["t-alerts", "t-quiet"]
    assert alerts[0].priority == 5


def test_alert_payload_has_listing_button(cfg):
    listing = DemoSource().search()[0]
    from hygge_traversant.analysis import analyze
    n = build_alert(listing, analyze(listing, cfg, today=TODAY), cfg)
    p = n.payload()
    assert p["click"] == listing.url
    assert p["actions"][0]["label"] == "Annonce"
    json.dumps(p, ensure_ascii=False)  # sérialisable avec les emojis


class BrokenSource(Source):
    name = "broken"

    def search(self):
        raise RuntimeError("site changé")


def test_health_alert_once_after_errors(cfg):
    cfg.raw["health"] = {"alert_after_errors": 2, "alert_after_hours": 6}
    db, notifier = Database(), RecordingNotifier(cfg)
    for _ in range(3):
        res = run_source(BrokenSource(), cfg, db, notifier)
        check_health("broken", cfg, db, notifier)
    assert res.error and "site changé" in res.error
    system = [n for n in notifier.sent if "souci" in n.title]
    assert len(system) == 1 and system[0].topic == "t-test"


def test_recap(cfg):
    db = Database()
    run_source(DemoSource(), cfg, db, RecordingNotifier(cfg), today=TODAY)
    title, body = build_recap(cfg, db)
    assert "3 nouvelles annonces" in title
    assert "Rejets" in body
