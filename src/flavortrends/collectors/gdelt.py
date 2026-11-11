"""GDELT DOC 2.0 : articles de presse mondiale (gratuit, sans clé).

GDELT bloque vite une adresse IP qui envoie trop de requêtes. Pour en envoyer le moins possible,
on regroupe les arômes par 10 dans une même requête :
    ("yuzu" OR "matcha" OR kimchi ...) (boisson OR saveur OR recette ...) sourcelang:french
soit 22 requêtes pour 102 arômes en 2 langues, au lieu de 204.

Chaque article est ensuite rattaché aux arômes du groupe dont le nom apparaît dans son titre
(champ _matched_flavors). L'étape 5 (extraction) confirmera ou complétera ce rattachement.

Rythme : 1 requête toutes les 8 s, et arrêt après 2 refus consécutifs (« trop de requêtes »).
La recherche d'articles couvre environ les 3 derniers mois.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Iterator

import httpx

from ..cleaning.text import normalize_key
from ..taxonomy import Flavor
from .base import Collector, RawItem, sha1

log = logging.getLogger(__name__)

URL = "https://api.gdeltproject.org/api/v2/doc/doc"
SOURCELANG = {"fr": "french", "en": "english"}
CONTEXT = {
    "fr": "(boisson OR saveur OR recette OR dessert OR arôme OR goût)",
    "en": "(drink OR flavor OR flavour OR recipe OR dessert OR snack)",
}
GROUP_SIZE = 10


def _phrase(term: str) -> str:
    return f'"{term}"' if any(c in term for c in " -'") else term


def build_query(terms: list[str], lang: str) -> str:
    inner = " OR ".join(_phrase(t) for t in terms)
    group = f"({inner})" if len(terms) > 1 else inner
    return f"{group} {CONTEXT[lang]} sourcelang:{SOURCELANG[lang]}"


def title_matcher(flavor: Flavor) -> re.Pattern:
    """Reconnaît un arôme dans un titre : tous ses synonymes FR et EN, mots entiers, sans accents."""
    keys = {normalize_key(a) for als in flavor.aliases.values() for a in als}
    keys |= {normalize_key(flavor.name_fr), normalize_key(flavor.name_en)}
    keys = sorted((k for k in keys if k), key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(k) for k in keys) + r")\b")


class Gdelt(Collector):
    source_id = "gdelt"
    min_interval = 8.0
    backoff_min = 15.0
    backoff_max = 60.0
    max_attempts = 3
    MAX_CONSECUTIVE_429 = 2  # au-delà, GDELT bloque notre adresse IP : inutile d'insister

    def fetch(self, flavors: list[Flavor], langs: list[str], timespan: str = "3d",
              max_records: int = 250, group_size: int = GROUP_SIZE) -> Iterator[RawItem]:
        matchers = {f.flavor_id: title_matcher(f) for f in flavors}
        groups = [flavors[i:i + group_size] for i in range(0, len(flavors), group_size)]
        seen: set[str] = set()   # un article peut sortir dans deux groupes : on ne le garde qu'une fois
        blocked = 0
        n_queries = sum(1 for lang in langs if lang in SOURCELANG) * len(groups)
        log.info("[gdelt] %s requêtes (%s arômes par requête)", n_queries, group_size)
        for lang in langs:
            if lang not in SOURCELANG:
                continue
            for group in groups:
                q = build_query([f.term(lang) for f in group], lang)
                try:
                    resp = self.http.get(URL, params={
                        "query": q, "mode": "artlist", "format": "json",
                        "maxrecords": max_records, "timespan": timespan, "sort": "datedesc",
                    })
                except httpx.HTTPStatusError as exc:
                    self.errors += 1
                    if exc.response.status_code == 429:
                        blocked += 1
                        if blocked >= self.MAX_CONSECUTIVE_429:
                            log.warning("[gdelt] GDELT limite temporairement notre adresse IP (429 répétés). "
                                        "Arrêt de la source pour cette exécution ; réessayez dans quelques heures.")
                            self.truncated = True
                            return
                    log.error("[gdelt] groupe %s… : HTTP %s", group[0].flavor_id, exc.response.status_code)
                    continue
                except Exception as exc:
                    log.error("[gdelt] groupe %s… : %s", group[0].flavor_id, type(exc).__name__)
                    self.errors += 1
                    continue
                blocked = 0
                text = resp.text.strip()
                if not text:
                    continue  # aucun article
                if not text.startswith("{"):
                    # GDELT renvoie ses erreurs en texte brut avec un code 200
                    log.warning("[gdelt] requête refusée (groupe %s…) : %s", group[0].flavor_id, text[:160])
                    self.errors += 1
                    continue
                try:
                    data = json.loads(text, strict=False)
                except ValueError as exc:
                    log.error("[gdelt] JSON invalide (groupe %s…) : %s", group[0].flavor_id, exc)
                    self.errors += 1
                    continue
                articles = data.get("articles", [])
                if len(articles) >= max_records:
                    log.info("[gdelt] groupe %s… : %s articles, maximum atteint (des articles peuvent manquer)",
                             group[0].flavor_id, max_records)
                for a in articles:
                    url = a.get("url")
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    title = normalize_key(a.get("title") or "")
                    matched = [f.flavor_id for f in group if matchers[f.flavor_id].search(title)]
                    yield RawItem(external_id=sha1(url), payload={**a, "_matched_flavors": matched},
                                  query=q, flavor_id=matched[0] if matched else None)
