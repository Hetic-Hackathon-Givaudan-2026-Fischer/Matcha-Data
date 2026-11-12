"""AI Trend Analyst : transforme les résultats Data d'un arôme en explication métier, avec un LLM local (Ollama).

Séparation stricte (aucun chiffre n'est produit par le LLM) :
1. INDICATEURS (Python, déterministe) : statut métier, taux de croissance, buzz score, trend score, confiance,
   limites des données. Calculés à partir de trends_scored.json, sans rien recalculer dans la pipeline.
2. TEXTE (LLM) : résumé, explication, facteurs, opportunité, recommandation. Le LLM reçoit les faits déjà
   rédigés en français ; sa réponse est contrainte par un schéma JSON, vérifiée, puis les indicateurs Python
   sont réinjectés (le LLM ne peut pas les modifier).
3. REPLI : si Ollama est indisponible, trop lent ou répond mal, un texte modèle est construit à partir des
   mêmes faits (generated_by = « fallback »). L'API ne tombe jamais à cause du LLM.

Inspiré du projet de référence du cours (Ollama + FastAPI, prompt système « réponds uniquement à partir des
données ») ; sans ChromaDB ni RAG : nos données sont déjà structurées, elles sont passées telles quelles.

Réglages (variables d'environnement) : OLLAMA_HOST, LLM_MODEL (qwen2.5:1.5b), LLM_TIMEOUT (secondes).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .config import ROOT

load_dotenv(ROOT / ".env")
log = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:1.5b")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "150"))
CACHE_DIR = ROOT / "data" / "sample" / "insights"
_llm_lock = threading.Lock()   # un seul appel à la fois : Ollama sur CPU sature vite

# --------------------------------------------------------------------------- 1. indicateurs (Python)
TREND_STATUSES = ("exploding", "emerging", "growing", "seasonal", "stable", "declining", "insufficient_data")
EXPLODING_SPIKE = 2.0      # pic récent ≥ 2 × la moyenne sur 26 semaines
EMERGING_MAX_PRODUCTS = 20  # en hausse mais encore peu présent en rayon

INDICATOR_DEFINITIONS = {
    "trend_status": {
        "type": "calculé (règle bêta)",
        "definition": "Dérivé du statut Data. Vraie hausse (≥ +20 % sur 3 mois ET vs l'an dernier) : "
                      f"« exploding » si le pic récent ≥ {EXPLODING_SPIKE} × la moyenne, « emerging » si moins de "
                      f"{EMERGING_MAX_PRODUCTS} produits en rayon, sinon « growing ». Sinon : seasonal, stable, "
                      "declining, ou insufficient_data (volume de recherche trop faible)."},
    "growth_rate": {
        "type": "calculé (pipeline Data)",
        "definition": "Évolution des recherches Google (monde) sur les 13 dernières semaines, en %."},
    "buzz_score": {
        "type": "bêta (rang relatif)",
        "definition": "Attention médiatique sur 30 jours, comparée aux 102 arômes : moyenne des rangs (0-100) "
                      "des mentions presse, des mentions réseaux sociaux et des vues YouTube. 80 = plus visible "
                      "que 80 % des arômes. Ce n'est pas une mesure absolue."},
    "trend_score": {
        "type": "bêta (rang relatif)",
        "definition": "Dynamique de recherche comparée aux autres arômes : moyenne des rangs (0-100) de la "
                      "croissance sur 3 mois et de la croissance vs l'an dernier. null si le volume est trop faible."},
    "perennity_score_v2": {
        "type": "calculé (modèle V2 validé)",
        "definition": "Probabilité (0-100) que la hausse tienne encore dans 1 an. N'existe que pour un arôme "
                      "en vraie hausse."},
    "confidence_level": {
        "type": "calculé (pipeline Data)",
        "definition": "Quantité de données disponibles : high = beaucoup de mentions et de produits, "
                      "low = peu de signaux."},
}


def _rank(value: float | None, population: list[float]) -> float | None:
    """Rang centile (0-100) d'une valeur dans une population (ex aequo comptés pour moitié)."""
    if value is None or not population:
        return None
    below = sum(v < value for v in population)
    equal = sum(v == value for v in population)
    return 100.0 * (below + 0.5 * equal) / len(population)


