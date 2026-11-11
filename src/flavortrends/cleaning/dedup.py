"""Détection des doublons exacts (empreinte) et des quasi-doublons (MinHash + LSH)."""
from __future__ import annotations

import logging
from datetime import timedelta

import numpy as np
import psycopg
from datasketch import MinHash, MinHashLSH

from .text import tokens

log = logging.getLogger(__name__)

NUM_PERM = 128
THRESHOLD = 0.8      # similarité de Jaccard au-dessus de laquelle deux textes sont des quasi-doublons
SHINGLE = 3          # taille des n-grammes de mots
MIN_TOKENS = 8       # en dessous, le texte est trop court pour un MinHash fiable (l'empreinte exacte suffit)
WINDOW = timedelta(days=14)


# Schéma de hachage fixé explicitement : les signatures stockées en base doivent rester relisibles.
SCHEME = "affine32"
DTYPE = "<u4"


def minhash(text: str) -> MinHash | None:
    toks = tokens(text)
    if len(toks) < MIN_TOKENS:
        return None
    m = MinHash(num_perm=NUM_PERM, seed=1, scheme=SCHEME)
    for i in range(len(toks) - SHINGLE + 1):
        m.update(" ".join(toks[i:i + SHINGLE]).encode("utf-8"))
    return m


def to_bytes(m: MinHash) -> bytes:
    return np.asarray(m.hashvalues).astype(DTYPE).tobytes()


def from_bytes(b: bytes) -> MinHash:
    return MinHash(num_perm=NUM_PERM, seed=1, scheme=SCHEME,
                   hashvalues=np.frombuffer(bytes(b), dtype=DTYPE).copy())


def mark_exact_duplicates(conn: psycopg.Connection, doc_ids: list[int]) -> int:
    """Pour chaque empreinte touchée, le document publié le plus tôt devient la référence ; les autres pointent vers lui."""
    if not doc_ids:
        return 0
    cur = conn.execute(
        """
        WITH touched AS (SELECT DISTINCT content_hash FROM core.document WHERE doc_id = ANY(%s)),
        canon AS (
            SELECT DISTINCT ON (d.content_hash) d.content_hash, d.doc_id
            FROM core.document d JOIN touched t USING (content_hash)
            ORDER BY d.content_hash, d.published_at, d.doc_id
        )
        UPDATE core.document d
        SET dup_of = c.doc_id, dup_method = 'exact'
        FROM canon c
        WHERE d.content_hash = c.content_hash AND d.doc_id <> c.doc_id
          AND (d.dup_of IS DISTINCT FROM c.doc_id OR d.dup_method IS DISTINCT FROM 'exact')
        """,
        (doc_ids,),
    )
    # La référence ne doit pas rester marquée comme doublon exact d'un autre document.
    conn.execute(
        """
        WITH touched AS (SELECT DISTINCT content_hash FROM core.document WHERE doc_id = ANY(%s)),
        canon AS (
            SELECT DISTINCT ON (d.content_hash) d.doc_id
            FROM core.document d JOIN touched t USING (content_hash)
            ORDER BY d.content_hash, d.published_at, d.doc_id
        )
        UPDATE core.document d SET dup_of = NULL, dup_method = NULL
        FROM canon c WHERE d.doc_id = c.doc_id AND d.dup_method = 'exact'
        """,
        (doc_ids,),
    )
    return cur.rowcount


def mark_near_duplicates(conn: psycopg.Connection, doc_ids: list[int]) -> int:
    """Rattache chaque nouveau document à un document antérieur très similaire (fenêtre de ±14 jours)."""
    if not doc_ids:
        return 0
    new = conn.execute(
        """SELECT doc_id, published_at, minhash FROM core.document
           WHERE doc_id = ANY(%s) AND dup_of IS NULL AND minhash IS NOT NULL
           ORDER BY published_at, doc_id""",
        (doc_ids,),
    ).fetchall()
    if not new:
        return 0
    lo = min(r["published_at"] for r in new) - WINDOW
    hi = max(r["published_at"] for r in new) + WINDOW
    pool = conn.execute(
        """SELECT doc_id, published_at, minhash FROM core.document
           WHERE dup_of IS NULL AND minhash IS NOT NULL AND published_at BETWEEN %s AND %s""",
        (lo, hi),
    ).fetchall()

    lsh = MinHashLSH(threshold=THRESHOLD, num_perm=NUM_PERM)
    sigs: dict[int, MinHash] = {}
    when: dict[int, object] = {}
    new_ids = {r["doc_id"] for r in new}
    for r in pool:
        if r["doc_id"] in new_ids:
            continue
        m = from_bytes(r["minhash"])
        sigs[r["doc_id"]] = m
        when[r["doc_id"]] = r["published_at"]
        lsh.insert(str(r["doc_id"]), m)

    marked = 0
    for r in new:
        m = from_bytes(r["minhash"])
        best = None
        for key in lsh.query(m):
            cid = int(key)
            if m.jaccard(sigs[cid]) < THRESHOLD:
                continue
            earlier = (when[cid], cid) < (r["published_at"], r["doc_id"])
            if earlier and (best is None or (when[cid], cid) < (when[best], best)):
                best = cid
        if best is not None:
            conn.execute("UPDATE core.document SET dup_of = %s, dup_method = 'near' WHERE doc_id = %s",
                         (best, r["doc_id"]))
            marked += 1
        else:
            sigs[r["doc_id"]] = m
            when[r["doc_id"]] = r["published_at"]
            lsh.insert(str(r["doc_id"]), m)
    return marked
