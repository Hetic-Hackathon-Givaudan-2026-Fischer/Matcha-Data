"""SPIKE-2 sur données réelles : cas de référence, modèles V1 et V2 validés, fiches MiroFish, données pour l'API.

Versions (alignées sur la checklist du hackathon) :
- V1 = premier résultat (Gate 1) : règle simple « gros pic = buzz » (pic récent ≥ 1,5 × la moyenne sur 26 semaines) ;
- V2 = modèle publié pour le prototype : régression logistique sur la forme de la courbe ;
- MiroFish = simulation séparée (enrichissement), qui n'entre pas dans les scores.

Tout est calculé à partir de Supabase (Google Trends 5 ans, Open Food Facts, presse, réseaux). Rien n'est inventé.

1. CAS DE RÉFÉRENCE (étiquettes objectives)
   Pour chaque arôme et chaque date passée T0 (tous les mois), si l'arôme connaissait une VRAIE HAUSSE à T0 :
     intérêt Google Trends des 13 semaines avant T0 ≥ +20 % vs les 13 semaines précédentes
     ET ≥ +20 % vs la même période un an avant (on écarte les hausses simplement saisonnières) ;
     - variables = mesurées UNIQUEMENT avec les données avant T0 ;
     - étiquette = « pérenne » si, un an plus tard (semaines T0+39 à T0+52, même saison),
       l'arôme conserve au moins la MOITIÉ de son gain ; sinon « buzz » (la hausse s'est dissipée).

2. MODÈLE V2 : régression logistique, validée en « leave-one-flavor-out » (on retire un arôme entier,
   on entraîne sur les autres, on prédit l'arôme retiré). Comparée à deux références simples.

3. FICHES MIROFISH (Markdown) : chiffres réels, titres d'articles et de vidéos réels, points de vigilance
   calculés. Contrôles qualité avant usage.
"""
from __future__ import annotations

import csv
import json
import logging
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

from .config import ROOT
from .exports import export_orange
from .product_types import aggregate as aggregate_product_types, classify as classify_product
from .taxonomy import FlavorFinder, from_db

log = logging.getLogger(__name__)

OUT_DIR = ROOT / "data" / "sample"
RISE_THRESHOLD = 0.20      # « monte » : +20 % sur 13 semaines
YOY_THRESHOLD = 0.20       # ... et +20 % vs l'an dernier à la même période (pas une simple saison)
KEEP_GAIN = 0.50           # « pérenne » : un an après, garde au moins 50 % du gain
CUTOFF_STEP = 4            # une date T0 toutes les 4 semaines
MIN_LEVEL = 5.0            # en dessous (sur 100), Google Trends est trop bruité
FEATURES = ["croissance_13s", "croissance_52s", "volatilite_26s", "pic_ratio", "acceleration",
            "popularite_vs_ancre", "produits_marche"]          # toutes les variables calculées (exportées pour Orange)
# Variables du modèle V2 : la FORME de la courbe. Choisies parmi 10 variantes comparées en leave-one-flavor-out
# (meilleure accuracy équilibrée). Plus de variables = le modèle apprend du bruit avec seulement ~34 arômes.
MODEL_FEATURES = ["pic_ratio", "volatilite_26s", "acceleration", "croissance_13s"]
FEATURE_HELP = {
    "croissance_13s": "croissance des recherches sur 13 semaines (vs 13 semaines précédentes)",
    "croissance_52s": "croissance vs la même période un an avant (neutralise la saison)",
    "volatilite_26s": "irrégularité de la courbe sur 26 semaines (écart-type / moyenne)",
    "pic_ratio": "pic des 13 dernières semaines / moyenne sur 26 semaines (forme « coup de buzz »)",
    "acceleration": "moyenne des 4 dernières semaines / moyenne des 13 dernières",
    "popularite_vs_ancre": "niveau de recherche comparé à la vanille (terme d'ancrage)",
    "produits_marche": "produits Open Food Facts citant l'arôme et ajoutés avant la date (log)",
}
# Rayons du supermarché 3D : les 14 types de produits définis avec l'équipe Tech (voir product_types.py).


