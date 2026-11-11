"""Import des exports CSV manuels de Google Trends.

Pourquoi manuel : pytrends est archivé (avril 2025) et l'API officielle est en alpha sur candidature.
Méthode : sur trends.google.com, comparez jusqu'à 5 termes dont un terme d'ancrage commun
(ex. « vanille »), puis téléchargez « Intérêt au fil du temps » en CSV dans data/manual/google_trends/.
Chaque fichier forme un lot (batch) : ses valeurs 0-100 ne sont comparables qu'entre elles.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

from .base import Collector, RawItem

log = logging.getLogger(__name__)

HEADER_FIRST = {"week", "day", "month", "time", "date", "semaine", "jour", "mois", "temps", "heure"}
COLUMN_RE = re.compile(r"^(?P<term>.+?):\s*\((?P<geo>[^)]*)\)\s*$")
DATE_FORMATS = ["%Y-%m-%d", "%Y-%m", "%d/%m/%Y", "%m/%d/%Y", "%b %d, %Y", "%Y-%m-%dT%H"]


class TrendsFormatError(ValueError):
    pass


def _parse_date(s: str) -> date:
    s = s.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise TrendsFormatError(f"format de date non reconnu : « {s} »")


def _granularity(days: list[date]) -> str:
    if len(days) < 2:
        return "week"
    gap = (days[1] - days[0]).days
    return "day" if gap <= 1 else ("week" if gap <= 7 else "month")


def parse_trends_csv(text: str) -> list[dict]:
    rows = list(csv.reader(io.StringIO(text)))
    header_idx = next((i for i, r in enumerate(rows) if r and r[0].strip().lower() in HEADER_FIRST), None)
    if header_idx is None:
        raise TrendsFormatError("en-tête introuvable : le fichier n'est pas un export « Intérêt au fil du temps »")
    header = rows[header_idx]
    columns = []
    for col in header[1:]:
        m = COLUMN_RE.match(col.strip())
        columns.append((m["term"].strip(), m["geo"].strip()) if m else (col.strip(), ""))
    data_rows = [r for r in rows[header_idx + 1:] if r and r[0].strip()]
    days = [_parse_date(r[0]) for r in data_rows]
    gran = _granularity(days)
    terms = [t for t, _ in columns]
    out = []
    for d, r in zip(days, data_rows):
        for (term, geo), raw in zip(columns, r[1:]):
            v = raw.strip()
            if v == "":
                continue
            censored = v.startswith("<")
            value = 0.5 if censored else float(v.replace(",", "."))
            out.append({"term": term, "geo": geo, "date": d.isoformat(), "value": value,
                        "value_raw": v, "censored": censored, "granularity": gran, "terms_in_batch": terms})
    return out


def build_plan(flavors, lang: str, anchor_id: str, per_batch: int = 4) -> list[list[str]]:
    """Découpe les arômes en comparaisons de 4 termes + 1 terme d'ancrage commun (Google Trends en accepte 5)."""
    anchor = next((f for f in flavors if f.flavor_id == anchor_id), None)
    if anchor is None:
        raise ValueError(f"terme d'ancrage inconnu : {anchor_id}")
    others = [f.term(lang) for f in flavors if f.flavor_id != anchor_id]
    return [others[i:i + per_batch] + [anchor.term(lang)] for i in range(0, len(others), per_batch)]


def build_popularity_plan(flavors, lang: str, popularity: dict[str, float], per_batch: int = 5) -> list[list[str]]:
    """Groupe les arômes de popularité proche (5 par requête, sans terme d'ancrage).

    Google Trends ramène chaque requête sur 0-100 par rapport au terme le plus recherché : un arôme de niche
    mis avec un arôme très populaire (la vanille) tombe à 0-2 et devient inutilisable. En groupant des arômes
    de popularité voisine, chacun garde une résolution suffisante pour mesurer la FORME de sa courbe.
    """
    ordered = sorted(flavors, key=lambda f: popularity.get(f.flavor_id, 0.0), reverse=True)
    terms = [f.term(lang) for f in ordered]
    return [terms[i:i + per_batch] for i in range(0, len(terms), per_batch)]


def explore_url(terms: list[str], geo: str, lang: str, period: str = "today 5-y") -> str:
    q = ",".join(quote(t) for t in terms)
    return f"https://trends.google.com/trends/explore?date={quote(period)}&geo={geo}&q={q}&hl={lang}"


