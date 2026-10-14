from pathlib import Path

import pytest

from hygge_traversant.config import Secrets, load_config

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def cfg(monkeypatch):
    """Config d'exemple du repo, avec des secrets factices (aucun .env réel lu)."""
    for k in ("NTFY_TOPIC_ALERTS", "NTFY_TOPIC_QUIET", "NTFY_TOPIC_TEST", "CONTACT_PHONE"):
        monkeypatch.delenv(k, raising=False)
    c = load_config(ROOT / "config.example.yaml")
    c.secrets = Secrets(topic_alerts="t-alerts", topic_quiet="t-quiet", topic_test="t-test",
                        contact_phone="+00 0 00 00 00 00")
    c.raw["database"] = ":memory:"
    # Valeurs fixes pour que les tests ne dépendent pas de l'exemple
    c.raw["budget"].update(target_max_total=14000, absolute_max_total=14500,
                           utilities_estimate=1500, suspicious_low_total=8000)
    c.raw["move_in"].update(earliest="2027-01-15", latest="2027-03-01")
    return c
