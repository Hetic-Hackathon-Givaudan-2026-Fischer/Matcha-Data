"""API Data pour l'équipe Tech (FastAPI) : sert les résultats SPIKE-2 calculés sur données réelles.

Lancement : flavortrends serve   puis   http://localhost:8000/docs   (Swagger interactif)
Les réponses sont pré-calculées (data/sample/trends_scored.json) : instantanées et sans dépendance réseau,
donc fiables en démo. Pour les rafraîchir : flavortrends spike2-build.
"""
from __future__ import annotations

import json
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .config import ROOT
from .spike2 import predict_proba

SAMPLE = ROOT / "data" / "sample"

app = FastAPI(
    title="FlavorTrends · API Data",
    description="Tendances d'arômes calculées sur données réelles (Google Trends, Open Food Facts, presse, "
                "réseaux, Wikipédia). V1 = règle simple « gros pic = buzz » (premier résultat). V2 = régression logistique "
                "validée en leave-one-flavor-out (modèle du prototype). MiroFish : simulation séparée, "
                "null tant qu'aucune simulation n'a été exécutée.",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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


@app.get("/api/v1/health", summary="État de l'API et date des données")
def health():
    d = _data()
    return {"status": "ok", "generated_at": d["generated_at"], "trends": d["count"]}


@app.get("/api/v1/trends", summary="Liste des arômes (dashboard et supermarché 3D)")
def list_trends(category: str | None = None, status: str | None = None, include_series: bool = False):
    items = _data()["trends"]
    if category:
        items = [t for t in items if category.lower() in t["category_3d_aisle"].lower()]
    if status:
        items = [t for t in items if status.lower() in t["status_label"].lower()]
    if not include_series:
        items = [{k: v for k, v in t.items() if k != "series"} for t in items]
    return {"count": len(items), "generated_at": _data()["generated_at"], "trends": items}


@app.get("/api/v1/trends/{trend_id}", summary="Fiche complète d'un arôme (rapport détaillé)")
def get_trend(trend_id: str):
    for t in _data()["trends"]:
        if t["trend_id"] == trend_id:
            return t
    raise HTTPException(404, f"Arôme inconnu : {trend_id}")


@app.get("/api/v1/trends/{trend_id}/packet", response_class=PlainTextResponse,
         summary="Fiche Markdown prête pour MiroFish")
def get_packet(trend_id: str):
    path = SAMPLE / "mirofish_packets" / f"{trend_id}.md"
    if not path.exists():
        raise HTTPException(404, f"Fiche absente : {trend_id}")
    return path.read_text(encoding="utf-8")


@app.get("/api/v1/model-metrics", summary="Validation du modèle V2, comparé à V1 (matrice de confusion, F1, comparaisons)")
def model_metrics():
    return _data()["model"]


class SimulationRequest(BaseModel):
    """Variables d'un arôme EN HAUSSE (mêmes définitions que les cas de référence)."""
    croissance_13s: float = Field(0.45, description="croissance sur 13 semaines (0.45 = +45 %)")
    croissance_52s: float | None = Field(0.30, description="vs la même période l'an dernier")
    volatilite_26s: float | None = Field(0.25, description="écart-type / moyenne sur 26 semaines")
    pic_ratio: float | None = Field(1.4, description="pic des 13 dernières semaines / moyenne sur 26")
    acceleration: float | None = Field(1.1, description="moyenne 4 semaines / moyenne 13 semaines")
    popularite_vs_ancre: float | None = Field(0.2, description="niveau de recherche / vanille")
    produits_marche: float | None = Field(3.0, description="log(1 + nombre de produits en rayon)")


@app.post("/api/v1/simulate", summary="Probabilité V2 qu'une hausse soit durable, pour des variables données")
def simulate(req: SimulationRequest):
    m = _model()
    if m is None:
        raise HTTPException(503, "Modèle V2 absent : lancez flavortrends spike2-build")
    prob = predict_proba(m, req.model_dump())
    return {"v2_probability_perenne": round(prob, 3), "verdict": "durable" if prob >= 0.6 else
            "buzz probable" if prob <= 0.4 else "incertain",
            "note": "Estimation statistique (modèle V2) ; la simulation MiroFish n'est pas exécutée par cette route."}
