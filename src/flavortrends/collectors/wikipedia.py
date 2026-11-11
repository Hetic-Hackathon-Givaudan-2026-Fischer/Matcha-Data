"""Wikipédia : vues quotidiennes des articles (API REST Wikimedia, gratuite, sans clé)."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Iterator
from urllib.parse import quote

from ..taxonomy import Flavor
from .base import Collector, RawItem

log = logging.getLogger(__name__)

PAGEVIEWS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
             "{lang}.wikipedia/all-access/user/{title}/daily/{start}/{end}")
ACTION_API = "https://{lang}.wikipedia.org/w/api.php"
DEFAULT_START = date(2016, 1, 1)
REFETCH_DAYS = 3  # on relit les derniers jours : Wikimedia complète parfois les chiffres en retard


class WikipediaPageviews(Collector):
    source_id = "wikipedia_pageviews"
    min_interval = 0.1

    def resolve_titles(self, lang: str, titles: list[str]) -> dict[str, str]:
        """Titre demandé -> titre canonique (suit normalisation et redirections). Absent si l'article n'existe pas.

        Indispensable : l'API Pageviews ne compte que les vues du titre exact, pas celles des redirections.
        """
        out: dict[str, str] = {}
        for i in range(0, len(titles), 50):
            batch = titles[i:i + 50]
            data = self.http.get(ACTION_API.format(lang=lang), params={
                "action": "query", "titles": "|".join(batch), "redirects": 1,
                "format": "json", "formatversion": 2,
            }).json()
            q = data.get("query", {})
            norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
            redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
            existing = {p["title"] for p in q.get("pages", []) if not p.get("missing") and not p.get("invalid")}
            for t in batch:
                final = norm.get(t, t)
                final = redir.get(final, final)
                if final in existing:
                    out[t] = final
        return out

    def watermark(self, lang: str, title: str) -> date | None:
        """Dernier jour déjà collecté, d'après la couche brute ET la couche propre
        (la couche brute peut avoir été purgée pour gagner de la place)."""
        row = self.conn.execute(
            """SELECT greatest(
                 (SELECT max(to_date(left(payload->>'timestamp', 8), 'YYYYMMDD')) FROM raw.raw_document
                  WHERE source_id = %s AND query = %s AND payload->>'lang' = %s),
                 (SELECT max(day) FROM core.search_interest
                  WHERE source_id = %s AND term = %s AND geo = %s)) AS last_day""",
            (self.source_id, title, lang, self.source_id, title, f"{lang}.wikipedia"),
        ).fetchone()
        if not row or not row["last_day"]:
            return None
        return row["last_day"] - timedelta(days=REFETCH_DAYS)

    def fetch(self, flavors: list[Flavor], langs: list[str], since: date | None = None,
              until: date | None = None, first_start: date = DEFAULT_START) -> Iterator[RawItem]:
        """first_start : début de l'historique au premier passage (WIKIPEDIA_START dans .env)."""
        until = until or (date.today() - timedelta(days=1))
        for lang in langs:
            wanted = {f.flavor_id: f.wiki(lang) for f in flavors if f.wiki(lang)}
            if not wanted:
                continue
            try:
                canonical = self.resolve_titles(lang, sorted(set(wanted.values())))
            except Exception as exc:
                log.error("[wikipedia] résolution des titres %s impossible : %s", lang, exc)
                self.errors += 1
                continue
            for fid, title in wanted.items():
                ct = canonical.get(title)
                if not ct:
                    log.warning("[wikipedia] article introuvable sur %s.wikipedia : « %s » (arôme %s). "
                                "Corrigez wiki_%s dans taxonomy/flavors.csv.", lang, title, fid, lang)
                    continue
                start = since or self.watermark(lang, ct) or first_start
                if start > until:
                    continue
                url = PAGEVIEWS.format(lang=lang, title=quote(ct.replace(" ", "_"), safe=""),
                                       start=start.strftime("%Y%m%d"), end=until.strftime("%Y%m%d"))
                try:
                    resp = self.http.get(url, allow_status=(404,))
                except Exception as exc:
                    log.error("[wikipedia] %s/%s : %s", lang, ct, exc)
                    self.errors += 1
                    continue
                if resp.status_code == 404:  # aucune vue sur la période
                    continue
                for it in resp.json().get("items", []):
                    day = it["timestamp"][:8]
                    yield RawItem(
                        external_id=f"{lang}:{ct}:{day}",
                        payload={"lang": lang, "article": ct, "requested_title": title,
                                 "timestamp": it["timestamp"], "views": it["views"],
                                 "agent": it.get("agent", "user"), "granularity": "daily"},
                        query=ct, flavor_id=fid,
                    )
