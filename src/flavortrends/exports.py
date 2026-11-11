"""Exports CSV pour Orange Data Mining (exploration, regroupements, textes, modèles V1/V2).

Orange lit directement ces fichiers avec le widget « File ». L'en-tête utilise le format simplifié
d'Orange : « D#nom » = variable discrète, « C#nom » = continue, « S#nom » = texte, préfixe « m » = méta
(affichée mais pas utilisée par les modèles).

Fichiers produits (dans data/exports/) :
1. aromes_indicateurs.csv   une ligne par arôme : indicateurs calculés sur les vraies données
2. aromes_courbes_wikipedia.csv   une ligne par arôme, une colonne par semaine (forme de la courbe)
3. documents_textes.csv     articles, posts et vidéos des 90 derniers jours, avec les arômes détectés
"""
from __future__ import annotations

import csv
import logging
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import psycopg

from .config import ROOT
from .taxonomy import FlavorFinder, from_db

log = logging.getLogger(__name__)
DEFAULT_DIR = ROOT / "data" / "exports"


def _pct(new: float | None, old: float | None) -> float | None:
    if not new or not old:
        return None
    return round((new / old - 1) * 100, 1)


def _write(path: Path, header: list[str], rows: list[list]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])
    return len(rows)


def export_orange(conn: psycopg.Connection, out_dir: Path = DEFAULT_DIR) -> dict[str, int]:
    flavors = from_db(conn)
    finder = FlavorFinder(flavors)
    today = date.today()

    # --- Wikipédia : volumes, croissances, volatilité, courbe hebdomadaire
    wiki = {r["flavor_id"]: r for r in conn.execute(
        """SELECT flavor_id,
                  sum(value) FILTER (WHERE day > current_date - 30)  AS v30,
                  sum(value) FILTER (WHERE day > current_date - 90)  AS v90,
                  sum(value) FILTER (WHERE day <= current_date - 90  AND day > current_date - 180) AS v90_prev,
                  sum(value) FILTER (WHERE day > current_date - 365) AS v365,
                  sum(value) FILTER (WHERE day <= current_date - 365 AND day > current_date - 730) AS v365_prev
           FROM core.search_interest
           WHERE source_id = 'wikipedia_pageviews' AND flavor_id IS NOT NULL GROUP BY flavor_id""")}
    weekly: dict[str, dict[date, float]] = defaultdict(dict)
    for r in conn.execute(
            """SELECT flavor_id, date_trunc('week', day)::date AS w, sum(value) AS v
               FROM core.search_interest
               WHERE source_id = 'wikipedia_pageviews' AND flavor_id IS NOT NULL
                 AND day > current_date - 728 AND day < date_trunc('week', current_date)
               GROUP BY 1, 2"""):
        weekly[r["flavor_id"]][r["w"]] = float(r["v"])

    def volatility(fid: str) -> float | None:
        pts = [v for w, v in weekly.get(fid, {}).items() if w > today - timedelta(weeks=26)]
        if len(pts) < 8:
            return None
        m = sum(pts) / len(pts)
        sd = (sum((x - m) ** 2 for x in pts) / len(pts)) ** 0.5
        return round(sd / m, 3) if m else None

    # --- Produits Open Food Facts : rattachés aux arômes par le dictionnaire de synonymes
    prod_n, prod_new12, prod_prev12 = Counter(), Counter(), Counter()
    brands, countries = defaultdict(set), defaultdict(set)
    for p in conn.execute("SELECT name, generic_name, ingredients_text, brand_main, countries, added_at FROM core.product"):
        for fid in set(finder.find(" ".join(x for x in (p["name"], p["generic_name"], p["ingredients_text"]) if x))):
            prod_n[fid] += 1
            if p["brand_main"]:
                brands[fid].add(p["brand_main"])
            countries[fid].update(p["countries"] or [])
            if p["added_at"]:
                age = (today - p["added_at"].date()).days
                if age <= 365:
                    prod_new12[fid] += 1
                elif age <= 730:
                    prod_prev12[fid] += 1

    # --- Documents des 90 derniers jours : arômes détectés dans le texte (pas seulement le mot cherché)
    doc_rows, news30, social30, sponso30, yt_views30, likes30 = [], Counter(), Counter(), Counter(), Counter(), Counter()
    for d in conn.execute(
            """SELECT d.source_id, s.family, d.doc_type, d.lang, d.published_at, d.title, d.text_clean, d.url,
                      d.engagement, d.is_sponsored
               FROM core.document d JOIN raw.source s USING (source_id)
               WHERE d.dup_of IS NULL AND d.published_at > now() - interval '90 days'
               ORDER BY d.published_at DESC"""):
        found = sorted(set(finder.find(d["text_clean"])))
        recent = d["published_at"].date() > today - timedelta(days=30)
        eng = d["engagement"] or {}
        for fid in found:
            if recent:
                (news30 if d["family"] == "news" else social30)[fid] += 1
                sponso30[fid] += int(d["is_sponsored"])
                yt_views30[fid] += int(eng.get("views") or 0) if d["source_id"] == "youtube" else 0
                likes30[fid] += int(eng.get("likes") or 0)
        url = d["url"] if d["family"] != "social" else None   # pas de lien vers des comptes de personnes
        doc_rows.append([d["source_id"], d["family"], d["doc_type"], d["lang"] or "", d["published_at"].date(),
                         ",".join(found), len(found), int(d["is_sponsored"]), (d["title"] or "")[:300],
                         (d["text_clean"] or "")[:1000], url])

    pin = Counter({r["flavor_id"]: r["n"] for r in conn.execute(
        """SELECT flavor_id, count(*) AS n FROM core.external_trend
           WHERE flavor_id IS NOT NULL AND observed_on > current_date - 30 GROUP BY 1""")})

    # --- 1. Indicateurs par arôme
    ind_header = ["mS#arome_id", "mS#arome", "D#famille",
                  "C#wiki_vues_30j", "C#wiki_croissance_3m_pct", "C#wiki_croissance_12m_pct",
                  "C#wiki_croissance_3m_relative", "C#wiki_croissance_12m_relative", "C#wiki_volatilite_26s",
                  "C#produits_total", "C#produits_nouveaux_12m", "C#produits_croissance_12m_pct",
                  "C#marques_distinctes", "C#pays_distincts",
                  "C#mentions_presse_30j", "C#mentions_reseaux_30j", "C#youtube_vues_30j", "C#likes_30j",
                  "C#part_sponsorise_30j", "C#pinterest_tendances_30j"]
    # Le trafic de Wikipédia baisse globalement : on compare chaque arôme à la médiane de tous les arômes.
    def median(xs):
        xs = sorted(x for x in xs if x is not None)
        return xs[len(xs) // 2] if xs else None
    g3 = {fid: _pct(w.get("v90"), w.get("v90_prev")) for fid, w in wiki.items()}
    g12 = {fid: _pct(w.get("v365"), w.get("v365_prev")) for fid, w in wiki.items()}
    m3, m12 = median(g3.values()), median(g12.values())

    def rel(g, m):
        return round(g - m, 1) if g is not None and m is not None else None

    ind_rows = []
    for f in flavors:
        w = wiki.get(f.flavor_id, {})
        mentions = news30[f.flavor_id] + social30[f.flavor_id]
        ind_rows.append([
            f.flavor_id, f.name_fr, f.family,
            w.get("v30"), g3.get(f.flavor_id), g12.get(f.flavor_id),
            rel(g3.get(f.flavor_id), m3), rel(g12.get(f.flavor_id), m12), volatility(f.flavor_id),
            prod_n[f.flavor_id], prod_new12[f.flavor_id], _pct(prod_new12[f.flavor_id], prod_prev12[f.flavor_id]),
            len(brands[f.flavor_id]), len(countries[f.flavor_id]),
            news30[f.flavor_id], social30[f.flavor_id], yt_views30[f.flavor_id], likes30[f.flavor_id],
            round(sponso30[f.flavor_id] / mentions, 3) if mentions else None, pin[f.flavor_id],
        ])
    counts = {"aromes_indicateurs.csv": _write(out_dir / "aromes_indicateurs.csv", ind_header, ind_rows)}

    # --- 2. Courbes Wikipédia : valeur hebdomadaire / moyenne de l'arôme (on compare des FORMES, pas des volumes)
    weeks = sorted({wk for s in weekly.values() for wk in s})
    curve_rows = []
    for f in flavors:
        s = weekly.get(f.flavor_id)
        if not s:
            continue
        m = sum(s.values()) / len(s)
        curve_rows.append([f.flavor_id, f.name_fr, f.family] +
                          [round(s.get(wk, 0) / m, 3) if m else None for wk in weeks])
    counts["aromes_courbes_wikipedia.csv"] = _write(
        out_dir / "aromes_courbes_wikipedia.csv",
        ["mS#arome_id", "mS#arome", "D#famille"] + [f"C#{wk.isoformat()}" for wk in weeks], curve_rows)

    # --- 3. Textes, pour l'add-on Text d'Orange (nuage de mots, sentiment, thèmes)
    counts["documents_textes.csv"] = _write(
        out_dir / "documents_textes.csv",
        ["D#source", "D#famille_source", "D#type", "D#langue", "mS#date", "mS#aromes_detectes",
         "C#nb_aromes", "D#sponsorise", "S#titre", "S#texte", "mS#url"], doc_rows)
    return counts
