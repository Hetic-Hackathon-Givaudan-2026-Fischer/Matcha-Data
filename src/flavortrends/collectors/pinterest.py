"""Pinterest : tendances de recherche, très utiles pour l'alimentaire (recettes, desserts, boissons).

Deux modes :

1. PinterestManualImport (commande `import-pinterest`) : UTILISABLE TOUT DE SUITE.
   L'équipe consulte https://trends.pinterest.com chaque semaine et note les tendances alimentaires
   dans un CSV déposé dans data/manual/pinterest/. Colonnes :
       date, region, keyword                       (obligatoires)
       trend_type, rank, growth_wow_pct, growth_mom_pct, growth_yoy_pct, note, url   (facultatives)
   Séparateur virgule ou point-virgule (Excel français) ; dates AAAA-MM-JJ ou JJ/MM/AAAA.

2. PinterestTrendsApi (commande `collect pinterest`) : PRÊT, MAIS ACCÈS RÉSERVÉ.
   API officielle GET https://api.pinterest.com/v5/trends/keywords/{region}/top/{trend_type}
   réservée aux agences, grands clients et partenaires. S'active seule si PINTEREST_ACCESS_TOKEN est rempli.
   Réponse documentée : trends[].keyword, pct_growth_wow, pct_growth_mom, pct_growth_yoy, time_series
   (courbe hebdomadaire 0-100, clé = date de fin de semaine). Données du jour uniquement, 50 résultats max.
   Les valeurs autorisées pour trend_type et interests ne sont pas toutes confirmées : réglables dans .env.

Pas de scraping : interdit par les conditions d'utilisation de Pinterest.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

import httpx

from ..config import ConfigError
from .base import Collector, RawItem

log = logging.getLogger(__name__)

API = "https://api.pinterest.com/v5/trends/keywords/{region}/top/{trend_type}"
REQUIRED = ("date", "region", "keyword")
OPTIONAL_NUM = ("rank", "growth_wow_pct", "growth_mom_pct", "growth_yoy_pct")


class PinterestFormatError(ValueError):
    pass


def _date(s: str) -> date:
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise PinterestFormatError(f"date non reconnue : « {s} » (attendu AAAA-MM-JJ ou JJ/MM/AAAA)")


def _num(s: str | None) -> float | None:
    s = (s or "").strip().replace("%", "").replace(",", ".").replace("+", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        raise PinterestFormatError(f"nombre non reconnu : « {s} »") from None


def parse_manual_csv(text: str) -> list[dict]:
    """Lit le CSV de veille et renvoie une ligne propre par tendance notée."""
    first = text.splitlines()[0] if text.strip() else ""
    delimiter = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    cols = [c.strip().lower() for c in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED if c not in cols]
    if missing:
        raise PinterestFormatError(f"colonnes obligatoires manquantes : {missing} (trouvées : {cols})")
    out = []
    for i, raw in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        if not row.get("keyword"):
            continue
        try:
            item = {"observed_on": _date(row["date"]).isoformat(), "region": row["region"].upper() or "WORLD",
                    "keyword": row["keyword"].lower(), "trend_type": (row.get("trend_type") or "").lower(),
                    "note": row.get("note") or None, "url": row.get("url") or None}
            for k in OPTIONAL_NUM:
                item[k] = _num(row.get(k))
        except PinterestFormatError as exc:
            raise PinterestFormatError(f"ligne {i} : {exc}") from None
        out.append(item)
    return out


class PinterestManualImport(Collector):
    source_id = "pinterest"

    def fetch(self, paths: list[Path]) -> Iterator[RawItem]:
        for path in paths:
            try:
                rows = parse_manual_csv(path.read_bytes().decode("utf-8-sig"))
            except (PinterestFormatError, UnicodeDecodeError) as exc:
                log.error("[pinterest] %s ignoré : %s", path.name, exc)
                self.errors += 1
                continue
            log.info("[pinterest] %s : %s tendances notées", path.name, len(rows))
            for r in rows:
                yield RawItem(
                    external_id=f"manual:{r['observed_on']}:{r['region']}:{r['trend_type']}:{r['keyword']}",
                    payload={**r, "kind": "trend", "mode": "manual", "file": path.name}, query=r["keyword"])


class PinterestTrendsApi(Collector):
    source_id = "pinterest"
    min_interval = 1.0

    def fetch(self, regions: list[str], trend_types: list[str], interests: list[str],
              limit: int = 50) -> Iterator[RawItem]:
        token = self.settings.pinterest_access_token
        if not token:
            raise ConfigError("PINTEREST_ACCESS_TOKEN est vide dans .env : l'API Pinterest est ignorée.")
        today = date.today().isoformat()
        headers = {"Authorization": f"Bearer {token}"}
        for region in regions:
            for trend_type in trend_types:
                params: dict = {"limit": limit}
                if interests:
                    params["interests"] = ",".join(interests)
                try:
                    data = self.http.get(API.format(region=region, trend_type=trend_type),
                                         params=params, headers=headers).json()
                except httpx.HTTPStatusError as exc:
                    code = exc.response.status_code
                    if code in (401, 403):
                        log.warning("[pinterest] accès refusé (HTTP %s) : l'API Trends est réservée aux partenaires "
                                    "Pinterest. Utilisez la veille manuelle (import-pinterest).", code)
                        self.errors += 1
                        return
                    log.error("[pinterest] %s/%s : HTTP %s %s", region, trend_type, code, exc.response.text[:150])
                    self.errors += 1
                    continue
                except Exception as exc:
                    log.error("[pinterest] %s/%s : %s", region, trend_type, type(exc).__name__)
                    self.errors += 1
                    continue
                for rank, t in enumerate(data.get("trends", []), start=1):
                    kw = (t.get("keyword") or "").strip().lower()
                    if not kw:
                        continue
                    yield RawItem(
                        external_id=f"api:{today}:{region}:{trend_type}:{kw}",
                        payload={"kind": "trend", "mode": "api", "observed_on": today, "region": region,
                                 "keyword": kw, "trend_type": trend_type, "rank": rank,
                                 "growth_wow_pct": t.get("pct_growth_wow"), "growth_mom_pct": t.get("pct_growth_mom"),
                                 "growth_yoy_pct": t.get("pct_growth_yoy"), "note": None, "url": None},
                        query=kw)
                    # La courbe hebdomadaire va dans core.search_interest, comme Google Trends.
                    for week_end, value in (t.get("time_series") or {}).items():
                        yield RawItem(
                            external_id=f"api-ts:{today}:{region}:{kw}:{week_end}",
                            payload={"kind": "series", "term": kw, "geo": region, "week_end": week_end,
                                     "value": value, "batch_id": f"pinterest:{today}"},
                            query=kw)