# --------------------------------------------------------------------------- chargement des séries
def load_trends(conn: psycopg.Connection) -> tuple[dict, dict]:
    """Séries hebdomadaires Google Trends par (zone, arôme) et séries de l'ancre par lot."""
    rows = conn.execute(
        """SELECT geo, term, flavor_id, batch_id, day, value FROM core.search_interest
           WHERE source_id = 'google_trends' AND batch_id LIKE 'pytrends:%%'""").fetchall()
    if not rows:
        return {}, {}
    df = pd.DataFrame(rows)
    df["day"] = pd.to_datetime(df["day"])
    # Pour chaque terme, le lot le plus long (le passage « 5 ans »)
    sizes = df.groupby(["geo", "term", "batch_id"]).size().reset_index(name="n")
    best = sizes.sort_values("n").groupby(["geo", "term"]).tail(1)
    series, anchors = {}, {}
    for r in best.itertuples():
        sub = df[(df.geo == r.geo) & (df.term == r.term) & (df.batch_id == r.batch_id)]
        s = sub.set_index("day")["value"].sort_index()
        fid = sub["flavor_id"].dropna().iloc[0] if sub["flavor_id"].notna().any() else None
        if fid:
            series[(r.geo, fid)] = (s, r.batch_id)
    for (geo, term, batch), sub in df.groupby(["geo", "term", "batch_id"]):
        if term in ("vanilla", "vanille"):
            anchors[batch] = sub.set_index("day")["value"].sort_index()
    return series, anchors


def product_dates(conn: psycopg.Connection, finder: FlavorFinder) -> tuple[dict, dict]:
    """Dates d'ajout des produits citant chaque arôme, et nombre de ces produits par type (product_types)."""
    added, type_votes = defaultdict(list), defaultdict(Counter)
    for p in conn.execute("SELECT name, generic_name, ingredients_text, categories, brand_main, countries, added_at "
                          "FROM core.product"):
        text = " ".join(x for x in (p["name"], p["generic_name"], p["ingredients_text"]) if x)
        ptype, _ = classify_product(p["categories"], p["name"])
        for fid in set(finder.find(text)):
            if p["added_at"]:
                added[fid].append(p["added_at"].date())
            if ptype:
                type_votes[fid][ptype] += 1
    return added, type_votes


# --------------------------------------------------------------------------- variables
def features_at(s: pd.Series, i: int, anchor: pd.Series | None, added: list[date]) -> dict | None:
    """Variables mesurées avec les données AVANT la position i (exclue). None si historique insuffisant."""
    if i < 65 or i > len(s):
        return None
    v = s.to_numpy(dtype=float)
    pre13, prev13, last26 = v[i - 13:i], v[i - 26:i - 13], v[i - 26:i]
    year_ago = v[i - 65:i - 52]
    if pre13.mean() < MIN_LEVEL or prev13.mean() <= 0:
        return None
    t0 = s.index[i - 1].date()
    f = {
        "croissance_13s": pre13.mean() / prev13.mean() - 1,
        "croissance_52s": (pre13.mean() / year_ago.mean() - 1) if year_ago.mean() > 0 else np.nan,
        "volatilite_26s": last26.std() / last26.mean() if last26.mean() > 0 else np.nan,
        "pic_ratio": pre13.max() / last26.mean() if last26.mean() > 0 else np.nan,
        "acceleration": v[i - 4:i].mean() / pre13.mean(),
        "popularite_vs_ancre": np.nan,
        "produits_marche": math.log1p(sum(1 for d in added if d <= t0)),
        "niveau_13s": pre13.mean(),
        "t0": t0,
    }
    if anchor is not None:
        a = anchor.reindex(s.index[i - 13:i]).to_numpy(dtype=float)
        if np.nanmean(a) > 0:
            f["popularite_vs_ancre"] = pre13.mean() / np.nanmean(a)
    return f


def model_matrix(df: pd.DataFrame, cols: list[str] = MODEL_FEATURES) -> np.ndarray:
    """Transformations : log des rapports (distributions très asymétriques), valeurs manquantes -> médiane."""
    X = df[cols].astype(float).copy()
    for c in ("croissance_13s", "croissance_52s"):
        if c in X:
            X[c] = np.log1p(X[c].clip(-0.95, 20))
    for c in ("pic_ratio", "acceleration", "popularite_vs_ancre"):
        if c in X:
            X[c] = np.log(X[c].clip(lower=0.01))
    return X.fillna(X.median()).fillna(0).to_numpy()


