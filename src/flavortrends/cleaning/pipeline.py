"""Pipeline de nettoyage : lit raw.raw_document non traités, écrit dans core.*, marque les doublons."""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ..config import Settings
from ..locks import JobLock
from ..taxonomy import FlavorFinder, alias_index, from_db
from .dedup import mark_exact_duplicates, mark_near_duplicates
from .mappers import MAPPERS, Context

log = logging.getLogger(__name__)

DOC_COLS = ["source_id", "external_id", "raw_id", "doc_type", "published_at", "lang", "lang_source", "country",
            "title", "body", "text_clean", "url", "author_hash", "engagement", "query", "flavor_hint",
            "content_hash", "minhash", "is_sponsored", "quality_flags"]
DOC_SQL = f"""
INSERT INTO core.document ({", ".join(DOC_COLS)}) VALUES ({", ".join(["%s"] * len(DOC_COLS))})
ON CONFLICT (source_id, external_id) DO UPDATE SET
  {", ".join(f"{c} = EXCLUDED.{c}" for c in DOC_COLS if c not in ("source_id", "external_id"))},
  cleaned_at = now()
WHERE coalesce(core.document.raw_id, 0) < EXCLUDED.raw_id
RETURNING doc_id
"""

PRODUCT_COLS = ["code", "raw_id", "name", "generic_name", "brands", "brand_main", "categories", "ingredients_text",
                "ingredients_tags", "countries", "lang", "added_at", "last_modified_at", "quality_flags"]
PRODUCT_SQL = f"""
INSERT INTO core.product ({", ".join(PRODUCT_COLS)}) VALUES ({", ".join(["%s"] * len(PRODUCT_COLS))})
ON CONFLICT (code) DO UPDATE SET
  {", ".join(f"{c} = EXCLUDED.{c}" for c in PRODUCT_COLS if c != "code")}, cleaned_at = now()
WHERE coalesce(core.product.raw_id, 0) < EXCLUDED.raw_id
"""

INTEREST_COLS = ["source_id", "term", "geo", "day", "batch_id", "flavor_id", "value", "granularity",
                 "is_censored", "raw_id"]
INTEREST_SQL = f"""
INSERT INTO core.search_interest ({", ".join(INTEREST_COLS)}) VALUES ({", ".join(["%s"] * len(INTEREST_COLS))})
ON CONFLICT (source_id, term, geo, day, batch_id) DO UPDATE SET
  flavor_id = EXCLUDED.flavor_id, value = EXCLUDED.value, granularity = EXCLUDED.granularity,
  is_censored = EXCLUDED.is_censored, raw_id = EXCLUDED.raw_id, cleaned_at = now()
WHERE coalesce(core.search_interest.raw_id, 0) < EXCLUDED.raw_id
"""


TREND_COLS = ["source_id", "observed_on", "region", "keyword", "trend_type", "flavor_id", "rank",
              "pct_growth_wow", "pct_growth_mom", "pct_growth_yoy", "note", "url", "raw_id"]
TREND_SQL = f"""
INSERT INTO core.external_trend ({", ".join(TREND_COLS)}) VALUES ({", ".join(["%s"] * len(TREND_COLS))})
ON CONFLICT (source_id, observed_on, region, keyword, trend_type) DO UPDATE SET
  {", ".join(f"{c} = EXCLUDED.{c}" for c in TREND_COLS[5:])}, cleaned_at = now()
WHERE coalesce(core.external_trend.raw_id, 0) < EXCLUDED.raw_id
"""


def _params(rec: dict[str, Any], cols: list[str]) -> tuple:
    return tuple(Jsonb(rec[c]) if c == "engagement" else rec[c] for c in cols)


def _write_many(conn: psycopg.Connection, sql: str, cols: list[str], records: list[dict],
                failed: list[tuple[int, str]]) -> list[int]:
    """Écrit un lot ; si le lot échoue, réessaie ligne par ligne pour isoler la ligne fautive."""
    ok_raw_ids = [r["raw_id"] for r in records]
    if not records:
        return []
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.executemany(sql, [_params(r, cols) for r in records])
        return ok_raw_ids
    except psycopg.Error:
        ok_raw_ids = []
        for r in records:
            try:
                with conn.transaction():
                    conn.execute(sql, _params(r, cols))
                ok_raw_ids.append(r["raw_id"])
            except psycopg.Error as exc:
                failed.append((r["raw_id"], f"{type(exc).__name__}: {exc}".splitlines()[0][:400]))
        return ok_raw_ids


CLEAN_LOCK = "clean"


