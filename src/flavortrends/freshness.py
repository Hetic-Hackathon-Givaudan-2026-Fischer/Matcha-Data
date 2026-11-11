"""Contrôle de fraîcheur : chaque source a-t-elle été collectée et nettoyée à temps ?

Niveaux :
- ok       : à jour
- info     : source non configurée (clé absente) : pas une anomalie
- warning  : à surveiller (dernière exécution partielle ou en échec mais données encore récentes,
             nettoyage en retard)
- alert    : en retard, jamais collectée, ou en échec depuis trop longtemps
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

import psycopg

from .config import Settings

CLEANING_MAX_DELAY = timedelta(hours=6)


@dataclass(frozen=True)
class Rule:
    source_id: str
    max_age: timedelta
    cadence: str
    configured: Callable[[Settings], bool] = lambda s: True


RULES = [
    Rule("wikipedia_pageviews", timedelta(hours=30), "chaque nuit"),
    Rule("open_food_facts", timedelta(hours=30), "chaque nuit"),
    Rule("gdelt", timedelta(hours=30), "chaque nuit"),
    Rule("rss", timedelta(hours=6), "toutes les 4 h"),
    Rule("google_news", timedelta(hours=6), "toutes les 4 h"),
    Rule("youtube", timedelta(hours=30), "chaque nuit", lambda s: bool(s.youtube_api_key)),
    Rule("bluesky", timedelta(hours=30), "chaque nuit", lambda s: bool(s.bluesky_handle and s.bluesky_app_password)),
    Rule("google_trends", timedelta(days=8), "chaque semaine (automatique via pytrends, ou export manuel)"),
    Rule("pinterest", timedelta(days=8), "veille manuelle chaque semaine (ou API si accès)"),
]

SQL = """
WITH runs AS (
    SELECT source_id,
           max(finished_at) FILTER (WHERE status IN ('success', 'partial')) AS last_ok_at,
           (array_agg(status ORDER BY started_at DESC))[1] AS last_status,
           (array_agg(started_at ORDER BY started_at DESC))[1] AS last_started_at,
           (array_agg(error ORDER BY started_at DESC))[1] AS last_error
    FROM raw.collection_run GROUP BY source_id
),
pending AS (
    SELECT source_id, count(*) AS pending, min(fetched_at) AS oldest_pending_at
    FROM raw.raw_document WHERE processed_at IS NULL GROUP BY source_id
),
data AS (
    SELECT source_id, max(published_at) AS data_until FROM core.document GROUP BY source_id
    UNION ALL SELECT 'open_food_facts', max(last_modified_at) FROM core.product
    UNION ALL SELECT source_id, max(day)::timestamptz FROM core.search_interest GROUP BY source_id
    UNION ALL SELECT source_id, max(observed_on)::timestamptz FROM core.external_trend GROUP BY source_id
)
SELECT s.source_id, r.last_ok_at, r.last_status, r.last_started_at, r.last_error,
       coalesce(p.pending, 0) AS pending, p.oldest_pending_at, d.data_until
FROM raw.source s
LEFT JOIN runs r USING (source_id) LEFT JOIN pending p USING (source_id) LEFT JOIN data d USING (source_id)
"""


def _age(delta: timedelta) -> str:
    h = int(delta.total_seconds() // 3600)
    return f"{h // 24} j {h % 24} h" if h >= 24 else f"{h} h {int(delta.total_seconds() % 3600 // 60)} min"


def check(conn: psycopg.Connection, settings: Settings, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rows = {r["source_id"]: r for r in conn.execute(SQL)}
    out = []
    for rule in RULES:
        r = rows.get(rule.source_id, {})
        last_ok, last_status = r.get("last_ok_at"), r.get("last_status")
        item = {
            "source_id": rule.source_id, "cadence": rule.cadence, "max_age_hours": rule.max_age.total_seconds() / 3600,
            "last_ok_at": last_ok.isoformat() if last_ok else None,
            "age_hours": round((now - last_ok).total_seconds() / 3600, 1) if last_ok else None,
            "last_status": last_status, "pending": r.get("pending", 0),
            "data_until": r["data_until"].isoformat() if r.get("data_until") else None,
        }
        if not rule.configured(settings):
            item.update(level="info", message="non configurée (clé ou compte absent dans .env)")
        elif last_ok is None:
            running = last_status == "running"
            item.update(level="warning" if running else "alert",
                        message="première collecte en cours" if running else "jamais collectée")
        elif now - last_ok > rule.max_age:
            msg = f"en retard : dernière collecte réussie il y a {_age(now - last_ok)} (attendu : {rule.cadence})"
            if last_status == "failed":
                msg += f" ; dernier essai en échec : {(r.get('last_error') or '')[:120]}"
            item.update(level="alert", message=msg)
        elif last_status == "failed":
            item.update(level="warning", message=f"dernier essai en échec, données encore récentes : {(r.get('last_error') or '')[:120]}")
        elif r.get("oldest_pending_at") and now - r["oldest_pending_at"] > CLEANING_MAX_DELAY:
            item.update(level="warning", message=f"{r['pending']} lignes en attente de nettoyage depuis plus de 6 h "
                                                 "(lancez flavortrends clean)")
        elif last_status == "partial":
            item.update(level="warning", message=f"à jour, mais la dernière collecte était partielle "
                                                 f"(il y a {_age(now - last_ok)})")
        else:
            item.update(level="ok", message=f"à jour (il y a {_age(now - last_ok)})")
        out.append(item)
    out.append(_storage(conn, settings))
    return out


def _storage(conn: psycopg.Connection, settings: Settings) -> dict:
    """Espace disque : sur Supabase gratuit, la base est limitée (500 Mo)."""
    mb = conn.execute("SELECT pg_database_size(current_database()) / 1048576.0 AS mb").fetchone()["mb"]
    item = {"source_id": "base_de_donnees", "cadence": "", "max_age_hours": None, "last_ok_at": None,
            "age_hours": None, "last_status": None, "pending": 0, "data_until": None, "size_mb": round(mb)}
    limit = settings.db_size_limit_mb
    if not limit:
        item.update(level="info", message=f"taille {mb:.0f} Mo (aucune limite définie : DB_SIZE_LIMIT_MB)")
    elif mb >= 0.95 * limit:
        item.update(level="alert", message=f"{mb:.0f} Mo sur {limit} Mo ({mb / limit:.0%}) : base presque pleine. "
                                           "Lancez flavortrends purge-raw --families all --older-than-days 7")
    elif mb >= 0.8 * limit:
        item.update(level="warning", message=f"{mb:.0f} Mo sur {limit} Mo ({mb / limit:.0%}) : à surveiller")
    else:
        item.update(level="ok", message=f"{mb:.0f} Mo sur {limit} Mo ({mb / limit:.0%})")
    return item
