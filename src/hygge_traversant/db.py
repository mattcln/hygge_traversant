"""Base SQLite : annonces déjà vues, historique, passages, petit état clé-valeur."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Analysis, Listing

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    source          TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    url             TEXT NOT NULL,
    title           TEXT,
    area            TEXT,
    postal_code     INTEGER,
    rent            INTEGER,
    utilities       INTEGER,
    total_estimate  INTEGER,
    size_m2         REAL,
    rooms           INTEGER,
    floor           INTEGER,
    furnished       INTEGER,
    available_from  TEXT,
    published_at    TEXT,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    verdict         TEXT,
    zone            TEXT,
    reasons         TEXT,
    checks          TEXT,
    bonuses         TEXT,
    language        TEXT,
    notified_at     TEXT,
    raw_text        TEXT,
    PRIMARY KEY (source, source_id)
);

CREATE TABLE IF NOT EXISTS price_changes (
    source      TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    seen_at     TEXT NOT NULL,
    old_rent    INTEGER,
    new_rent    INTEGER
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    n_found     INTEGER NOT NULL DEFAULT 0,
    n_new       INTEGER NOT NULL DEFAULT 0,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


class Database:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # --- annonces -----------------------------------------------------------

    def get(self, source: str, source_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM listings WHERE source = ? AND source_id = ?", (source, source_id)
        ).fetchone()

    def is_known(self, listing: Listing) -> bool:
        return self.get(*listing.key) is not None

    def touch(self, listing: Listing) -> int | None:
        """Met à jour last_seen d'une annonce connue. Renvoie l'ancien loyer s'il a changé."""
        row = self.get(*listing.key)
        if row is None:
            return None
        now = utcnow()
        old_rent = row["rent"]
        changed = listing.rent is not None and old_rent is not None and listing.rent != old_rent
        with self.conn:
            self.conn.execute(
                "UPDATE listings SET last_seen_at = ?, rent = COALESCE(?, rent) "
                "WHERE source = ? AND source_id = ?",
                (now, listing.rent, *listing.key),
            )
            if changed:
                self.conn.execute(
                    "INSERT INTO price_changes VALUES (?, ?, ?, ?, ?)",
                    (*listing.key, now, old_rent, listing.rent),
                )
        return old_rent if changed else None

    def save(self, listing: Listing, analysis: Analysis) -> None:
        now = utcnow()
        f = analysis.facts
        values = dict(
            source=listing.source,
            source_id=listing.source_id,
            url=listing.url,
            title=listing.title,
            area=listing.area,
            postal_code=listing.postal_code,
            rent=listing.rent,
            utilities=listing.utilities,
            total_estimate=analysis.total_estimate,
            size_m2=listing.size_m2,
            rooms=listing.rooms,
            floor=f.floor,
            furnished=None if f.furnished is None else int(f.furnished),
            available_from=_iso(f.available_from),
            published_at=_iso(listing.published_at),
            first_seen_at=now,
            last_seen_at=now,
            verdict=analysis.verdict,
            zone=analysis.zone,
            reasons=json.dumps(analysis.reasons, ensure_ascii=False),
            checks=json.dumps(analysis.checks, ensure_ascii=False),
            bonuses=json.dumps(analysis.bonuses, ensure_ascii=False),
            language=f.language,
            raw_text=listing.text,
        )
        cols = ", ".join(values)
        marks = ", ".join(f":{k}" for k in values)
        updates = ", ".join(
            f"{k} = excluded.{k}" for k in values if k not in ("first_seen_at", "source", "source_id")
        )
        with self.conn:
            self.conn.execute(
                f"INSERT INTO listings ({cols}) VALUES ({marks}) "
                f"ON CONFLICT(source, source_id) DO UPDATE SET {updates}",
                values,
            )

    def mark_notified(self, listing: Listing) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE listings SET notified_at = ? WHERE source = ? AND source_id = ?",
                (utcnow(), *listing.key),
            )

    # --- passages -------------------------------------------------------------

    def start_run(self, source: str) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO runs (source, started_at) VALUES (?, ?)", (source, utcnow())
            )
        return cur.lastrowid

    def end_run(self, run_id: int, n_found: int, n_new: int, error: str | None = None) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE runs SET n_found = ?, n_new = ?, error = ? WHERE id = ?",
                (n_found, n_new, error, run_id),
            )

    def consecutive_errors(self, source: str) -> int:
        rows = self.conn.execute(
            "SELECT error FROM runs WHERE source = ? ORDER BY id DESC LIMIT 50", (source,)
        ).fetchall()
        n = 0
        for r in rows:
            if r["error"] is None:
                break
            n += 1
        return n

    def last_error(self, source: str) -> str | None:
        row = self.conn.execute(
            "SELECT error FROM runs WHERE source = ? AND error IS NOT NULL ORDER BY id DESC LIMIT 1",
            (source,),
        ).fetchone()
        return row["error"] if row else None

    def last_successful_find(self, source: str) -> str | None:
        row = self.conn.execute(
            "SELECT started_at FROM runs WHERE source = ? AND error IS NULL AND n_found > 0 "
            "ORDER BY id DESC LIMIT 1",
            (source,),
        ).fetchone()
        return row["started_at"] if row else None

    # --- état clé-valeur --------------------------------------------------------

    def get_kv(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_kv(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    # --- récap -----------------------------------------------------------------

    def listings_since(self, since_iso: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM listings WHERE first_seen_at >= ? ORDER BY first_seen_at", (since_iso,)
        ).fetchall()

    def price_changes_since(self, since_iso: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT p.*, l.url, l.area FROM price_changes p "
            "JOIN listings l USING (source, source_id) WHERE p.seen_at >= ?",
            (since_iso,),
        ).fetchall()

    def runs_since(self, since_iso: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM runs WHERE started_at >= ?", (since_iso,)
        ).fetchall()
