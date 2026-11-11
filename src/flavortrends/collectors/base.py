"""Socle commun des collecteurs : suivi des exécutions et insertion idempotente dans raw.raw_document."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Iterator

import psycopg
from psycopg.types.json import Jsonb

from ..config import Settings
from ..http import HttpClient
from ..locks import JobLock

log = logging.getLogger(__name__)
FLUSH_EVERY = 500


@dataclass
class RawItem:
    external_id: str
    payload: dict[str, Any]
    query: str | None = None
    flavor_id: str | None = None


@dataclass
class RunResult:
    source_id: str
    run_id: int
    status: str
    n_fetched: int
    n_inserted: int
    n_errors: int
    error: str | None = None


def canonical_json(payload: dict[str, Any]) -> str:
    # PostgreSQL refuse le caractère \u0000 dans jsonb.
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).replace("\\u0000", "")


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


class Collector:
    """Un collecteur implémente fetch() qui produit des RawItem. run() s'occupe du reste."""

    source_id: str = ""
    min_interval: float = 0.0   # secondes entre deux requêtes
    backoff_min: float = 2.0    # première attente après une erreur 429/5xx
    backoff_max: float = 60.0
    max_attempts: int = 5
    flush_every: int = FLUSH_EVERY  # éléments écrits en base par paquet

    def __init__(self, conn: psycopg.Connection, settings: Settings, http: HttpClient | None = None):
        self.conn = conn
        self.settings = settings
        self.http = http or HttpClient(settings.user_agent, min_interval=self.min_interval, max_attempts=self.max_attempts,
                                       backoff_min=self.backoff_min, backoff_max=self.backoff_max)
        self.errors = 0          # erreurs partielles (une requête ratée n'arrête pas la collecte)
        self.truncated = False   # vrai si la collecte s'est arrêtée volontairement (quota)

    # À implémenter
    def fetch(self, **params: Any) -> Iterator[RawItem]:
        raise NotImplementedError

    def after_success(self, run_id: int) -> None:
        """Appelé une fois que tout ce qui a été collecté est enregistré (à surcharger si besoin)."""

    def run(self, **params: Any) -> RunResult:
        """Lance la collecte, sauf si une autre collecte de la même source tourne déjà (verrou raw.job_lock)."""
        self.lock = JobLock(self.conn, f"collect:{self.source_id}")
        if not self.lock.acquire():
            log.warning("[%s] une collecte de cette source est déjà en cours : ignorée", self.source_id)
            return RunResult(self.source_id, 0, "skipped", 0, 0, 0)
        try:
            return self._run(**params)
        finally:
            self.lock.release()

    def _run(self, **params: Any) -> RunResult:
        # Nous tenons le verrou : toute exécution encore « running » pour cette source est forcément morte
        # (PC éteint, coupure réseau). On la clôt.
        self.conn.execute(
            """UPDATE raw.collection_run SET status = 'failed', finished_at = now(),
                 error = 'exécution interrompue (processus arrêté ou connexion perdue avant la fin)'
               WHERE source_id = %s AND status = 'running'""",
            (self.source_id,),
        )
        logged = {k: v for k, v in params.items() if k != "flavors"}
        if "flavors" in params:
            logged["flavors"] = [f.flavor_id for f in params["flavors"]]
        run_id = self.conn.execute(
            "INSERT INTO raw.collection_run (source_id, params) VALUES (%s, %s) RETURNING run_id",
            (self.source_id, Jsonb(json.loads(canonical_json(logged)))),
        ).fetchone()["run_id"]
        self.conn.commit()
        log.info("[%s] début de la collecte (run %s)", self.source_id, run_id)

        fetched = inserted = 0
        buffer: list[RawItem] = []
        error: str | None = None
        try:
            for item in self.fetch(**params):
                buffer.append(item)
                fetched += 1
                if getattr(self, "lock", None):
                    self.lock.heartbeat()
                if len(buffer) >= self.flush_every:
                    inserted += self._flush(buffer, run_id)
                    buffer.clear()
            inserted += self._flush(buffer, run_id)
            self.after_success(run_id)
        except Exception as exc:  # on garde ce qui a été collecté avant l'erreur
            self.conn.rollback()
            inserted += self._flush(buffer, run_id)
            error = f"{type(exc).__name__}: {exc}"
            log.exception("[%s] collecte interrompue", self.source_id)

        status = "failed" if error else ("partial" if (self.errors or self.truncated) else "success")
        self.conn.execute(
            """UPDATE raw.collection_run SET finished_at = now(), status = %s, n_fetched = %s,
               n_inserted = %s, n_errors = %s, error = %s WHERE run_id = %s""",
            (status, fetched, inserted, self.errors + (1 if error else 0), error, run_id),
        )
        self.conn.commit()
        log.info("[%s] %s : %s éléments reçus, %s nouveaux en base, %s erreurs",
                 self.source_id, status, fetched, inserted, self.errors)
        return RunResult(self.source_id, run_id, status, fetched, inserted, self.errors, error)

    def _flush(self, items: list[RawItem], run_id: int) -> int:
        if not items:
            return 0
        payloads = [canonical_json(i.payload) for i in items]
        cur = self.conn.execute(
            """INSERT INTO raw.raw_document (source_id, external_id, run_id, query, flavor_id, payload, payload_hash)
               SELECT %s, e, %s, q, f, p::jsonb, h
               FROM unnest(%s::text[], %s::text[], %s::text[], %s::text[], %s::text[]) AS t(e, q, f, p, h)
               ON CONFLICT (source_id, external_id, payload_hash) DO NOTHING""",
            (self.source_id, run_id,
             [i.external_id for i in items], [i.query for i in items], [i.flavor_id for i in items],
             payloads, [hashlib.sha256(p.encode("utf-8")).hexdigest() for p in payloads]),
        )
        self.conn.commit()
        return cur.rowcount
