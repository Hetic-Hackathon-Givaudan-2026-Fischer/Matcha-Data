from collections import Counter

from flavortrends.product_types import LABELS, PRODUCT_TYPES, aggregate, classify


def test_les_14_types_du_front():
    assert [t[0] for t in PRODUCT_TYPES] == [
        "nutrition", "glaces", "vegetal", "produits-laitiers", "desserts-lactes", "biscuits", "viennoiseries",
        "cereales", "chocolats", "confiseries", "snacks", "sauces", "plats", "boissons"]
    assert len(LABELS) == 14


def test_categorie_exacte_et_piege_plant_based():
    # « plant-based-foods-and-beverages » ne doit pas faire d'un biscuit une boisson
    assert classify(["en:plant-based-foods-and-beverages", "en:biscuits"]) == ("biscuits", "categorie")
    assert classify(["en:plant-based-foods-and-beverages"]) == (None, None)


def test_le_plus_precis_gagne():
    assert classify(["en:dairies", "en:yogurts", "en:non-dairy-yogurts"])[0] == "vegetal"
    assert classify(["en:chocolates", "en:chocolate-biscuits", "en:biscuits"])[0] == "biscuits"
    assert classify(["en:beverages", "en:dairy-drinks"])[0] == "produits-laitiers"


def test_repli_sur_le_nom():
    assert classify([], "Matcha Latte") == ("boissons", "nom")
    assert classify(None, "Milk Chocolate Almonds")[0] == "chocolats"     # pas « produits laitiers »
    assert classify([], "Pumpkin Spice Kombucha")[0] == "boissons"        # « spice » n'est pas une sauce
    assert classify([], "Sauce soja")[0] == "sauces"                      # « soja » n'est pas végétal
    assert classify([], "") == (None, None)


def test_aggregate_seuil_et_repli_famille():
    out = aggregate(Counter({"boissons": 50, "glaces": 12, "snacks": 1}))
    assert [t["id"] for t in out] == ["boissons", "glaces"]               # snacks < 10 %
    assert out[0]["share"] == round(50 / 63, 3) and out[0]["basis"] == "produits"
    fallback = aggregate(Counter(), "epice")
    assert fallback == [{"id": "sauces", "label": "Sauces et condiments", "products": 0, "share": None,
                         "basis": "famille"}]
