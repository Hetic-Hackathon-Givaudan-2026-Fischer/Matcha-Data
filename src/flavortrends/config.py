"""Configuration lue depuis les variables d'environnement (fichier .env à la racine)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


class ConfigError(RuntimeError):
    """Paramètre manquant ou invalide : le message explique quoi corriger."""


def _list(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str
    contact: str
    pseudonymization_salt: str
    youtube_api_key: str
    youtube_unit_budget: int
    bluesky_handle: str
    bluesky_app_password: str
    off_categories: list[str]
    off_countries: list[str]
    langs: list[str]
    # Maîtrise de l'espace disque (utile sur Supabase)
    off_only_flavor_matches: bool = False
    wikipedia_start: str = "2016-01-01"
    raw_retention_days: int = 0
    db_size_limit_mb: int = 0
    bluesky_max_pages: int = 5
    # Pinterest (API réservée aux partenaires ; vide = seule la veille manuelle est utilisée)
    pinterest_access_token: str = ""
    pinterest_regions: tuple = ("FR", "US")
    pinterest_trend_types: tuple = ("growing",)
    pinterest_interests: tuple = ("food_and_drinks",)
    # Google Trends automatique (pytrends) : zones « ZONE:langue » ; WORLD = monde entier
    google_trends_zones: tuple = (("WORLD", "en"), ("FR", "fr"))

    @property
    def user_agent(self) -> str:
        # Les en-têtes HTTP doivent rester en ASCII.
        return f"FlavorTrends/0.1 (student research project; contact: {self.contact})"

    def require_salt(self) -> str:
        if len(self.pseudonymization_salt) < 16:
            raise ConfigError(
                "PSEUDONYMIZATION_SALT est vide ou trop court dans .env. "
                "Générez-le avec : python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return self.pseudonymization_salt


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or ROOT / ".env")
    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql://data:change-me@localhost:5432/flavors"),
        contact=os.getenv("CONTACT", "equipe-data@example.org"),
        pseudonymization_salt=os.getenv("PSEUDONYMIZATION_SALT", ""),
        youtube_api_key=os.getenv("YOUTUBE_API_KEY", ""),
        youtube_unit_budget=int(os.getenv("YOUTUBE_UNIT_BUDGET", "9000")),
        bluesky_handle=os.getenv("BLUESKY_HANDLE", ""),
        bluesky_app_password=os.getenv("BLUESKY_APP_PASSWORD", ""),
        # Vide = tous les aliments, monde entier
        off_categories=_list(os.getenv("OFF_CATEGORIES", "")),
        off_countries=_list(os.getenv("OFF_COUNTRIES", "")),
        langs=_list(os.getenv("LANGS", "fr,en")),
        off_only_flavor_matches=os.getenv("OFF_ONLY_FLAVOR_MATCHES", "false").strip().lower() in ("1", "true", "oui", "yes"),
        wikipedia_start=os.getenv("WIKIPEDIA_START", "2016-01-01").strip() or "2016-01-01",
        raw_retention_days=int(os.getenv("RAW_RETENTION_DAYS", "0") or 0),
        db_size_limit_mb=int(os.getenv("DB_SIZE_LIMIT_MB", "0") or 0),
        bluesky_max_pages=int(os.getenv("BLUESKY_MAX_PAGES", "5") or 5),
        pinterest_access_token=os.getenv("PINTEREST_ACCESS_TOKEN", ""),
        pinterest_regions=tuple(_list(os.getenv("PINTEREST_REGIONS", "FR,US"))),
        pinterest_trend_types=tuple(_list(os.getenv("PINTEREST_TREND_TYPES", "growing"))),
        pinterest_interests=tuple(_list(os.getenv("PINTEREST_INTERESTS", "food_and_drinks"))),
        google_trends_zones=tuple(tuple(z.split(":", 1)) for z in _list(os.getenv("GOOGLE_TRENDS_ZONES", "WORLD:en,FR:fr"))),
    )
