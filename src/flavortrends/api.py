"""API Data pour l'équipe Tech (FastAPI) : sert les résultats SPIKE-2 calculés sur données réelles.

Lancement : flavortrends serve   puis   http://localhost:8000/docs   (Swagger interactif)
Les réponses sont pré-calculées (data/sample/trends_scored.json) : instantanées et sans dépendance réseau,
donc fiables en démo. Pour les rafraîchir : flavortrends spike2-build.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .config import ROOT
from .spike2 import predict_proba

SAMPLE = ROOT / "data" / "sample"
log = logging.getLogger(__name__)

DESCRIPTION = """
Tendances d'arômes calculées sur **données réelles** (Google Trends, Open Food Facts, presse, réseaux, Wikipédia).

- **V1** = règle simple « gros pic = buzz » (premier résultat).
- **V2** = régression logistique validée en leave-one-flavor-out (modèle du prototype).
- **MiroFish** = simulation séparée, `null` tant qu'aucune simulation n'a été exécutée.

### Quelle route pour quoi ?
| Besoin côté Tech | Route |
|---|---|
| Vérifier que l'API répond et la date des données | `GET /api/v1/health` |
| Liste des 102 arômes (dashboard, rayons du supermarché 3D) | `GET /api/v1/trends` |
| Fiche détaillée d'un arôme (courbe, preuves, points de vigilance) | `GET /api/v1/trends/{trend_id}` |
| Fiabilité du modèle (panneau « validation ») | `GET /api/v1/model-metrics` |
| Calculatrice « et si… » (variables saisies à la main) | `POST /api/v1/simulate` |

### Erreurs
Toutes les erreurs renvoient un JSON `{"detail": "..."}`.
`404` = identifiant inconnu · `422` = paramètre invalide (détail par champ) ·
`503` = données ou modèle absents côté serveur · `500` = erreur inattendue (le champ `error` donne le type).