def build_cases(series: dict, anchors: dict, added: dict) -> pd.DataFrame:
    cases = []
    for (geo, fid), (s, batch) in series.items():
        anchor = anchors.get(batch)
        n = len(s)
        for i in range(65, n - 52 + 1, CUTOFF_STEP):
            f = features_at(s, i, anchor, added.get(fid, []))
            if (not f or f["croissance_13s"] < RISE_THRESHOLD or np.isnan(f["croissance_52s"])
                    or f["croissance_52s"] < YOY_THRESHOLD):
                continue                              # on ne garde que les VRAIES hausses à T0
            post = s.to_numpy(dtype=float)[i + 39:i + 52].mean()
            before = f["niveau_13s"] / (1 + f["croissance_13s"])        # niveau avant la hausse
            kept = (post - before) / (f["niveau_13s"] - before)          # part du gain conservée un an après
            f.update({"zone": geo, "flavor_id": fid, "niveau_un_an_apres": post, "part_gain_conservee": kept,
                      "label": "perenne" if kept >= KEEP_GAIN else "buzz"})
            cases.append(f)
    return pd.DataFrame(cases)


# --------------------------------------------------------------------------- modèle
V1_SPIKE = 1.5   # V1 : « buzz » si le pic récent dépasse 1,5 × la moyenne sur 26 semaines


def v1_verdict(pic_ratio: float | None) -> str | None:
    if pic_ratio is None or (isinstance(pic_ratio, float) and math.isnan(pic_ratio)):
        return None
    return "buzz" if pic_ratio >= V1_SPIKE else "perenne"


def train_and_validate(cases: pd.DataFrame) -> tuple[dict, dict | None, np.ndarray | None]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score,
                                 precision_score, recall_score, roc_auc_score)
    from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    y = (cases["label"] == "perenne").astype(int).to_numpy()
    groups = cases["flavor_id"].to_numpy()
    info = {"n_cases": int(len(cases)), "n_flavors": int(len(set(groups))),
            "n_perenne": int(y.sum()), "n_buzz": int(len(y) - y.sum()),
            "label_rule": f"cas = arôme en vraie hausse à T0 (≥ +{int(RISE_THRESHOLD * 100)} % sur 13 semaines ET "
                          f"≥ +{int(YOY_THRESHOLD * 100)} % vs l'an dernier) ; pérenne si, un an après (semaines +39 à +52), "
                          f"il conserve au moins {int(KEEP_GAIN * 100)} % de son gain, sinon buzz"}
    if len(cases) < 20 or y.sum() < 5 or (len(y) - y.sum()) < 5 or len(set(groups)) < 5:
        info["warning"] = "Pas assez de cas pour un modèle fiable."
        return info, None, None
    X = model_matrix(cases)
    model = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=2000))
    proba = cross_val_predict(model, X, y, groups=groups, cv=LeaveOneGroupOut(), method="predict_proba")[:, 1]
    pred = (proba >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    spike_rule = (cases["pic_ratio"].fillna(1) < V1_SPIKE).astype(int).to_numpy()   # V1 : gros pic = buzz
    majority = np.full_like(y, int(y.mean() >= 0.5))

    def summary(pred_):
        return {"accuracy": round(float(accuracy_score(y, pred_)), 3),
                "balanced_accuracy": round(float(balanced_accuracy_score(y, pred_)), 3),
                "buzz_detectes": round(float(recall_score(1 - y, 1 - pred_, zero_division=0)), 3)}
    info.update({
        "model_version": "V2",
        "model_description": "Régression logistique sur la forme de la courbe Google Trends (pic, volatilité, "
                             "accélération, croissance sur 13 semaines)",
        "v1_description": f"Règle simple : buzz si le pic récent ≥ {V1_SPIKE} × la moyenne sur 26 semaines",
        "validation": "leave-one-flavor-out (chaque arôme est prédit par un modèle qui ne l'a jamais vu)",
        "accuracy": round(float(accuracy_score(y, pred)), 3),
        "balanced_accuracy": round(float(balanced_accuracy_score(y, pred)), 3),
        "buzz_detectes": round(float(recall_score(1 - y, 1 - pred, zero_division=0)), 3),
        "precision_buzz": round(float(precision_score(1 - y, 1 - pred, zero_division=0)), 3),
        "precision_perenne": round(float(precision_score(y, pred, zero_division=0)), 3),
        "recall_perenne": round(float(recall_score(y, pred, zero_division=0)), 3),
        "f1_perenne": round(float(f1_score(y, pred, zero_division=0)), 3),
        "roc_auc": round(float(roc_auc_score(y, proba)), 3),
        "confusion_matrix": {"vrai_perenne_predit_perenne": int(tp), "vrai_buzz_predit_perenne": int(fp),
                             "vrai_perenne_predit_buzz": int(fn), "vrai_buzz_predit_buzz": int(tn)},
        "baselines": {
            "v1_regle_gros_pic": summary(spike_rule),
            "reference_toujours_perenne": summary(majority),
        },
        "lecture": "Le but métier est de repérer les buzz pour ne pas y investir : regarder balanced_accuracy et "
                   "buzz_detectes. Toujours répondre « pérenne » a une bonne accuracy mais détecte 0 buzz.",
    })
    model.fit(X, y)
    scaler, lr = model.named_steps["standardscaler"], model.named_steps["logisticregression"]
    info["features"] = MODEL_FEATURES
    info["coefficients"] = {f: round(float(c), 3) for f, c in zip(MODEL_FEATURES, lr.coef_[0])}
    info["selection_note"] = ("Variables choisies parmi 10 variantes comparées sur ces mêmes cas : le score est "
                              "probablement un peu optimiste ; à reconfirmer sur les mois à venir.")
    saved = {"features": MODEL_FEATURES, "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
             "coef": lr.coef_[0].tolist(), "intercept": float(lr.intercept_[0]),
             "medians": pd.DataFrame(model_matrix(cases), columns=MODEL_FEATURES).median().tolist()}
    return info, saved, proba


def predict_proba(saved: dict, feats: dict) -> float:
    cols = saved["features"]
    row = pd.DataFrame([{k: feats.get(k, np.nan) for k in cols}])
    x = model_matrix(row, cols)[0]
    x = np.where(np.isnan(x), saved["medians"], x)
    z = (x - np.array(saved["mean"])) / np.array(saved["scale"])
    return float(1 / (1 + math.exp(-(float(np.dot(z, saved["coef"])) + saved["intercept"]))))


# --------------------------------------------------------------------------- fiches MiroFish
def _fmt_pct(x) -> str:
    return "n.d." if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:+.0f} %"


