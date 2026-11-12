import pytest

from flavortrends import analyst


def trend(fid="x", status="Stable", growth=10.0, spike=1.2, products=100, press=5, social=20, yt=1000, v2=None):
    return {
        "trend_id": fid, "aroma_name": fid.title(), "family": "epice", "status_label": status,
        "scores": {"v2_perennity_score": v2, "confidence_level": "moyenne"},
        "metrics": {"search_growth_13w_pct": growth, "search_growth_52w_pct": growth, "search_volatility_26w": 0.3,
                    "search_spike_ratio": spike, "openfoodfacts_products_count": products,
                    "openfoodfacts_brands": 10, "openfoodfacts_countries": 5, "press_mentions_30d": press,
                    "social_mentions_30d": social, "youtube_views_30d": yt},
        "product_types": [{"label": "Boissons", "share": 0.6}], "watch_points": [], "evidence": [],
        "series": {"google_trends_world_weekly": [{"week": "w", "value": 1}] * 104},
    }


@pytest.mark.parametrize("status,spike,products,expected", [
    ("En hausse : probablement passager (buzz)", 3.8, 361, "exploding"),
    ("En hausse : issue incertaine", 1.3, 5, "emerging"),
    ("En hausse : probablement durable", 1.3, 200, "growing"),
    ("En hausse saisonnière (niveau proche de l'an dernier)", 1.3, 200, "seasonal"),
    ("En baisse", 1.0, 200, "declining"),
    ("Stable", 1.0, 200, "stable"),
    ("Volume de recherche trop faible pour conclure", None, 0, "insufficient_data"),
])
def test_trend_status(status, spike, products, expected):
    assert analyst.trend_status(trend(status=status, spike=spike, products=products))[0] == expected


def test_indicateurs_rangs_relatifs():
    pop = [trend("a", press=0, social=0, yt=0, growth=-10), trend("b", press=5, social=5, yt=5, growth=0),
           trend("c", press=50, social=500, yt=10**6, growth=40)]
    top = analyst.compute_indicators(pop[2], pop)
    low = analyst.compute_indicators(pop[0], pop)
    assert top["buzz_score"] > low["buzz_score"] and top["trend_score"] > low["trend_score"]
    assert top["growth_rate"] == 40 and top["confidence_level"] == "medium"
    faible = trend("d", growth=None)
    assert analyst.compute_indicators(faible, pop + [faible])["trend_score"] is None


def test_controle_anti_invention():
    facts = "Recherches : +27 % sur 3 mois ; 50 327 vues YouTube ; pic 3.8 fois"
    assert analyst.unsupported_numbers("Hausse de 27 %, 50 327 vues, pic de 3,8.", facts) == []
    assert analyst.unsupported_numbers("Hausse de 45 % en 2024.", facts) == ["45", "2024"]


def test_controles_qualite():
    ind = {"trend_status": "stable"}
    facts = "Recherches : -10 % sur 3 mois ; 361 produits"
    ok = {"trend_summary": "La vanille reste stable sur les trois derniers mois.",
          "evolution_explanation": "Les recherches varient peu.", "key_drivers": ["361 produits en rayon", "sans chiffre"],
          "business_opportunity": "Hypothèse : arôme installé.", "recommendation": "Maintenir le portefeuille."}
    assert analyst.quality_problems(dict(ok), ind, facts) == []
    contradiction = {**ok, "trend_summary": "La vanille est actuellement en hausse, portée par les réseaux."}
    assert any("contredit" in p for p in analyst.quality_problems(contradiction, ind, facts))
    anglais = {**ok, "trend_summary": "Stable, but with slight fluctuations in the market.",
               "evolution_explanation": "The trend is stable, but there are slight fluctuations in the market.",
               "business_opportunity": "Given the stable trend there is an opportunity.",
               "recommendation": "Givaudan should continue to focus on developing new products."}
    assert any("français" in p for p in analyst.quality_problems(anglais, ind, facts))
    invente = {**ok, "key_drivers": ["45 % de hausse"]}
    assert any("45" in p for p in analyst.quality_problems(invente, ind, facts))


def test_validation_reponse_llm():
    ok = {"trend_summary": "Un résumé suffisamment long pour passer.",
          "evolution_explanation": "Une explication suffisamment longue pour passer.",
          "key_drivers": ["a", "b", "c", "d", "e"], "business_opportunity": "Une opportunité suffisamment longue.",
          "recommendation": "Une recommandation suffisamment longue."}
    assert len(analyst.validate_llm_output(ok)["key_drivers"]) == 4
    for court in ("", "Stable"):
        with pytest.raises(analyst.LLMError):
            analyst.validate_llm_output({**ok, "trend_summary": court})


def test_repli_si_ollama_injoignable(monkeypatch, tmp_path):
    monkeypatch.setattr(analyst, "OLLAMA_HOST", "http://127.0.0.1:9")    # port fermé
    monkeypatch.setattr(analyst, "CACHE_DIR", tmp_path)
    t = trend("curry", status="En hausse : probablement passager (buzz)", spike=3.8, v2=13)
    r = analyst.insight(t, [t], "2026-11-12", refresh=True)
    assert r["generated_by"] == "fallback" and "injoignable" in r["llm_error"]
    assert r["trend_status"] == "exploding" and r["perennity_score_v2"] == 13
    assert r["trend_summary"] and r["recommendation"] and r["data_limitations"]
    assert not list(tmp_path.iterdir())          # un repli n'est pas mis en cache


def test_routes_api_sans_llm(monkeypatch):
    from fastapi.testclient import TestClient

    from flavortrends import api
    t = trend("curry", status="En hausse : probablement passager (buzz)", spike=3.8, v2=13)
    t.update({"category_3d_aisle": "Boissons", "main_product_type": "boissons"})
    monkeypatch.setattr(api, "_data", lambda: {"generated_at": "2026-11-12", "count": 1, "trends": [t]})
    c = TestClient(api.app)
    ind = c.get("/api/v1/ai/indicators").json()
    assert ind[0]["trend_status"] == "exploding"
    r = c.get("/api/v1/trends/curry/insight?use_llm=false").json()
    assert r["generated_by"] == "fallback" and r["trend_status"] == "exploding"
    assert c.get("/api/v1/trends/inconnu/insight").status_code == 404
    assert c.get("/api/v1/trends/curry/insight?focus=nimporte").status_code == 422