def _mean(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def trend_status(t: dict) -> tuple[str, str]:
    m, label = t["metrics"], t["status_label"]
    if label.startswith("En hausse :"):
        spike = m.get("search_spike_ratio") or 0
        products = m.get("openfoodfacts_products_count") or 0
        if spike >= EXPLODING_SPIKE:
            return "exploding", f"hausse soudaine : le pic récent atteint {spike:.1f} fois la moyenne"
        if products < EMERGING_MAX_PRODUCTS:
            return "emerging", f"recherches en hausse mais seulement {products} produits en rayon"
        return "growing", "recherches en hausse régulière, arôme déjà présent en rayon"
    if label.startswith("En hausse saisonnière"):
        return "seasonal", "hausse récente, mais au même niveau que l'an dernier à la même période"
    if label == "En baisse":
        return "declining", "recherches en baisse sur les 3 derniers mois"
    if label == "Stable":
        return "stable", "recherches stables sur les 3 derniers mois"
    return "insufficient_data", "volume de recherche trop faible pour conclure"


def compute_indicators(t: dict, population: list[dict]) -> dict:
    """Indicateurs métier d'un arôme. `population` = les 102 arômes (pour les rangs relatifs)."""
    m = t["metrics"]

    def pop(key):
        return [x["metrics"][key] for x in population if x["metrics"].get(key) is not None]

    buzz = _mean([_rank(m.get(k), pop(k)) for k in ("press_mentions_30d", "social_mentions_30d", "youtube_views_30d")])
    trend = None
    if m.get("search_growth_13w_pct") is not None:
        trend = _mean([_rank(m.get(k), pop(k)) for k in ("search_growth_13w_pct", "search_growth_52w_pct")])
    status, reason = trend_status(t)
    conf = {"haute": "high", "moyenne": "medium", "basse": "low"}.get(t["scores"]["confidence_level"], "low")
    return {
        "trend_status": status, "trend_status_reason": reason,
        "growth_rate": m.get("search_growth_13w_pct"),
        "buzz_score": None if buzz is None else round(buzz),
        "trend_score": None if trend is None else round(trend),
        "perennity_score_v2": t["scores"].get("v2_perennity_score"),
        "confidence_level": conf,
    }


def data_limitations(t: dict) -> list[str]:
    m, out = t["metrics"], []
    if m.get("search_growth_13w_pct") is None:
        out.append("Volume de recherche Google trop faible : pas de mesure fiable de la dynamique.")
    if len(t.get("series", {}).get("google_trends_world_weekly", [])) < 52:
        out.append("Historique de recherche court (moins d'un an).")
    if t["scores"].get("v2_perennity_score") is None:
        out.append("Pas de prédiction « durable ou buzz » : le modèle ne s'applique qu'aux arômes en vraie hausse.")
    if not m.get("openfoodfacts_products_count"):
        out.append("Aucun produit trouvé en rayon (Open Food Facts).")
    if (m.get("press_mentions_30d") or 0) + (m.get("social_mentions_30d") or 0) < 10:
        out.append("Peu de mentions médias et réseaux sur 30 jours : signal faible.")
    out.append("Réseaux sociaux : langue connue, pays non connu. Google Trends : accès non officiel.")
    return out


# --------------------------------------------------------------------------- 2. faits rédigés pour le LLM
STATUS_FR = {"exploding": "en forte hausse soudaine", "emerging": "en émergence", "growing": "en croissance",
             "seasonal": "en hausse saisonnière", "stable": "stable", "declining": "en baisse",
             "insufficient_data": "difficile à évaluer (trop peu de recherches)"}

# Conclusion Data par statut : le LLM l'explique, il ne la décide pas (un petit modèle se trompe de sens).
GUIDANCE = {
    "exploding": "Hausse soudaine : ce profil ressemble souvent à un buzz passager. Prudence avant d'investir ; "
                 "surveiller si l'intérêt tient dans les prochains mois.",
    "emerging": "L'intérêt des consommateurs monte avant l'arrivée en rayon : piste à explorer tôt, en veille "
                "et en prototypes.",
    "growing": "Hausse régulière appuyée par une présence en rayon : piste sérieuse pour des projets de "
               "développement.",
    "seasonal": "La hausse revient chaque année à la même période : à planifier selon la saison, ce n'est pas "
                "une tendance de fond.",
    "stable": "Pas de hausse ni de baisse marquée : arôme installé, à maintenir dans le portefeuille ; pas de "
              "signal de nouvelle tendance.",
    "declining": "L'intérêt recule : ne pas lancer de nouveau projet sans signal de reprise.",
    "insufficient_data": "Trop peu de données pour conclure : compléter la veille avant toute décision.",
}


def _pct(x: float | None) -> str:
    return "inconnu" if x is None else f"{x:+.0f} %"


def _int(x) -> str:
    return "0" if not x else f"{int(x):,}".replace(",", " ")


def facts_text(t: dict, ind: dict) -> str:
    """Faits d'un arôme en phrases simples : un petit modèle comprend mal les noms de champs techniques."""
    m = t["metrics"]
    vol = m.get("search_volatility_26w")
    vol_txt = "inconnue" if vol is None else ("faible" if vol < 0.2 else "moyenne" if vol < 0.4 else "forte")
    types = ", ".join(f"{p['label']} ({round(p['share'] * 100)} %)" if p.get("share") is not None else p["label"]
                      for p in t.get("product_types", [])) or "inconnus"
    v2 = ind["perennity_score_v2"]
    guidance = GUIDANCE[ind["trend_status"]]
    if ind["trend_status"] == "stable" and (m.get("openfoodfacts_products_count") or 0) < 50:
        guidance = ("Pas de hausse ni de baisse marquée, et peu de produits en rayon : arôme de niche, stable ; "
                    "pas de signal de nouvelle tendance.")
    if v2 is not None and v2 <= 40:
        guidance += f" Le modèle V2 donne seulement {v2}/100 de chances que la hausse dure 1 an : buzz probable."
    elif v2 is not None and v2 >= 60:
        guidance += f" Le modèle V2 donne {v2}/100 de chances que la hausse dure 1 an : tendance probablement durable."
    lines = [
        f"Arôme : {t['aroma_name']} (famille : {t['family']})",
        f"Statut calculé (à respecter) : {STATUS_FR[ind['trend_status']]} — {ind['trend_status_reason']}",
        f"Conclusion Data (à expliquer, ne pas contredire) : {guidance}",
        f"Recherches Google (monde) : {_pct(m.get('search_growth_13w_pct'))} sur 3 mois ; "
        f"{_pct(m.get('search_growth_52w_pct'))} par rapport à l'an dernier ; irrégularité de la courbe : {vol_txt}",
        "Probabilité que la hausse dure encore dans 1 an (modèle V2) : "
        + (f"{v2}/100" if v2 is not None else "non applicable (l'arôme n'est pas en vraie hausse)"),
        f"Marché : {_int(m.get('openfoodfacts_products_count'))} produits en rayon, "
        f"{_int(m.get('openfoodfacts_brands'))} marques, {_int(m.get('openfoodfacts_countries'))} pays",
        f"Types de produits où l'arôme est présent : {types}",
        f"Médias sur 30 jours : {_int(m.get('press_mentions_30d'))} articles de presse, "
        f"{_int(m.get('social_mentions_30d'))} posts sur les réseaux, {_int(m.get('youtube_views_30d'))} vues YouTube",
        "Buzz score = attention des médias comparée aux 102 arômes : "
        + ("inconnu" if ind["buzz_score"] is None else
           f"{ind['buzz_score']}/100 (plus visible que {ind['buzz_score']} % des arômes)"),
        "Trend score = dynamique des recherches comparée aux 102 arômes : "
        + ("inconnu" if ind["trend_score"] is None else
           f"{ind['trend_score']}/100 (recherches plus dynamiques que {ind['trend_score']} % des arômes)"),
        f"Fiabilité des données : {ind['confidence_level']}",
    ]
    if t.get("watch_points"):
        lines.append("Points de vigilance : " + " ; ".join(t["watch_points"]))
    titles = [e["title"] for e in t.get("evidence", [])[:3] if e.get("title")]
    if titles:
        lines.append("Titres récents (presse, YouTube) : " + " | ".join(titles))
    return "\n".join(lines)


# --------------------------------------------------------------------------- 3. prompts spécialisés
SYSTEM_PROMPT = """Tu es analyste chez Givaudan, spécialiste des tendances d'arômes, des comportements consommateurs et du marché alimentaire.
Tu expliques des données à des clients et à des équipes marketing qui ne connaissent rien à la data science.
Règles strictes :
- Utilise UNIQUEMENT les faits fournis. N'invente aucun chiffre, aucune marque, aucun pays, aucune cause.
- Reprends les chiffres exactement comme ils sont donnés.
- Ne contredis jamais le statut calculé.
- Distingue ce qui est observé dans les données de ce qui est une hypothèse ou une recommandation (écris « hypothèse : »).
- Si une donnée manque ou est « inconnue », dis-le simplement au lieu de deviner.
- Phrases courtes, vocabulaire simple, en français. Pas de jargon (pas de « volatilité », dis « irrégularité »).
- Réponds uniquement avec le JSON demandé."""

FOCUS_INSTRUCTIONS = {
    "complete": "Analyse complète : explique la dynamique actuelle de l'arôme, ce qui la justifie dans les données, "
                "puis ce que cela peut signifier pour Givaudan.",
    "trend": "Explique clairement la dynamique actuelle de cet arôme : sa direction (hausse, baisse, stable), "
             "son intensité, son évolution et son potentiel.",
    "buzz": "Analyse la popularité et l'attention médiatique. Dis si l'arôme montre un intérêt croissant, "
            "une popularité stable ou un phénomène de buzz, et explique les éléments qui le justifient.",
    "emerging": "Dis si l'arôme montre une accélération de sa popularité. Distingue une croissance régulière, "
                "une tendance émergente et une explosion soudaine. Si les données sont insuffisantes, "
                "dis que la classification est incertaine.",
    "business": "Transforme les indicateurs en informations métier : ce que cette tendance peut signifier pour "
                "Givaudan et une piste d'action concrète. Sépare observations et hypothèses.",
}

LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "trend_summary": {"type": "string", "minLength": 40, "description": "1 à 2 phrases complètes"},
        "evolution_explanation": {"type": "string", "minLength": 60, "description": "2 à 3 phrases"},
        "key_drivers": {"type": "array", "items": {"type": "string", "minLength": 10}, "minItems": 2, "maxItems": 4},
        "business_opportunity": {"type": "string", "minLength": 40, "description": "1 à 2 phrases"},
        "recommendation": {"type": "string", "minLength": 30, "description": "1 phrase d'action"},
    },
    "required": ["trend_summary", "evolution_explanation", "key_drivers", "business_opportunity", "recommendation"],
}