def watch_points(cur: dict | None, ind: dict) -> list[str]:
    pts = []
    if cur:
        if cur.get("volatilite_26s", 0) > 0.5:
            pts.append(f"Courbe de recherche irrégulière (volatilité {cur['volatilite_26s']:.2f}) : risque d'effet de mode.")
        if cur.get("pic_ratio", 0) > 1.8:
            pts.append(f"Pic récent marqué (pic = {cur['pic_ratio']:.1f} × la moyenne) : forme typique d'un buzz.")
        c13, c52 = cur.get("croissance_13s"), cur.get("croissance_52s")
        if c13 is not None and c52 is not None and not math.isnan(c52) and c13 > 0.2 and c52 < 0:
            pts.append("Hausse récente mais niveau inférieur à l'an dernier à la même période : probablement saisonnier.")
    else:
        pts.append("Volume de recherche Google Trends trop faible pour mesurer une tendance fiable.")
    if ind.get("produits", 0) < 20:
        pts.append(f"Peu de produits en rayon dans notre échantillon Open Food Facts ({ind.get('produits', 0)}) : "
                   "marché encore étroit (ou arôme de niche).")
    if (ind.get("sponso") or 0) > 0.1:
        pts.append(f"{ind['sponso'] * 100:.0f} % des mentions récentes sont sponsorisées : signal en partie marketing.")
    if ind.get("mentions", 0) < 10:
        pts.append(f"Peu de mentions récentes dans la presse et les réseaux ({ind.get('mentions', 0)} sur 30 jours) : "
                   "confiance limitée.")
    pts.append("Les vues Wikipédia baissent globalement (≈ -24 % en un an) : seule la croissance relative est interprétable.")
    return pts


