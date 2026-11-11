"""Connexion PostgreSQL et migrations."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator
from urllib.parse import urlsplit

import psycopg
from psycopg.rows import dict_row

from .config import ROOT, ConfigError, Settings

log = logging.getLogger(__name__)
MIGRATIONS_DIR = ROOT / "migrations"


def connection_options(url: str) -> dict:
    """Options de connexion, compatibles avec une base locale comme avec Supabase."""
    parts = urlsplit(url)
    if parts.port == 6543:
        raise ConfigError(
            "DATABASE_URL utilise le « Transaction pooler » de Supabase (port 6543). Il casse les verrous qui "
            "empêchent deux collectes simultanées. Prenez l'adresse du « Session pooler » (port 5432) : "
            "Supabase > Connect > Session pooler.")
    opts = {
        "row_factory": dict_row,
        "connect_timeout": 10,       # sans délai maximal, Windows attend plusieurs minutes si la base est injoignable
        "prepare_threshold": None,   # pas de requêtes préparées : compatible avec les poolers de connexions
        # Signaux de maintien : une connexion silencieuse pendant une longue collecte (Google Trends, GDELT)
        # n'est pas coupée par le réseau ou le pooler.
        "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 5,
    }
    host = parts.hostname or ""
    if host.endswith(("supabase.co", "supabase.com")) and "sslmode" not in url:
        opts["sslmode"] = "require"  # connexion chiffrée vers Supabase
    return opts


@contextmanager
def connect(settings: Settings) -> Iterator[psycopg.Connection]:
    opts = connection_options(settings.database_url)
    try:
        conn = psycopg.connect(settings.database_url, **opts)
    except psycopg.OperationalError as exc:
        raise SystemExit(
            f"Connexion impossible à PostgreSQL ({exc}).\n"
            "Vérifiez DATABASE_URL dans .env (adresse, mot de passe), que le projet Supabase n'est pas en pause, "
            "ou que la base locale tourne."
        ) from exc
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate(conn: psycopg.Connection) -> list[str]:
    """Applique, dans l'ordre, les fichiers migrations/*.sql pas encore appliqués."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS public.schema_migrations ("
        " version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
    )
    # Sur Supabase, le schéma public est exposé par l'API web : RLS activé, aucune règle = aucun accès par l'API.
    # Le propriétaire de la table (notre connexion) n'est pas concerné.
    conn.execute("ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY")
    applied = {r["version"] for r in conn.execute("SELECT version FROM public.schema_migrations")}
    done = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO public.schema_migrations (version) VALUES (%s)", (path.name,))
        log.info("Migration appliquée : %s", path.name)
        done.append(path.name)
    conn.commit()
    return done
