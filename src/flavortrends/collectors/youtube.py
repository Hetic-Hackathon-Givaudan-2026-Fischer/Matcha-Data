"""YouTube Data API v3 : vidéos récentes par arôme, avec leurs statistiques.

Coût en quota : search.list = 100 unités, videos.list = 1 unité (quota quotidien par défaut : 10 000).
Le collecteur s'arrête proprement avant de dépasser YOUTUBE_UNIT_BUDGET.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Iterator

import httpx

from ..config import ConfigError
from ..taxonomy import Flavor
from .base import Collector, RawItem

log = logging.getLogger(__name__)

SEARCH = "https://www.googleapis.com/youtube/v3/search"
VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
COST_SEARCH, COST_VIDEOS = 100, 1
CONTEXT = {"fr": "saveur", "en": "flavor"}  # mot ajouté à la requête pour rester dans l'alimentaire


class YouTube(Collector):
    source_id = "youtube"
    min_interval = 0.2

    def fetch(self, flavors: list[Flavor], langs: list[str], days: int = 7,
              max_results: int = 50) -> Iterator[RawItem]:
        key = self.settings.youtube_api_key
        if not key:
            raise ConfigError("YOUTUBE_API_KEY est vide dans .env : la source YouTube est ignorée.")
        budget, used = self.settings.youtube_unit_budget, 0
        after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

        pairs = [(lang, f) for lang in langs for f in flavors]
        per_run = max(1, budget // (COST_SEARCH + COST_VIDEOS))
        if per_run < len(pairs):
            # Rotation : on ne commence pas toujours par les mêmes arômes. Chaque couple (langue, arôme)
            # est couvert au moins une fois tous les ceil(couples / recherches possibles) jours,
            # soit un jour sur deux avec la configuration par défaut (76 couples, 89 recherches).
            offset = (date.today().toordinal() * per_run) % len(pairs)
            pairs = pairs[offset:] + pairs[:offset]
            log.info("[youtube] budget suffisant pour %s recherches sur %s : rotation quotidienne", per_run, len(pairs))

        for lang, f in pairs:
            if used + COST_SEARCH + COST_VIDEOS > budget:
                # Arrêt prévu par la rotation : ce n'est pas une anomalie, les arômes restants passent demain.
                log.info("[youtube] budget de %s unités atteint, suite demain à partir de %s/%s", budget, f.flavor_id, lang)
                return
            q = f"{f.term(lang)} {CONTEXT.get(lang, '')}".strip()
            try:
                res = self.http.get(SEARCH, params={
                    "part": "snippet", "q": q, "type": "video", "maxResults": max_results,
                    "publishedAfter": after, "relevanceLanguage": lang, "order": "date", "key": key,
                }).json()
                used += COST_SEARCH
                ids = [it["id"]["videoId"] for it in res.get("items", []) if it.get("id", {}).get("videoId")]
                if not ids:
                    continue
                vids = self.http.get(VIDEOS, params={
                    "part": "snippet,statistics", "id": ",".join(ids), "key": key,
                }).json()
                used += COST_VIDEOS
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 403 and "quota" in exc.response.text.lower():
                    log.warning("[youtube] quota quotidien épuisé, arrêt de la collecte")
                    self.truncated = True
                    return
                log.error("[youtube] %s : HTTP %s", q, exc.response.status_code)
                self.errors += 1
                continue
            except Exception as exc:
                log.error("[youtube] %s : %s", q, type(exc).__name__)
                self.errors += 1
                continue
            for v in vids.get("items", []):
                yield RawItem(external_id=v["id"], payload={**v, "_search_lang": lang},
                              query=q, flavor_id=f.flavor_id)
        log.info("[youtube] %s unités de quota utilisées", used)
