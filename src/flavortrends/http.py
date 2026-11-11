"""Client HTTP commun : User-Agent, limitation de débit et reprises automatiques."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


def _short(exc: BaseException | None) -> str:
    """Message court, sans l'URL (qui peut contenir une clé d'API)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__ if exc else ""


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in RETRY_STATUS


class HttpClient:
    """Enveloppe httpx.

    min_interval : délai minimum entre deux requêtes (respect des quotas).
    allow_status : codes HTTP renvoyés tels quels au lieu de lever une erreur (ex. 404).
    """

    def __init__(self, user_agent: str, min_interval: float = 0.0, timeout: float = 30.0,
                 max_attempts: int = 5, backoff_min: float = 2.0, backoff_max: float = 60.0,
                 transport: httpx.BaseTransport | None = None):
        self.client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"},
            timeout=timeout, follow_redirects=True, transport=transport,
        )
        self.min_interval = min_interval
        self.max_attempts = max_attempts
        self.backoff_min = backoff_min
        self.backoff_max = backoff_max
        self._last = 0.0

    def _wait(self, rs) -> float:
        """Attente avant nouvelle tentative : en-tête Retry-After s'il existe, sinon délai exponentiel."""
        exc = rs.outcome.exception()
        if isinstance(exc, httpx.HTTPStatusError):
            ra = exc.response.headers.get("Retry-After", "")
            if ra.isdigit():
                return min(float(ra), self.backoff_max)
        return min(self.backoff_max, self.backoff_min * 2 ** (rs.attempt_number - 1))

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def request(self, method: str, url: str, *, allow_status: tuple[int, ...] = (), **kwargs: Any) -> httpx.Response:
        retrying = Retrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=self._wait,
            retry=retry_if_exception(_retryable),
            reraise=True,
            before_sleep=lambda rs: log.warning("%s : nouvelle tentative dans %.0f s (%s)", httpx.URL(url).host,
                                                rs.upcoming_sleep, _short(rs.outcome.exception())),
        )
        for attempt in retrying:
            with attempt:
                self._throttle()
                resp = self.client.request(method, url, **kwargs)
                if resp.status_code in allow_status:
                    return resp
                resp.raise_for_status()
                return resp
        raise AssertionError("inaccessible")  # pragma: no cover

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        self.client.close()