def build_messages(facts: str, focus: str) -> list[dict]:
    user = (f"{FOCUS_INSTRUCTIONS[focus]}\n\nFaits (seule source autorisée) :\n{facts}\n\n"
            "Remplis : trend_summary (1-2 phrases qui commencent par le nom de l'arôme et reprennent le statut "
            "calculé), evolution_explanation "
            "(2-3 phrases), key_drivers (2 à 4 facteurs ; chacun cite un chiffre des faits), business_opportunity "
            "(1-2 phrases, commence par « Hypothèse : »), recommendation (1 phrase d'action, cohérente avec la "
            "conclusion Data).\nRéponds en français uniquement.")
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


# --------------------------------------------------------------------------- 4. appel Ollama + contrôles
class LLMError(RuntimeError):
    pass


def ollama_status() -> dict:
    try:
        tags = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5).json()
        models = [m["name"] for m in tags.get("models", [])]
        return {"reachable": True, "host": OLLAMA_HOST, "model": LLM_MODEL, "model_installed": LLM_MODEL in models,
                "installed_models": models}
    except Exception as exc:
        return {"reachable": False, "host": OLLAMA_HOST, "model": LLM_MODEL, "model_installed": False,
                "error": f"{type(exc).__name__}: {exc}"}


def call_llm(messages: list[dict]) -> tuple[dict, str]:
    """Appelle Ollama ; renvoie (objet JSON, texte brut). Lève LLMError si Ollama échoue (non réessayé)."""
    payload = {"model": LLM_MODEL, "messages": messages, "stream": False, "format": LLM_SCHEMA,
               "options": {"temperature": 0.2, "num_predict": 600}}
    with _llm_lock:
        try:
            r = httpx.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=LLM_TIMEOUT)
        except httpx.TimeoutException as exc:
            raise LLMError(f"Ollama trop lent (> {LLM_TIMEOUT:.0f} s)") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama injoignable sur {OLLAMA_HOST} ({type(exc).__name__})") from exc
    if r.status_code != 200:
        raise LLMError(f"Ollama a répondu HTTP {r.status_code} : {r.text[:200]}")
    content = r.json().get("message", {}).get("content", "")
    try:
        out = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMError("Réponse du LLM qui n'est pas du JSON valide") from exc
    if not isinstance(out, dict):
        raise LLMError("Réponse du LLM qui n'est pas un objet JSON")
    return out, content