Les données sont recalculées chaque nuit (3 h) ; `generated_at` (UTC) indique leur date.
"""

app = FastAPI(
    title="FlavorTrends · API Data",
    description=DESCRIPTION,
    version="1.1.0",
    openapi_tags=[
        {"name": "Données", "description": "Arômes, scores et fiches (lecture seule)"},
        {"name": "Modèle", "description": "Validation du modèle V2 et simulation"},
        {"name": "Système", "description": "État de l'API"},
    ],
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------- schémas (documentation Swagger)
# Ils décrivent les réponses sans les filtrer : les routes renvoient les données telles quelles.

class ErrorResponse(BaseModel):
    detail: str = Field(..., examples=["Arôme inconnu : pitaya"])
    error: str | None = Field(None, description="Type d'exception (erreurs 500 uniquement)")


class Health(BaseModel):
    status: Literal["ok"]
    generated_at: str = Field(..., description="Date de calcul des données (ISO 8601, UTC)",
                              examples=["2026-11-12T05:27:22+00:00"])
    trends: int = Field(..., description="Nombre d'arômes disponibles", examples=[102])


class Scores(BaseModel):
    v1_rule_verdict: Literal["buzz", "perenne"] | None = Field(
        None, description="V1 : « buzz » si pic ≥ 1,5 × la moyenne. null si l'arôme n'est pas en vraie hausse")
    v2_perennity_score: int | None = Field(
        None, ge=0, le=100, description="V2 : probabilité (0-100) que la hausse soit durable. null hors hausse")
    mirofish_simulation_score: int | None = Field(None, description="Toujours null (simulation non exécutée)")
    confidence_level: Literal["haute", "moyenne", "basse"]


class Metrics(BaseModel):
    search_growth_13w_pct: float | None = Field(None, description="Croissance Google Trends sur 13 semaines (%)")
    search_growth_52w_pct: float | None = Field(None, description="Croissance vs la même période l'an dernier (%)")
    search_volatility_26w: float | None = Field(None, description="Écart-type / moyenne sur 26 semaines")
    search_spike_ratio: float | None = Field(None, description="Pic des 13 dernières semaines / moyenne sur 26")
    popularity_vs_vanilla: float | None = Field(None, description="Obsolète, souvent null")
    wikipedia_growth_12m_relative_pts: float | None = Field(
        None, description="Croissance Wikipédia sur 12 mois, en points au-dessus de la médiane des arômes")
    openfoodfacts_products_count: int | None = Field(None, description="Produits en rayon citant l'arôme")
    openfoodfacts_brands: int | None = None
    openfoodfacts_countries: int | None = None
    press_mentions_30d: int | None = None
    social_mentions_30d: int | None = None
    youtube_views_30d: int | None = None
    sponsored_share_30d: float | None = Field(None, description="Part de contenus sponsorisés (0-1)")
    efsa_regulatory_status: str | None = Field(None, examples=["non_verifie"])


class SeriesPoint(BaseModel):
    week: str = Field(..., examples=["2024-11-10"])
    value: float | None = Field(None, description="Indice Google Trends (0-100)")


class Series(BaseModel):
    google_trends_world_weekly: list[SeriesPoint] = Field(..., description="104 semaines, monde")


class Evidence(BaseModel):
    source: str = Field(..., examples=["google_news"])
    date: str | None = Field(None, examples=["2026-11-12"])
    title: str | None = None
    url: str | None = None


class MiroFish(BaseModel):
    status: str = Field(..., examples=["fiche_prete"])
    packet: str | None = Field(None, description="Chemin de la fiche ; contenu via /trends/{id}/packet")
    simulation: dict | None = None


PRODUCT_TYPE_IDS = Literal["desserts-lactes", "produits-laitiers", "boissons", "glaces", "confiseries", "chocolats",
                           "biscuits", "viennoiseries", "cereales", "snacks", "sauces", "plats", "vegetal",
                           "nutrition"]


class ProductType(BaseModel):
    id: PRODUCT_TYPE_IDS = Field(..., examples=["boissons"])
    label: str = Field(..., examples=["Boissons"])
    products: int = Field(..., description="Produits Open Food Facts de ce type qui citent l'arôme")
    share: float | None = Field(None, description="Part des produits de l'arôme (0-1) ; null si basis = famille")
    basis: Literal["produits", "famille"] = Field(
        ..., description="« produits » = calculé sur les vrais produits ; « famille » = aucun produit, "
                         "type déduit de la famille de l'arôme")


class TrendSummary(BaseModel):
    trend_id: str = Field(..., examples=["matcha"])
    aroma_name: str = Field(..., examples=["Matcha"])
    aroma_name_en: str
    family: str = Field(..., examples=["herbace"])
    category_3d_aisle: str = Field(..., description="Libellé du type principal (= product_types[0].label)",
                                   examples=["Boissons"])
    main_product_type: PRODUCT_TYPE_IDS = Field(..., description="Identifiant du type principal (rayon 3D)")
    product_types: list[ProductType] = Field(
        ..., description="Types de produits associés, du plus fréquent au moins fréquent : tout type qui pèse "
                         "au moins 10 % des produits de l'arôme (et 2 produits), toujours au moins un")
    status_label: str = Field(..., examples=["Stable", "En hausse : probablement passager (buzz)", "En baisse",
                                              "En hausse saisonnière (niveau proche de l'an dernier)",
                                              "Volume de recherche trop faible pour conclure"])
    scores: Scores
    metrics: Metrics
    evidence: list[Evidence] = Field(..., description="Jusqu'à 6 titres réels récents (presse, YouTube)")
    watch_points: list[str] = Field(..., description="Points de vigilance en français")
    mirofish: MiroFish
    data_origin: Literal["reel"]


class Trend(TrendSummary):
    series: Series


class TrendList(BaseModel):
    count: int
    generated_at: str
    trends: list[TrendSummary] = Field(..., description="Avec include_series=true, chaque arôme a aussi `series`")


class ModelMetrics(BaseModel):
    model_version: str = Field(..., examples=["V2"])
    n_cases: int
    n_flavors: int
    n_perenne: int
    n_buzz: int
    validation: str
    accuracy: float
    balanced_accuracy: float
    buzz_detectes: float
    precision_buzz: float
    roc_auc: float | None = None
    confusion_matrix: dict[str, int]
    baselines: dict[str, dict[str, float]] = Field(..., description="v1_regle_gros_pic, reference_toujours_perenne")
    features: list[str]
    coefficients: dict[str, float]


class SimulationResponse(BaseModel):
    v2_probability_perenne: float = Field(..., ge=0, le=1, examples=[0.42])
    verdict: Literal["durable", "buzz probable", "incertain"]
    note: str


ERR_404 = {404: {"model": ErrorResponse, "description": "Identifiant inconnu"}}
ERR_503 = {503: {"model": ErrorResponse, "description": "Données ou modèle absents (lancer flavortrends spike2-build)"}}
ERR_500 = {500: {"model": ErrorResponse, "description": "Erreur inattendue"}}


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    """Erreur imprévue : JSON lisible au lieu d'un texte brut, et trace complète dans le terminal de l'API."""
    log.exception("Erreur sur %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"Erreur interne : {exc}",
                                                  "error": type(exc).__name__})


@lru_cache(maxsize=1)
def _data() -> dict:
    path = SAMPLE / "trends_scored.json"
    if not path.exists():
        raise HTTPException(503, "Données absentes : lancez flavortrends spike2-build")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _model() -> dict | None:
    path = SAMPLE / "model_v2.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@app.get("/api/v1/health", summary="État de l'API et date des données", tags=["Système"],
         responses={200: {"model": Health}, **ERR_503, **ERR_500})
def health():
    d = _data()
    return {"status": "ok", "generated_at": d["generated_at"], "trends": d["count"]}


@app.get("/api/v1/trends", summary="Liste des arômes (dashboard et supermarché 3D)", tags=["Données"],
         description="Route principale pour le front. Filtres optionnels, insensibles à la casse : "
                     "`category` = identifiant d'un des 14 types de produits (ex. `glaces`, `desserts-lactes`) ; "
                     "renvoie les arômes associés à ce type (principal ou secondaire). "
                     "`status` = partie du statut (ex. `buzz`, `stable`). "
                     "`include_series=true` ajoute la courbe de 104 semaines à chaque arôme (réponse plus lourde).",
         responses={200: {"model": TrendList}, **ERR_503, **ERR_500})
def list_trends(category: str | None = None, status: str | None = None, include_series: bool = False):
    items = _data()["trends"]
    if category:
        c = category.lower()
        items = [t for t in items
                 if any(c == pt["id"] or c in pt["label"].lower() for pt in t.get("product_types", []))
                 or c in t["category_3d_aisle"].lower()]
    if status:
        items = [t for t in items if status.lower() in t["status_label"].lower()]
    if not include_series:
        items = [{k: v for k, v in t.items() if k != "series"} for t in items]
    return {"count": len(items), "generated_at": _data()["generated_at"], "trends": items}


class ProductTypeCount(BaseModel):
    id: PRODUCT_TYPE_IDS
    label: str
    flavors_main: int = Field(..., description="Arômes dont c'est le type principal")
    flavors_any: int = Field(..., description="Arômes associés à ce type (principal ou secondaire)")


@app.get("/api/v1/product-types", summary="Les 14 types de produits (rayons 3D) et leur nombre d'arômes",
         tags=["Données"], responses={200: {"model": list[ProductTypeCount]}, **ERR_503, **ERR_500})
def product_types():
    from .product_types import PRODUCT_TYPES
    trends = _data()["trends"]
    return [{"id": tid, "label": label,
             "flavors_main": sum(t.get("main_product_type") == tid for t in trends),
             "flavors_any": sum(any(pt["id"] == tid for pt in t.get("product_types", [])) for t in trends)}
            for tid, label, _, _ in PRODUCT_TYPES]


@app.get("/api/v1/trends/{trend_id}", summary="Fiche complète d'un arôme (rapport détaillé)", tags=["Données"],
         description="`trend_id` = identifiant anglais en minuscules, tel que renvoyé par /trends "
                     "(ex. `matcha`, `curry`, `dragon_fruit`). Inclut la courbe Google Trends.",
         responses={200: {"model": Trend}, **ERR_404, **ERR_503, **ERR_500})
def get_trend(trend_id: str):
    for t in _data()["trends"]:
        if t["trend_id"] == trend_id:
            return t
    raise HTTPException(404, f"Arôme inconnu : {trend_id}")


@app.get("/api/v1/trends/{trend_id}/packet", response_class=PlainTextResponse,
         summary="Fiche Markdown prête pour MiroFish", tags=["Données"],
         responses={200: {"content": {"text/plain": {}}, "description": "Fiche au format Markdown"},
                    **ERR_404, **ERR_500})
def get_packet(trend_id: str):
    path = SAMPLE / "mirofish_packets" / f"{trend_id}.md"
    if not path.exists():
        raise HTTPException(404, f"Fiche absente : {trend_id}")
    return path.read_text(encoding="utf-8")


@app.get("/api/v1/model-metrics", summary="Validation du modèle V2, comparé à V1 (matrice de confusion, F1, comparaisons)",
         tags=["Modèle"], responses={200: {"model": ModelMetrics}, **ERR_503, **ERR_500})
def model_metrics():
    return _data()["model"]


class SimulationRequest(BaseModel):
    """Variables d'un arôme EN HAUSSE (mêmes définitions que les cas de référence)."""
    croissance_13s: float = Field(0.45, description="croissance sur 13 semaines (0.45 = +45 %)")
    croissance_52s: float | None = Field(0.30, description="vs la même période l'an dernier")
    volatilite_26s: float | None = Field(0.25, description="écart-type / moyenne sur 26 semaines")
    pic_ratio: float | None = Field(1.4, description="pic des 13 dernières semaines / moyenne sur 26")
    acceleration: float | None = Field(1.1, description="moyenne 4 semaines / moyenne 13 semaines")
    popularite_vs_ancre: float | None = Field(0.2, description="non utilisé par V2 (conservé pour compatibilité)")
    produits_marche: float | None = Field(3.0, description="non utilisé par V2 (conservé pour compatibilité)")


@app.post("/api/v1/simulate", summary="Probabilité V2 qu'une hausse soit durable, pour des variables données",
          tags=["Modèle"],
          description="Calculatrice « et si… » : ne renvoie PAS les données des arômes (pour ça : GET /api/v1/trends). "
                      "V2 n'utilise que pic_ratio, volatilite_26s, acceleration et croissance_13s. "
                      "Verdict : durable si probabilité ≥ 0,6 ; buzz probable si ≤ 0,4 ; sinon incertain.",
          responses={200: {"model": SimulationResponse}, **ERR_503, **ERR_500})
def simulate(req: SimulationRequest):
    m = _model()
    if m is None:
        raise HTTPException(503, "Modèle V2 absent : lancez flavortrends spike2-build")
    prob = predict_proba(m, req.model_dump())
    return {"v2_probability_perenne": round(prob, 3), "verdict": "durable" if prob >= 0.6 else
            "buzz probable" if prob <= 0.4 else "incertain",
            "note": "Estimation statistique (modèle V2) ; la simulation MiroFish n'est pas exécutée par cette route."}