def run_cleaning(conn: psycopg.Connection, settings: Settings, source: str | None = None,
                 batch_size: int = 2000) -> Counter:
    """Nettoie les lignes brutes en attente. Un seul nettoyage à la fois (verrou PostgreSQL)."""
    ctx = Context(salt=settings.require_salt(), alias_index=alias_index(conn),
                  finder=FlavorFinder(from_db(conn)))
    lock = JobLock(conn, CLEAN_LOCK)
    if not lock.acquire():
        log.warning("Un nettoyage est déjà en cours : celui-ci est ignoré")
        return Counter({"locked": 1})
    try:
        return _clean_batches(conn, ctx, source, batch_size, lock)
    finally:
        lock.release()


def _clean_batches(conn: psycopg.Connection, ctx: Context, source: str | None, batch_size: int,
                   lock: JobLock | None = None) -> Counter:
    stats: Counter = Counter()
    while True:
        rows = conn.execute(
            """SELECT id, source_id, external_id, query, flavor_id, payload, fetched_at
               FROM raw.raw_document
               WHERE processed_at IS NULL AND (%s::text IS NULL OR source_id = %s)
               ORDER BY id LIMIT %s""",
            (source, source, batch_size),
        ).fetchall()
        if not rows:
            break

        docs, products, interests, trends = [], [], [], []
        skipped: list[tuple[int, str]] = []
        failed: list[tuple[int, str]] = []
        for row in rows:
            mapper = MAPPERS.get(row["source_id"])
            if mapper is None:
                failed.append((row["id"], f"aucun nettoyage défini pour la source {row['source_id']}"))
                continue
            try:
                m = mapper(row, ctx)
            except Exception as exc:
                failed.append((row["id"], f"{type(exc).__name__}: {exc}"[:400]))
                continue
            if m.kind == "skip":
                skipped.append((row["id"], m.reason or "ignoré"))
            elif m.kind == "document":
                docs.append(m.record)
            elif m.kind == "product":
                products.append(m.record)
            elif m.kind == "trend":
                trends.append(m.record)
            else:
                interests.append(m.record)

        ok: list[int] = []
        new_doc_ids: list[int] = []
        for rec in docs:
            try:
                with conn.transaction():
                    res = conn.execute(DOC_SQL, _params(rec, DOC_COLS)).fetchone()
                ok.append(rec["raw_id"])
                if res:
                    new_doc_ids.append(res["doc_id"])
            except psycopg.Error as exc:
                failed.append((rec["raw_id"], f"{type(exc).__name__}: {exc}".splitlines()[0][:400]))
        ok += _write_many(conn, PRODUCT_SQL, PRODUCT_COLS, products, failed)
        ok += _write_many(conn, INTEREST_SQL, INTEREST_COLS, interests, failed)
        ok += _write_many(conn, TREND_SQL, TREND_COLS, trends, failed)

        with conn.cursor() as cur:
            cur.execute("UPDATE raw.raw_document SET processed_at = now(), process_error = NULL WHERE id = ANY(%s)", (ok,))
            cur.executemany("UPDATE raw.raw_document SET processed_at = now(), process_error = %s WHERE id = %s",
                            [(f"ignoré : {reason}", rid) for rid, reason in skipped]
                            + [(f"erreur : {err}", rid) for rid, err in failed])

        stats["exact_duplicates"] += mark_exact_duplicates(conn, new_doc_ids)
        stats["near_duplicates"] += mark_near_duplicates(conn, new_doc_ids)
        conn.commit()

        if lock:
            lock.heartbeat(force=True)
        stats["raw_read"] += len(rows)
        stats["documents"] += len(docs)
        stats["products"] += len(products)
        stats["interest_points"] += len(interests)
        stats["external_trends"] += len(trends)
        stats["skipped"] += len(skipped)
        stats["errors"] += len(failed)
        for rid, err in failed[:3]:
            log.warning("raw %s en erreur : %s", rid, err)
        log.info("Lot nettoyé : %s lignes brutes, %s documents, %s produits, %s points de série, %s ignorées, %s erreurs",
                 len(rows), len(docs), len(products), len(interests), len(skipped), len(failed))
    return stats


def retry_errors(conn: psycopg.Connection, source: str | None = None) -> int:
    """Remet en file les lignes brutes en erreur (après correction du code)."""
    cur = conn.execute(
        """UPDATE raw.raw_document SET processed_at = NULL, process_error = NULL
           WHERE process_error LIKE 'erreur :%%' AND (%s::text IS NULL OR source_id = %s)""",
        (source, source),
    )
    conn.commit()
    return cur.rowcount
