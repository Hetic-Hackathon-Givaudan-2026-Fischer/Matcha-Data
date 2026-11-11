"""Verrous de travaux avec battement de cœur (table raw.job_lock).

Un seul programme à la fois peut tenir un verrou donné (« collect:rss », « clean »…). Il met à jour
heartbeat_at régulièrement ; si un programme s'arrête brutalement (PC éteint, coupure réseau), son verrou
n'est plus rafraîchi et un autre programme peut le reprendre au bout de STALE_MINUTES.
"""
from __future__ import annotations

import os
import socket
import time
import uuid

import psycopg

STALE_MINUTES = 15
HEARTBEAT_EVERY = 60.0   # secondes


class JobLock:
    def __init__(self, conn: psycopg.Connection, name: str):
        self.conn = conn
        self.name = name
        self.holder = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._last_beat = 0.0
        self.held = False

    def acquire(self) -> bool:
        row = self.conn.execute(
            """INSERT INTO raw.job_lock (lock_name, holder) VALUES (%s, %s)
               ON CONFLICT (lock_name) DO UPDATE
                 SET holder = EXCLUDED.holder, acquired_at = now(), heartbeat_at = now()
                 WHERE raw.job_lock.heartbeat_at < now() - make_interval(mins => %s)
               RETURNING holder""",
            (self.name, self.holder, STALE_MINUTES),
        ).fetchone()
        self.conn.commit()
        self.held = bool(row)
        self._last_beat = time.monotonic()
        return self.held

    def heartbeat(self, force: bool = False) -> None:
        if not self.held or (not force and time.monotonic() - self._last_beat < HEARTBEAT_EVERY):
            return
        self.conn.execute("UPDATE raw.job_lock SET heartbeat_at = now() WHERE lock_name = %s AND holder = %s",
                          (self.name, self.holder))
        self.conn.commit()
        self._last_beat = time.monotonic()

    def release(self) -> None:
        if not self.held:
            return
        try:
            self.conn.rollback()
            self.conn.execute("DELETE FROM raw.job_lock WHERE lock_name = %s AND holder = %s",
                              (self.name, self.holder))
            self.conn.commit()
        except psycopg.Error:
            pass   # connexion perdue : le verrou expirera seul au bout de STALE_MINUTES
        self.held = False
