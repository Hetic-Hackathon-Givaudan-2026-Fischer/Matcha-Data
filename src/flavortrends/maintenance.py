"""Suivi de l'état des données et purge RGPD de la couche brute."""
from __future__ import annotations

import psycopg


def status(conn: psycopg.Connection) -> list[dict]:
    return conn.execute(
        """
        WITH raw AS (
            SELECT source_id, count(*) AS raw_rows, count(*) FILTER (WHERE processed_at IS NULL) AS pending,
                   count(*) FILTER (WHERE process_error LIKE 'erreur :%%') AS errors,
                   count(*) FILTER (WHERE process_error LIKE 'ignoré :%%') AS skipped
            FROM raw.raw_document GROUP BY source_id
        ),
        last_run AS (
            SELECT DISTINCT ON (source_id) source_id, status AS last_status, started_at AS last_run_at,
                   n_inserted AS last_inserted
            FROM raw.collection_run ORDER BY source_id, started_at DESC
        ),
        docs AS (
            SELECT source_id, count(*) AS clean_rows, count(*) FILTER (WHERE dup_of IS NOT NULL) AS duplicates,
                   count(*) FILTER (WHERE is_sponsored) AS sponsored
            FROM core.document GROUP BY source_id
            UNION ALL SELECT 'open_food_facts', count(*), 0, 0 FROM core.product
            UNION ALL SELECT source_id, count(*), 0, 0 FROM core.search_interest GROUP BY source_id
            UNION ALL SELECT source_id, count(*), 0, 0 FROM core.external_trend GROUP BY source_id
        )
        SELECT s.source_id, s.family, coalesce(r.raw_rows, 0) AS raw_rows, coalesce(r.pending, 0) AS pending,
               coalesce(r.skipped, 0) AS skipped, coalesce(r.errors, 0) AS errors,
               coalesce(d.clean_rows, 0) AS clean_rows, coalesce(d.duplicates, 0) AS duplicates,
               coalesce(d.sponsored, 0) AS sponsored, l.last_status, l.last_run_at, l.last_inserted
        FROM raw.source s
        LEFT JOIN raw r USING (source_id) LEFT JOIN last_run l USING (source_id) LEFT JOIN docs d USING (source_id)
        ORDER BY s.family, s.source_id
        """
    ).fetchall()


ALL_FAMILIES = ["social", "search", "news", "market", "science"]
PURGE_BATCH = 20_000


def purge_raw(conn: psycopg.Connection, older_than_days: int, families: list[str]) -> int:
    """Supprime de la couche brute les lignes déjà nettoyées et plus vieilles que N jours.

    Deux raisons de le faire :
    - RGPD : ne pas garder indéfiniment des posts de personnes (famille « social ») ;
    - espace disque : la couche propre garde toutes les données utiles, et le brut peut être
      re-téléchargé depuis les sources si besoin.
    Les lignes en erreur sont conservées pour pouvoir être retraitées.
    Suppression par paquets : chaque requête reste courte (Supabase coupe les requêtes trop longues).
    """
    deleted = 0
    while True:
        n = conn.execute(
            """
            DELETE FROM raw.raw_document WHERE id IN (
                SELECT r.id FROM raw.raw_document r JOIN raw.source s USING (source_id)
                WHERE s.family = ANY(%s)
                  AND r.processed_at IS NOT NULL
                  AND (r.process_error IS NULL OR r.process_error LIKE 'ignoré :%%')
                  AND r.fetched_at < now() - make_interval(days => %s)
                LIMIT %s)
            """,
            (families, older_than_days, PURGE_BATCH),
        ).rowcount
        conn.commit()
        deleted += n
        if n < PURGE_BATCH:
            return deleted


def compact_raw(database_url: str, connect_options: dict) -> None:
    """Rend au disque la place libérée par une purge (VACUUM FULL).

    Sans cela, PostgreSQL réutilise la place pour les prochaines lignes mais la taille de la base
    (celle que Supabase compte) ne baisse pas. Bloque la table brute quelques secondes à quelques minutes.
    """
    with psycopg.connect(database_url, autocommit=True, **connect_options) as c:
        c.execute("SET statement_timeout = 0")   # le compactage peut dépasser le délai par défaut de Supabase
        # La purge vide aussi le lien raw_id des lignes propres : ces tables gardent d'anciennes versions à compacter.
        for table in ("raw.raw_document", "core.search_interest", "core.product", "core.document"):
            c.execute(f"VACUUM FULL {table}")


def database_size_mb(conn: psycopg.Connection) -> float:
    return conn.execute("SELECT pg_database_size(current_database()) / 1048576.0 AS mb").fetchone()["mb"]


def table_sizes(conn: psycopg.Connection) -> list[dict]:
    return conn.execute(
        """SELECT n.nspname || '.' || c.relname AS table_name,
                  round(pg_total_relation_size(c.oid) / 1048576.0, 1) AS mb
           FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname IN ('raw', 'core') AND c.relkind = 'r'
           ORDER BY pg_total_relation_size(c.oid) DESC"""
    ).fetchall()
