"""SPIKE-2 : règles d'étiquetage, variables sans fuite d'information, contrôles qualité, API."""
import json

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from flavortrends import api as api_module
from flavortrends.spike2 import build_cases, check_packet, features_at, predict_proba


def weekly(values):
    return pd.Series(values, index=pd.date_range("2021-11-07", periods=len(values), freq="W"), dtype=float)


def test_features_use_only_past_data():
    s = weekly([10] * 100 + [1000] * 50)                 # explosion APRÈS la position 100
    f = features_at(s, 100, None, [])
    assert f["croissance_13s"] == 0 and f["pic_ratio"] == 1   # rien de l'avenir ne fuit dans les variables


def test_labels_lasting_vs_buzz():
    # Arôme A : monte puis tient un an après -> pérenne ; arôme B : monte puis retombe -> buzz
    rising = [10] * 70 + list(np.linspace(10, 40, 20))
    lasting = weekly(rising + [40] * 70)
    buzz = weekly(rising + [8] * 70)
    cases = build_cases({("WORLD", "a"): (lasting, "b1"), ("WORLD", "b"): (buzz, "b2")}, {}, {})
    labels = cases.groupby("flavor_id")["label"].agg(set)
    assert "perenne" in labels["a"] and labels["b"] == {"buzz"}
    assert (cases["croissance_13s"] >= 0.2).all()          # seuls les arômes EN HAUSSE à T0 sont des cas


def test_predict_proba_matches_saved_model():
    saved = {"features": ["croissance_13s", "croissance_52s", "volatilite_26s", "pic_ratio", "acceleration",
                          "popularite_vs_ancre", "produits_marche"],
             "mean": [0] * 7, "scale": [1] * 7, "coef": [0] * 7, "intercept": 0.0, "medians": [0] * 7}
    assert predict_proba(saved, {"croissance_13s": 0.5}) == 0.5


def test_packet_quality_gates():
    good = "# Fiche\n" + "\n".join(f"## {i}. Section\n- point" for i in range(1, 6)) + "\nPoints de vigilance\n" + "x" * 1600
    assert check_packet(good) == []
    assert any("taille" in i for i in check_packet("## 1.\n## 2.\n## 3.\n## 4.\n## 5."))
    assert any("@" in i for i in check_packet(good + " contact @someone"))


def test_api_routes(tmp_path, monkeypatch):
    trend = {"trend_id": "yuzu", "aroma_name": "Yuzu", "category_3d_aisle": "Boissons", "status_label": "Stable",
             "scores": {"v2_perennity_score": None}, "series": {"google_trends_world_weekly": []}}
    (tmp_path / "trends_scored.json").write_text(json.dumps(
        {"generated_at": "2026-11-11T00:00:00Z", "count": 1, "model": {"accuracy": 0.7}, "trends": [trend]}),
        encoding="utf-8")
    (tmp_path / "model_v2.json").write_text(json.dumps(
        {"features": ["pic_ratio", "volatilite_26s", "acceleration", "croissance_13s"],
         "mean": [0] * 4, "scale": [1] * 4, "coef": [0] * 4, "intercept": 0.0, "medians": [0] * 4}),
        encoding="utf-8")
    (tmp_path / "mirofish_packets").mkdir()
    (tmp_path / "mirofish_packets" / "yuzu.md").write_text("# Fiche yuzu", encoding="utf-8")
    monkeypatch.setattr(api_module, "SAMPLE", tmp_path)
    api_module._data.cache_clear(); api_module._model.cache_clear()
    c = TestClient(api_module.app)
    assert c.get("/api/v1/trends?category=boisson").json()["count"] == 1
    assert "series" not in c.get("/api/v1/trends").json()["trends"][0]
    assert c.get("/api/v1/trends/yuzu").json()["aroma_name"] == "Yuzu"
    assert c.get("/api/v1/trends/inconnu").status_code == 404
    assert c.get("/api/v1/trends/yuzu/packet").text == "# Fiche yuzu"
    assert c.post("/api/v1/simulate", json={"croissance_13s": 0.4}).json()["v2_probability_perenne"] == 0.5
    api_module._data.cache_clear(); api_module._model.cache_clear()