class GoogleTrendsAuto(Collector):
    """Collecte automatique via pytrends (bibliothèque NON officielle, archivée en 2025).

    - Une fois par semaine (le collecteur ne fait rien si la dernière collecte auto a moins de 6 jours).
    - Par zone (ex. monde en anglais, France en français) : arômes groupés par 5 de POPULARITÉ VOISINE
      (d'après leurs vues Wikipédia), pour que les arômes de niche (yuzu, hojicha…) ne soient pas écrasés à 0.
    - Premier passage d'une zone : 5 ans d'historique hebdomadaire. Ensuite : seulement les dernières semaines
      (économie de place sur Supabase).
    - Une requête toutes les 10 s ; arrêt après 2 refus « trop de requêtes » consécutifs.
    Si Google bloque, l'import manuel des CSV (import-trends) reste disponible.
    """

    source_id = "google_trends"
    min_interval = 10.0
    KEEP_WEEKS_AFTER_FIRST = 8

    def _recent_auto_run(self, days: int = 6) -> bool:
        row = self.conn.execute(
            """SELECT 1 FROM raw.collection_run WHERE source_id = %s AND params->>'mode' = 'auto'
               AND status = 'success' AND finished_at > now() - make_interval(days => %s) LIMIT 1""",
            (self.source_id, days)).fetchone()
        return bool(row)

    def _weeks_per_term(self, zone: str) -> dict[str, int]:
        """Nombre de semaines déjà en base par terme : un terme sans historique recevra ses 5 ans."""
        rows = self.conn.execute(
            """SELECT term, count(DISTINCT day) AS n FROM core.search_interest
               WHERE source_id = %s AND geo = %s AND batch_id LIKE 'pytrends:%%' GROUP BY term""",
            (self.source_id, zone)).fetchall()
        return {r["term"]: r["n"] for r in rows}

    def fetch(self, flavors, zones: list[tuple[str, str]], anchor: str | None = None,
              popularity: dict[str, float] | None = None, force: bool = False, mode: str = "auto",
              trend_req=None) -> Iterator[RawItem]:
        """anchor : un terme commun à chaque lot (méthode « ancre ») ; sinon, lots par popularité voisine."""
        if not force and self._recent_auto_run():
            log.info("[google_trends] collecte automatique déjà faite il y a moins de 6 jours : rien à faire")
            return
        if trend_req is None:
            from pytrends.request import TrendReq
            trend_req = TrendReq(hl="en-US", tz=0, timeout=(10, 30), retries=0)
        today = date.today().isoformat()
        blocked = 0
        for zone, lang in zones:
            plan = build_plan(flavors, lang, anchor) if anchor else build_popularity_plan(flavors, lang, popularity or {})
            history = self._weeks_per_term(zone)
            log.info("[google_trends] zone %s (%s) : %s requêtes (%s termes ont déjà leur historique)",
                     zone, lang, len(plan), sum(1 for n in history.values() if n >= 100))
            for i, terms in enumerate(plan):
                self.http._throttle()   # même rythme que les autres collecteurs
                try:
                    trend_req.build_payload(terms, timeframe="today 5-y", geo="" if zone == "WORLD" else zone)
                    df = trend_req.interest_over_time()
                except Exception as exc:
                    self.errors += 1
                    if "429" in str(exc) or type(exc).__name__ == "TooManyRequestsError":
                        blocked += 1
                        if blocked >= 2:
                            log.warning("[google_trends] Google limite nos requêtes (429 répétés) : arrêt. "
                                        "Réessayez plus tard, ou utilisez l'import manuel (import-trends).")
                            self.truncated = True
                            return
                    log.error("[google_trends] %s lot %s : %s", zone, i, str(exc)[:150])
                    continue
                blocked = 0
                if df is None or df.empty:
                    continue
                batch = f"pytrends:{zone}:{today}:{'a' if anchor else 'p'}{i:02d}"
                keep_all = any(history.get(t, 0) < 100 for t in terms)   # un terme du lot sans 5 ans d'historique
                dates = list(df.index)
                if not keep_all:
                    dates = dates[-self.KEEP_WEEKS_AFTER_FIRST:]
                for d in dates:
                    row = df.loc[d]
                    if bool(row.get("isPartial", False)):
                        continue   # semaine en cours, incomplète : elle sera collectée la semaine prochaine
                    day = d.date().isoformat()
                    for term in terms:
                        yield RawItem(
                            external_id=f"{batch}:{term}:{day}",
                            payload={"term": term, "geo": zone, "date": day, "value": float(row[term]),
                                     "value_raw": str(int(row[term])), "censored": False, "granularity": "week",
                                     "terms_in_batch": terms, "batch_id": batch, "mode": "auto", "anchor": anchor,
                                     "grouping": "anchor" if anchor else "popularity"},
                            query=term)


class GoogleTrendsImport(Collector):
    source_id = "google_trends"

    def fetch(self, paths: list[Path]) -> Iterator[RawItem]:
        for path in paths:
            content = path.read_bytes()
            batch = hashlib.sha1(content).hexdigest()[:12]
            try:
                rows = parse_trends_csv(content.decode("utf-8-sig"))
            except (TrendsFormatError, UnicodeDecodeError) as exc:
                log.error("[google_trends] %s ignoré : %s", path.name, exc)
                self.errors += 1
                continue
            log.info("[google_trends] %s : %s valeurs (lot %s)", path.name, len(rows), batch)
            for r in rows:
                yield RawItem(external_id=f"{batch}:{r['term']}:{r['geo']}:{r['date']}",
                              payload={**r, "file": path.name, "batch_id": batch}, query=r["term"])
