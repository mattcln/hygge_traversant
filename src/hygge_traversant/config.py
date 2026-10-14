"""Chargement de config.yaml et des secrets du .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


@dataclass
class Zone:
    name: str
    tier: str
    postal_ranges: list[tuple[int, int]]
    keywords: list[str]

    def matches_postal(self, code: int | None) -> bool:
        return code is not None and any(lo <= code <= hi for lo, hi in self.postal_ranges)

    def matches_text(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in self.keywords)


@dataclass
class Secrets:
    ntfy_server: str = "https://ntfy.sh"
    topic_alerts: str = ""
    topic_quiet: str = ""
    topic_test: str = ""
    contact_phone: str = ""
    anthropic_api_key: str = ""


@dataclass
class Config:
    raw: dict[str, Any]
    zones: list[Zone]
    secrets: Secrets
    base_dir: Path = field(default_factory=Path.cwd)

    # Raccourcis lisibles
    @property
    def mode(self) -> str:
        return self.raw.get("mode", "observe")

    @property
    def timezone(self) -> str:
        return self.raw.get("timezone", "Europe/Copenhagen")

    @property
    def budget(self) -> dict[str, Any]:
        return self.raw["budget"]

    @property
    def listing(self) -> dict[str, Any]:
        return self.raw["listing"]

    @property
    def move_in_earliest(self) -> date:
        return _as_date(self.raw["move_in"]["earliest"])

    @property
    def move_in_latest(self) -> date:
        return _as_date(self.raw["move_in"]["latest"])

    @property
    def notify(self) -> dict[str, Any]:
        return self.raw.get("notify", {})

    @property
    def database_path(self) -> Path:
        p = Path(self.raw.get("database", "data/hygge.sqlite3"))
        return p if p.is_absolute() else self.base_dir / p

    def section(self, name: str) -> dict[str, Any]:
        return self.raw.get(name, {}) or {}


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _parse_postal(spec: str | int) -> tuple[int, int]:
    s = str(spec).strip()
    if "-" in s:
        lo, hi = s.split("-", 1)
        return int(lo), int(hi)
    return int(s), int(s)


def parse_zones(raw_zones: dict[str, list[dict]]) -> list[Zone]:
    zones: list[Zone] = []
    for tier in ("excluded", "priority", "secondary", "open"):
        for z in raw_zones.get(tier, []) or []:
            zones.append(
                Zone(
                    name=z["name"],
                    tier=tier,
                    postal_ranges=[_parse_postal(p) for p in z.get("postal_codes", [])],
                    keywords=[k.lower() for k in z.get("keywords", [])],
                )
            )
    return zones


def load_secrets() -> Secrets:
    return Secrets(
        ntfy_server=os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/"),
        topic_alerts=os.environ.get("NTFY_TOPIC_ALERTS", ""),
        topic_quiet=os.environ.get("NTFY_TOPIC_QUIET", ""),
        topic_test=os.environ.get("NTFY_TOPIC_TEST", ""),
        contact_phone=os.environ.get("CONTACT_PHONE", ""),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
    )


def load_config(path: str | Path = "config.yaml") -> Config:
    path = Path(path)
    if load_dotenv is not None:
        load_dotenv(path.parent / ".env")
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config(
        raw=raw,
        zones=parse_zones(raw.get("zones", {})),
        secrets=load_secrets(),
        base_dir=path.parent.resolve(),
    )
