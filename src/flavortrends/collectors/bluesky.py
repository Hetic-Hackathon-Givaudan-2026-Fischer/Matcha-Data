"""Bluesky : posts publics récents par arôme (AT Protocol).

La recherche demande un compte : identifiant + mot de passe d'application (gratuit).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterator

import httpx

from ..config import ConfigError
from ..taxonomy import Flavor
from .base import Collector, RawItem

log = logging.getLogger(__name__)

PDS = "https://bsky.social/xrpc"


class Bluesky(Collector):
    source_id = "bluesky"
    min_interval = 0.3

    def _token(self) -> str:
        s = self.settings
        if not (s.bluesky_handle and s.bluesky_app_password):
            raise ConfigError("BLUESKY_HANDLE ou BLUESKY_APP_PASSWORD vide dans .env : la source Bluesky est ignorée.")
        resp = self.http.post(f"{PDS}/com.atproto.server.createSession",
                              json={"identifier": s.bluesky_handle, "password": s.bluesky_app_password},
                              allow_status=(401,))
        if resp.status_code == 401:
            raise ConfigError("Bluesky refuse la connexion : vérifiez BLUESKY_HANDLE et le mot de passe d'application.")
        return resp.json()["accessJwt"]

    def fetch(self, flavors: list[Flavor], langs: list[str], days: int = 2,
              max_pages: int = 5) -> Iterator[RawItem]:
        headers = {"Authorization": f"Bearer {self._token()}"}
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        for lang in langs:
            for f in flavors:
                q = f.term(lang)
                cursor = None
                for _ in range(max_pages):
                    params = {"q": q, "lang": lang, "sort": "latest", "since": since, "limit": 100}
                    if cursor:
                        params["cursor"] = cursor
                    try:
                        data = self.http.get(f"{PDS}/app.bsky.feed.searchPosts", params=params, headers=headers).json()
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 401:  # jeton expiré : on en redemande un
                            headers = {"Authorization": f"Bearer {self._token()}"}
                            continue
                        log.error("[bluesky] %s/%s : HTTP %s", q, lang, exc.response.status_code)
                        self.errors += 1
                        break
                    except Exception as exc:
                        log.error("[bluesky] %s/%s : %s", q, lang, exc)
                        self.errors += 1
                        break
                    for p in data.get("posts", []):
                        yield RawItem(external_id=p["uri"], payload={**p, "_search_lang": lang},
                                      query=q, flavor_id=f.flavor_id)
                    cursor = data.get("cursor")
                    if not cursor or not data.get("posts"):
                        break