def validate_llm_output(out: dict) -> dict:
    clean = {}
    for k in ("trend_summary", "evolution_explanation", "business_opportunity", "recommendation"):
        v = out.get(k)
        if not isinstance(v, str) or len(v.strip()) < 25:
            raise LLMError(f"le champ « {k} » est vide ou trop court (une vraie phrase est attendue)")
        clean[k] = v.strip()[:900]
    drivers = out.get("key_drivers")
    if not isinstance(drivers, list) or not drivers:
        raise LLMError("Champ « key_drivers » vide ou absent dans la réponse du LLM")
    clean["key_drivers"] = [str(d).strip()[:200] for d in drivers if str(d).strip()][:4]
    return clean


_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_THOUSANDS = re.compile(r"(?<=\d)[   ](?=\d{3}\b)")   # « 50 327 » -> « 50327 »


def _numbers(s: str) -> set[str]:
    out = set()
    for n in _NUM.findall(_THOUSANDS.sub("", s)):
        n = n.replace(",", ".")
        out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out


def unsupported_numbers(text: str, facts: str) -> list[str]:
    """Nombres écrits par le LLM qui n'apparaissent pas dans les faits (contrôle anti-invention)."""
    allowed = _numbers(facts) | {"1", "2", "3", "4", "10", "12", "13", "26", "52", "100", "102", "2025", "2026"}
    return sorted(_numbers(text) - allowed, key=lambda x: float(x))


