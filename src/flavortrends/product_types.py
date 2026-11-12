"""Types de produits du supermarché 3D (définis avec l'équipe Tech) et rattachement des produits Open Food Facts.

Chaque produit reçoit UN type : le premier qui correspond dans l'ordre de PRODUCT_TYPES, du plus précis au plus
général (ex. un yaourt végétal est « vegetal » avant d'être « produits-laitiers » ; un biscuit au chocolat est
« biscuits » avant d'être « chocolats »).

1. Catégories Open Food Facts EXACTES (ex. « en:yogurts »). On ne cherche pas un mot à l'intérieur d'une catégorie :
   « en:plant-based-foods-and-beverages », présente sur presque tous les produits végétaux, ferait sinon passer
   biscuits et yaourts pour des boissons.
2. Si le produit n'a aucune catégorie utile (≈ 40 % des cas), mots du NOM du produit, en mot entier.

Un arôme est ensuite associé aux types de ses produits : voir aggregate().
"""
from __future__ import annotations

import re
from collections import Counter

from .cleaning.text import normalize_key

# (identifiant, libellé, catégories OFF exactes, mots du nom du produit)
PRODUCT_TYPES: list[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = [
    ("nutrition", "Produits nutritionnels et sportifs",
     ("dietary-supplements", "bodybuilding-supplements", "protein-bars", "protein-powders", "protein-shakes",
      "sports-drinks", "meal-replacements", "vitamins"),
     ("protein", "proteine", "whey", "complement alimentaire", "supplement", "vitamin", "vitamine")),
    ("glaces", "Glaces et desserts glacés",
     ("ice-creams-and-sorbets", "ice-creams", "sorbets", "ice-cream-tubs", "ice-cream-bars", "ice-cream-cones",
      "frozen-desserts", "ice-lollies"),
     ("ice cream", "sorbet", "creme glacee", "gelato", "esquimau", "cornet")),
    ("vegetal", "Produits végétaux et alternatives alimentaires",
     ("dairy-substitutes", "milk-substitutes", "plant-based-milk-alternatives", "non-dairy-yogurts",
      "non-dairy-desserts", "non-dairy-fermented-foods", "meat-alternatives", "meat-analogues", "tofu",
      "plant-based-creams", "plant-based-cheeses"),
     # pas « soja » ni « végétal » seuls : « sauce soja », « huile végétale » ne sont pas des alternatives
     ("plant based", "boisson vegetale", "boisson d avoine", "oat drink", "oat milk", "soy milk",
      "almond milk", "lait d amande", "yaourt vegetal", "dessert vegetal", "tofu")),
    ("produits-laitiers", "Produits laitiers",
     ("yogurts", "fruit-yogurts", "fermented-milk-products", "cheeses", "milks", "milks-liquid-and-powder",
      "flavoured-milks", "dairy-drinks", "fermented-milk-drinks", "creams", "butters", "fresh-cheeses", "kefir"),
     # pas « lait » / « milk » seuls : « milk chocolate », « lait de coco »
     ("yaourt", "yogourt", "yogurt", "yoghurt", "fromage", "cheese", "kefir", "skyr", "fromage blanc",
      "lait fermente", "milkshake")),
    ("desserts-lactes", "Desserts lactés",
     ("dairy-desserts", "fermented-dairy-desserts", "creamy-puddings", "entremets-mousses-and-creamy-puddings",
      "chocolate-desserts", "puddings", "custards", "dessert-creams", "mousses", "panna-cotta", "rice-puddings"),
     ("creme dessert", "mousse", "flan", "pudding", "panna cotta", "liegeois", "riz au lait", "tiramisu")),
    ("biscuits", "Biscuits et pâtisseries",
     ("biscuits", "biscuits-and-cakes", "cakes", "chocolate-biscuits", "filled-biscuits", "wafers", "drop-cookies",
      "cookies", "pastries", "sweet-pastries-and-pies", "chocolate-cakes", "shortbread-cookies", "madeleines",
      "macarons"),
     ("biscuit", "cookie", "cookies", "gateau", "cake", "madeleine", "macaron", "gaufrette", "sable", "tarte",
      "brownie", "financier")),
    ("viennoiseries", "Viennoiseries et produits de boulangerie",
     ("viennoiseries", "breads", "brioches", "croissants", "pains-au-chocolat", "sliced-breads", "muffins",
      "doughnuts", "pancakes", "crepes"),
     ("pain", "bread", "brioche", "croissant", "viennoiserie", "muffin", "donut", "beignet", "bagel", "crepe",
      "pancake")),
    ("cereales", "Céréales et produits du petit-déjeuner",
     ("breakfast-cereals", "mueslis", "chocolate-cereals", "extruded-cereals", "cereal-bars", "granolas",
      "porridges", "breakfasts", "sweet-spreads", "fr:pates-a-tartiner", "jams", "fruit-jams", "honeys",
      "peanut-butters", "nut-butters"),
     ("cereales", "cereal", "muesli", "granola", "porridge", "flocons", "confiture", "jam", "miel", "honey",
      "pate a tartiner", "peanut butter", "beurre de cacahuete")),
    ("chocolats", "Chocolats et produits chocolatés",
     ("chocolates", "chocolate-candies", "milk-chocolates", "dark-chocolates", "white-chocolates",
      "chocolate-bars", "candy-chocolate-bars", "filled-chocolates", "chocolate-truffles", "pralines"),
     ("chocolat", "chocolate", "cacao", "truffe", "praline")),
    ("confiseries", "Confiseries",
     ("confectioneries", "candies", "bonbons", "gummies", "lollipops", "chewing-gum", "marshmallows", "nougats",
      "jelly-beans", "hard-candies", "marzipan", "caramels"),
     ("bonbon", "candy", "gummies", "gummy", "sucette", "chewing gum", "nougat", "guimauve", "marshmallow",
      "caramel", "pate de fruits", "dragee")),
    ("snacks", "Snacks et produits apéritifs",
     ("salty-snacks", "chips-and-fries", "crisps", "potato-crisps", "appetizers", "crackers-appetizers",
      "crackers", "popcorn", "nuts", "salted-nuts", "pretzels", "bars", "salty-snacks-made-from-potato"),
     ("chips", "crisps", "cracker", "crackers", "popcorn", "pop corn", "bretzel", "pretzel", "aperitif",
      "cacahuetes", "barre")),
    ("sauces", "Sauces et condiments",
     ("sauces", "condiments", "tomato-sauces", "pasta-sauces", "dips", "mayonnaises", "ketchup", "mustards",
      "spices", "herbs-and-spices", "salad-dressings", "vinegars", "cooking-helpers", "spice-mixes",
      "hot-sauces", "pestos", "marinades"),
     ("sauce", "ketchup", "mayonnaise", "moutarde", "mustard", "vinaigrette", "dressing", "pesto", "marinade",
      # pas « spice » seul : « pumpkin spice », « chai spice » sont des noms d'arômes
      "spice mix", "melange d epices", "condiment", "curry paste", "pate de curry")),
    ("plats", "Plats préparés et produits traiteur",
     ("meals", "meals-with-meat", "meals-with-chicken", "meals-with-poultry", "meals-with-fish", "pasta-dishes",
      "pizzas", "pizzas-pies-and-quiches", "microwave-meals", "soups", "vegetable-soups", "sandwiches",
      "prepared-salads", "combination-meals", "frozen-ready-made-meals", "rice-dishes", "instant-noodles",
      "broths", "frozen-pizzas-and-pies", "stuffed-pastas", "quiches"),
     ("pizza", "soupe", "soup", "plat", "salade", "sandwich", "quiche", "lasagne", "risotto", "noodles", "ramen",
      "nouilles", "wrap", "burger", "gratin")),
    ("boissons", "Boissons",
     ("beverages", "non-alcoholic-beverages", "plant-based-beverages", "sodas", "soft-drinks", "carbonated-drinks",
      "juices-and-nectars", "fruit-juices", "fruit-based-beverages", "teas", "herbal-teas", "tea-based-beverages",
      "iced-teas", "coffees", "coffee-drinks", "instant-coffees", "coffee-capsules", "syrups", "flavoured-syrups",
      "waters", "flavored-waters", "energy-drinks", "hot-beverages", "alcoholic-beverages",
      "beverage-preparations", "instant-beverages", "sweetened-beverages", "smoothies", "kombuchas",
      "fermented-drinks", "beverages-and-beverages-preparations"),
     ("boisson", "drink", "jus", "juice", "soda", "tea", "infusion", "tisane", "cafe", "coffee", "latte",
      "sirop", "syrup", "smoothie", "limonade", "lemonade", "nectar", "kombucha", "water", "biere",
      "beer", "vin", "wine", "cocktail")),
]
LABELS = {tid: label for tid, label, _, _ in PRODUCT_TYPES}

# Repli pour un arôme sans aucun produit : type le plus probable selon sa famille.
FAMILY_TYPE = {
    "agrumes": "boissons", "cocktail": "boissons", "the": "boissons", "floral": "boissons",
    "fruits_exotiques": "boissons", "fruits_frais": "produits-laitiers", "fruits_noyau": "produits-laitiers",
    "fruits_rouges": "produits-laitiers", "fruits_a_coque": "chocolats", "gourmand": "biscuits",
    "torrefie": "chocolats", "epice": "sauces", "umami": "sauces", "fume": "sauces", "fermente": "sauces",
    "herbace": "sauces", "vegetal": "vegetal",
}

# Seuil d'association : un type est retenu s'il représente au moins 10 % des produits de l'arôme (min. 2 produits).
MIN_SHARE, MIN_PRODUCTS = 0.10, 2

_CATEGORY_INDEX: dict[str, str] = {}
for _tid, _label, _cats, _words in PRODUCT_TYPES:
    for _c in _cats:
        _CATEGORY_INDEX.setdefault(_c if ":" in _c else f"en:{_c}", _tid)
_ORDER = {tid: i for i, (tid, _, _, _) in enumerate(PRODUCT_TYPES)}
_NAME_PATTERNS = [(tid, re.compile(r"\b(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
                                   + r")\b")) for tid, _, _, words in PRODUCT_TYPES]


def classify(categories: list[str] | None, name: str | None = None) -> tuple[str | None, str | None]:
    """Type d'un produit et méthode utilisée (« categorie » ou « nom »), ou (None, None)."""
    found = {_CATEGORY_INDEX[c] for c in (categories or []) if c in _CATEGORY_INDEX}
    if found:
        return min(found, key=_ORDER.__getitem__), "categorie"
    text = normalize_key(name or "")
    if text:
        for tid, pattern in _NAME_PATTERNS:
            if pattern.search(text):
                return tid, "nom"
    return None, None


def aggregate(counts: Counter, family: str | None = None) -> list[dict]:
    """Types associés à un arôme, du plus fréquent au moins fréquent.

    Retient les types qui pèsent au moins 10 % (et 2 produits) ; toujours au moins le premier.
    Sans aucun produit classé : repli sur la famille de l'arôme (products = 0, basis = « famille »).
    """
    total = sum(counts.values())
    if not total:
        tid = FAMILY_TYPE.get(family or "", "plats")
        return [{"id": tid, "label": LABELS[tid], "products": 0, "share": None, "basis": "famille"}]
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], _ORDER[kv[0]]))
    out = [{"id": tid, "label": LABELS[tid], "products": n, "share": round(n / total, 3), "basis": "produits"}
           for i, (tid, n) in enumerate(ranked) if i == 0 or (n / total >= MIN_SHARE and n >= MIN_PRODUCTS)]
    return out