def build_packet(f, cur, prob, status, ind, evidence, model_info) -> str:
    perf = (f"accuracy {model_info['accuracy']:.0%}, F1 {model_info['f1_perenne']:.2f}, ROC AUC {model_info['roc_auc']:.2f} "
            f"sur {model_info['n_cases']} cas réels, validation {model_info['validation']}") if "accuracy" in model_info \
        else model_info.get("warning", "modèle non disponible")
    lines = [
        f"# Fiche tendance : {f.name_fr} ({f.name_en})",
        "",
        f"- **Identifiant** : `{f.flavor_id}`",
        f"- **Famille aromatique** : {f.family}",
        f"- **Types de produits** : " + ", ".join(
            t["label"] + (f" ({round(t['share'] * 100)} %)" if t["share"] is not None else " (d'après la famille)")
            for t in ind["types"]),
        f"- **Zone et période** : monde entier (recherches en anglais), historique Google Trends sur 5 ans ; "
        f"presse et réseaux sur les 30 derniers jours. Données au {date.today().isoformat()}.",
        "- **Origine** : données réelles collectées par le pipeline FlavorTrends. Aucune citation n'est inventée.",
        "",
        "## 1. Signaux quantitatifs",
        "",
        f"- Recherches Google (13 dernières semaines vs les 13 précédentes) : {_fmt_pct(cur.get('croissance_13s') if cur else None)}",
        f"- Recherches Google vs la même période l'an dernier : {_fmt_pct(cur.get('croissance_52s') if cur else None)}",
        f"- Irrégularité de la courbe (volatilité sur 26 semaines) : "
        f"{'n.d.' if not cur else format(cur['volatilite_26s'], '.2f')} (0 = régulière)",
        f"- Wikipédia, croissance sur 12 mois relative aux autres arômes : "
        f"{'n.d.' if ind.get('wiki_rel') is None else format(ind['wiki_rel'], '+.0f') + ' points'}",
        f"- Produits Open Food Facts citant l'arôme : {ind.get('produits', 0)} produits, {ind.get('marques', 0)} marques, "
        f"{ind.get('pays', 0)} pays (échantillon des produits récemment mis à jour, monde entier)",
        f"- Mentions sur 30 jours : {ind.get('presse', 0)} dans la presse, {ind.get('reseaux', 0)} sur les réseaux "
        f"(YouTube, Bluesky) ; {format(ind.get('yt_vues', 0), ',').replace(',', ' ')} vues YouTube",
        "",
        "## 2. Résultat statistique (modèle V2)",
        "",
        f"- **Statut** : {status}",
        f"- **Probabilité que la hausse soit durable** : {'non calculée (arôme pas en hausse)' if prob is None else f'{prob:.0%}'}",
        f"- Fiabilité du modèle : {perf}.",
        "",
        "## 3. Preuves : articles et vidéos réels (30 derniers jours)",
        "",
    ]
    lines += [f"- [{e['source']}] {e['date']} : « {e['title']} »" for e in evidence] or ["- Aucune mention récente trouvée."]
    lines += ["", "## 4. Points de vigilance (calculés à partir des données)", ""]
    lines += [f"- {p}" for p in watch_points(cur, ind)]
    lines += [
        "",
        "## 5. Question de simulation",
        "",
        f"Simuler, sur 12 mois, la réaction de quatre profils de consommateurs (jeune adulte curieux de nouveautés, "
        f"parent qui fait les courses de la semaine, consommateur attentif à la santé et au « clean label », "
        f"acheteur de la grande distribution) au lancement de produits à l'arôme **{f.name_fr}** dans le rayon "
        f"« {ind['aisle']} ». En s'appuyant sur les signaux et les points de vigilance ci-dessus, l'arôme dépasse-t-il "
        f"l'effet de curiosité des premières semaines ? Quels arguments favorisent ou freinent le réachat ?",
        "",
    ]
    return "\n".join(lines)


def check_packet(text: str) -> list[str]:
    """Contrôles qualité avant injection dans MiroFish. Liste vide = fiche valide."""
    issues = []
    if not 1500 <= len(text) <= 15000:
        issues.append(f"taille {len(text)} caractères (attendu 1 500 à 15 000)")
    for s in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5."):
        if s not in text:
            issues.append(f"section manquante : {s}")
    if "@" in text:
        issues.append("présence d'un « @ » (pseudo ou e-mail possible)")
    if "bsky.app/profile" in text:
        issues.append("lien vers un compte personnel")
    if "Points de vigilance" not in text or text.count("\n- ", text.find("## 4.")) < 1:
        issues.append("aucun point de vigilance (fiche déséquilibrée)")
    return issues