# Mots interdits dans le résumé selon le statut calculé (contradiction flagrante).
CONTRADICTIONS = {
    "exploding": ("en baisse", "recul", "stable"), "growing": ("en baisse", "recul"),
    "emerging": ("en baisse", "recul"), "declining": ("en hausse", "explos", "en croissance", "progress"),
    "stable": ("en hausse", "explos", "en baisse", "en croissance"), "seasonal": ("explos",),
    "insufficient_data": ("explos", "en hausse", "en croissance"),
}


def _language(text: str) -> str:
    try:
        from langdetect import DetectorFactory, detect
        DetectorFactory.seed = 0
        return detect(text)
    except Exception:
        return "fr"   # détection impossible : ne pas bloquer


def _all_text(text: dict) -> str:
    return " ".join([text["trend_summary"], text["evolution_explanation"], text["business_opportunity"],
                     text["recommendation"], *text["key_drivers"]])


def quality_problems(text: dict, ind: dict, facts: str, aroma_name: str | None = None,
                     aroma_name_en: str | None = None) -> list[str]:
    """Contrôles d'une réponse LLM ; liste vide = réponse acceptée. Retire au passage les facteurs sans chiffre."""
    from .cleaning.text import normalize_key
    problems = []
    if _language(_all_text(text)) != "fr":
        problems.append("la réponse n'est pas en français")
    names = [normalize_key(n) for n in (aroma_name, aroma_name_en) if n]
    if names and not any(n in normalize_key(text["trend_summary"]) for n in names):
        problems.append(f"le résumé ne nomme pas l'arôme « {aroma_name} »")
    summary = text["trend_summary"].lower()
    bad = [w for w in CONTRADICTIONS[ind["trend_status"]] if w in summary]
    if bad:
        problems.append(f"le résumé contredit le statut calculé « {STATUS_FR[ind['trend_status']]} » "
                        f"(mots : {', '.join(bad)})")
    text["key_drivers"] = [d for d in text["key_drivers"] if re.search(r"\d", d)]
    if not text["key_drivers"]:
        problems.append("aucun facteur ne cite un chiffre des faits")
    nums = unsupported_numbers(_all_text(text), facts)
    if nums:
        problems.append("chiffres absents des faits : " + ", ".join(nums))
    return problems


# --------------------------------------------------------------------------- 5. repli sans LLM
def fallback_text(t: dict, ind: dict) -> dict:
    m, name = t["metrics"], t["aroma_name"]
    drivers = [f"Recherches Google : {_pct(m.get('search_growth_13w_pct'))} sur 3 mois"]
    if m.get("openfoodfacts_products_count"):
        drivers.append(f"{_int(m['openfoodfacts_products_count'])} produits en rayon, "
                       f"{_int(m.get('openfoodfacts_brands'))} marques")
    drivers.append(f"{_int(m.get('press_mentions_30d'))} articles et {_int(m.get('social_mentions_30d'))} posts "
                   "sur 30 jours")
    reco = GUIDANCE[ind["trend_status"]]
    return {
        "trend_summary": f"{name} est {STATUS_FR[ind['trend_status']]} : {ind['trend_status_reason']}.",
        "evolution_explanation": f"Les recherches Google évoluent de {_pct(m.get('search_growth_13w_pct'))} sur 3 mois "
                                 f"et de {_pct(m.get('search_growth_52w_pct'))} par rapport à l'an dernier.",
        "key_drivers": drivers,
        "business_opportunity": "Hypothèse : à confirmer avec les équipes marketing selon les types de produits "
                                "où l'arôme est déjà présent.",
        "recommendation": reco,
    }


# --------------------------------------------------------------------------- 6. orchestration + cache
def insight(t: dict, population: list[dict], generated_at: str, focus: str = "complete",
            refresh: bool = False, use_llm: bool = True) -> dict:
    if focus not in FOCUS_INSTRUCTIONS:
        raise ValueError(f"focus inconnu : {focus} (choix : {', '.join(FOCUS_INSTRUCTIONS)})")
    cache = CACHE_DIR / f"{t['trend_id']}__{focus}.json"
    if use_llm and not refresh and cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("data_generated_at") == generated_at and cached.get("model") == LLM_MODEL:
            return {**cached, "cached": True}

    ind = compute_indicators(t, population)
    facts = facts_text(t, ind)
    text, generated_by, error, seconds, attempts = None, "fallback", None, None, 0
    if use_llm:
        t0 = time.time()
        messages = build_messages(facts, focus)
        for attempts in (1, 2):                  # 1 essai + 1 essai de correction
            try:
                out, raw = call_llm(messages)
            except LLMError as exc:
                error = str(exc)
                break                            # Ollama absent / lent : inutile de réessayer
            try:
                candidate = validate_llm_output(out)
                problems = quality_problems(candidate, ind, facts, t["aroma_name"], t.get("aroma_name_en"))
            except LLMError as exc:              # champ vide, trop court… : réessayable
                candidate, problems = None, [str(exc)]
            if not problems:
                text, generated_by, error = candidate, "llm", None
                break
            error = "Réponse du LLM rejetée : " + " ; ".join(problems)
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "Ta réponse a des problèmes : " + " ; ".join(problems)
                 + ". Corrige-les et renvoie le JSON complet, en français, en respectant le statut calculé "
                   "et en ne citant que des chiffres présents dans les faits."}]
        if error:
            log.warning("AI Trend Analyst, repli pour %s : %s", t["trend_id"], error)
        seconds = round(time.time() - t0, 1)
    if text is None:
        text = fallback_text(t, ind)
    warnings = []

    result = {
        "trend_id": t["trend_id"], "aroma_name": t["aroma_name"],
        **ind,                                  # indicateurs Python : jamais modifiés par le LLM
        **text,
        "data_limitations": data_limitations(t),
        "indicator_definitions": INDICATOR_DEFINITIONS,
        "focus": focus, "generated_by": generated_by, "model": LLM_MODEL if generated_by == "llm" else None,
        "llm_error": error, "llm_seconds": seconds, "llm_attempts": attempts, "warnings": warnings,
        "data_generated_at": generated_at, "cached": False,
    }
    if generated_by == "llm":
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({**result, "model": LLM_MODEL}, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def load_trends(path: Path = ROOT / "data" / "sample" / "trends_scored.json") -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