# --------------------------------------------------------------------------- orchestration
def build(conn: psycopg.Connection, out_dir: Path = OUT_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    flavors = {f.flavor_id: f for f in from_db(conn)}
    finder = FlavorFinder(list(flavors.values()))
    series, anchors = load_trends(conn)
    if not series:
        raise ValueError("Aucune donnée Google Trends automatique en base : lancez d'abord flavortrends collect google_trends")
    added, type_votes = product_dates(conn, finder)

    # 1. Cas de référence + modèle
    cases = build_cases(series, anchors, added)
    model_info, saved, cv_proba = train_and_validate(cases) if len(cases) else ({"warning": "aucun cas"}, None, None)
    cases_out = cases.copy()
    cases_out["proba_v2_validation"] = cv_proba if cv_proba is not None else np.nan   # prédit sans avoir vu l'arôme
    cases_out["verdict_v1"] = [v1_verdict(x) for x in cases_out["pic_ratio"]]
    cases_out["verdict_v2"] = ["" if np.isnan(p) else ("perenne" if p >= 0.5 else "buzz")
                               for p in cases_out["proba_v2_validation"]]
    cases_out["t0"] = cases_out["t0"].astype(str)
    with open(out_dir / "reference_cases.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["mS#flavor_id", "D#zone", "mS#t0"] + [f"C#{c}" for c in FEATURES]
                   + ["mC#niveau_13s", "mC#niveau_un_an_apres", "mC#part_gain_conservee",
                      "mC#proba_v2_validation", "mD#verdict_v1", "mD#verdict_v2", "cD#label"])
        for r in cases_out.itertuples():
            w.writerow([r.flavor_id, r.zone, r.t0] + [round(getattr(r, c), 4) if pd.notna(getattr(r, c)) else ""
                                                      for c in FEATURES]
                       + [round(r.niveau_13s, 2), round(r.niveau_un_an_apres, 2), round(r.part_gain_conservee, 3),
                          "" if np.isnan(r.proba_v2_validation) else round(r.proba_v2_validation, 3),
                          r.verdict_v1 or "", r.verdict_v2, r.label])
    (out_dir / "model_metrics.json").write_text(json.dumps(model_info, ensure_ascii=False, indent=2), encoding="utf-8")
    if saved:
        (out_dir / "model_v2.json").write_text(json.dumps(saved, indent=2), encoding="utf-8")
        (out_dir / "model_v1.json").unlink(missing_ok=True)   # ancien nom

    # 2. Indicateurs et preuves (exports Orange réutilisés)
    orange_dir = out_dir / "orange"
    export_orange(conn, orange_dir)
    ind_rows = {r["mS#arome_id"]: r for r in csv.DictReader(open(orange_dir / "aromes_indicateurs.csv", encoding="utf-8"))}
    evidence = defaultdict(list)
    for d in csv.DictReader(open(orange_dir / "documents_textes.csv", encoding="utf-8")):
        if d["D#source"] not in ("google_news", "rss", "gdelt", "youtube"):
            continue   # pas de posts de particuliers dans les fiches (RGPD)
        for fid in filter(None, d["mS#aromes_detectes"].split(",")):
            if len(evidence[fid]) < 8 and d["S#titre"]:
                evidence[fid].append({"source": d["D#source"], "date": d["mS#date"], "title": d["S#titre"][:200],
                                      "url": d["mS#url"] or None})

    def num(r, k):
        v = r.get(k, "")
        return float(v) if v not in ("", None) else None

    # 3. État actuel de chaque arôme + fiches
    packets_dir = out_dir / "mirofish_packets"
    packets_dir.mkdir(exist_ok=True)
    trends, manifest = [], []
    for fid, f in flavors.items():
        r = ind_rows.get(fid, {})
        mentions = int(num(r, "C#mentions_presse_30j") or 0) + int(num(r, "C#mentions_reseaux_30j") or 0)
        ptypes = aggregate_product_types(type_votes[fid], f.family)
        aisle = ptypes[0]["label"]
        ind = {"aisle": aisle, "types": ptypes, "wiki_rel": num(r, "C#wiki_croissance_12m_relative"),
               "produits": int(num(r, "C#produits_total") or 0), "marques": int(num(r, "C#marques_distinctes") or 0),
               "pays": int(num(r, "C#pays_distincts") or 0), "presse": int(num(r, "C#mentions_presse_30j") or 0),
               "reseaux": int(num(r, "C#mentions_reseaux_30j") or 0), "yt_vues": int(num(r, "C#youtube_vues_30j") or 0),
               "sponso": num(r, "C#part_sponsorise_30j"), "mentions": mentions}
        cur, prob, weekly = None, None, []
        if ("WORLD", fid) in series:
            s, batch = series[("WORLD", fid)]
            cur = features_at(s, len(s), anchors.get(batch), added.get(fid, []))
            weekly = [{"week": d.date().isoformat(), "value": float(v)} for d, v in s.iloc[-104:].items()]
        if cur is None:
            status = "Volume de recherche trop faible pour conclure"
        elif (cur["croissance_13s"] >= RISE_THRESHOLD and not np.isnan(cur["croissance_52s"])
              and cur["croissance_52s"] >= YOY_THRESHOLD):
            prob = predict_proba(saved, cur) if saved else None
            status = ("En hausse : probablement durable" if prob is not None and prob >= 0.6 else
                      "En hausse : probablement passager (buzz)" if prob is not None and prob <= 0.4 else
                      "En hausse : issue incertaine")
        elif cur["croissance_13s"] >= RISE_THRESHOLD:
            status = "En hausse saisonnière (niveau proche de l'an dernier)"
        elif cur["croissance_13s"] <= -RISE_THRESHOLD:
            status = "En baisse"
        else:
            status = "Stable"
        confidence = "haute" if mentions >= 50 and ind["produits"] >= 50 and cur else \
                     "moyenne" if mentions >= 10 and cur else "basse"
        packet = build_packet(f, cur, prob, status, ind, evidence[fid][:6], model_info)
        issues = check_packet(packet)
        (packets_dir / f"{fid}.md").write_text(packet, encoding="utf-8")
        manifest.append({"flavor_id": fid, "chars": len(packet), "quality_ok": not issues, "issues": issues})
        trends.append({
            "trend_id": fid, "aroma_name": f.name_fr, "aroma_name_en": f.name_en, "family": f.family,
            "category_3d_aisle": aisle, "main_product_type": ptypes[0]["id"], "product_types": ptypes,
            "status_label": status,
            "scores": {"v1_rule_verdict": v1_verdict(cur["pic_ratio"]) if prob is not None else None,
                       "v2_perennity_score": None if prob is None else round(prob * 100),
                       "mirofish_simulation_score": None, "confidence_level": confidence},
            "metrics": {
                "search_growth_13w_pct": None if not cur else round(cur["croissance_13s"] * 100, 1),
                "search_growth_52w_pct": None if not cur or math.isnan(cur["croissance_52s"]) else round(cur["croissance_52s"] * 100, 1),
                "search_volatility_26w": None if not cur else round(cur["volatilite_26s"], 3),
                "search_spike_ratio": None if not cur else round(cur["pic_ratio"], 2),
                "popularity_vs_vanilla": None if not cur or math.isnan(cur["popularite_vs_ancre"]) else round(cur["popularite_vs_ancre"], 3),
                "wikipedia_growth_12m_relative_pts": ind["wiki_rel"],
                "openfoodfacts_products_count": ind["produits"], "openfoodfacts_brands": ind["marques"],
                "openfoodfacts_countries": ind["pays"], "press_mentions_30d": ind["presse"],
                "social_mentions_30d": ind["reseaux"], "youtube_views_30d": ind["yt_vues"],
                "sponsored_share_30d": ind["sponso"], "efsa_regulatory_status": "non_verifie",
            },
            "series": {"google_trends_world_weekly": weekly},
            "evidence": evidence[fid][:6],
            "watch_points": watch_points(cur, ind),
            "mirofish": {"status": "fiche_prete" if not issues else "fiche_a_verifier",
                         "packet": f"data/sample/mirofish_packets/{fid}.md", "simulation": None},
            "data_origin": "reel",
        })
    (packets_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "model": model_info, "count": len(trends),
               "trends": sorted(trends, key=lambda t: (t["scores"]["v2_perennity_score"] is None,
                                                       -(t["scores"]["v2_perennity_score"] or 0)))}
    (out_dir / "trends_scored.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                                                encoding="utf-8")
    return {"cases": len(cases), "trends": len(trends), "packets_ok": sum(m["quality_ok"] for m in manifest),
            "model": model_info}
