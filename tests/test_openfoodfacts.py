"""Open Food Facts : deltas quotidiens et export complet, avec des fichiers simulés (aucun appel réseau)."""
import gzip
import json

import httpx
import respx

from flavortrends.collectors.openfoodfacts import (DELTA_BASE, OpenFoodFactsDelta, OpenFoodFactsDump,
                                                   csv_row_to_product, is_usable, iter_gzip_lines, matches)
from flavortrends.http import HttpClient


class FakeConn:
    """Remplace la connexion PostgreSQL : aucun fichier delta n'a encore été importé."""
    def execute(self, *a, **k):
        return []


def _jsonl_gz(products):
    return gzip.compress("\n".join(json.dumps(p) for p in products).encode())


def test_iter_gzip_lines_handles_split_chunks():
    data = gzip.compress(b"ligne 1\nligne 2\nligne 3")
    chunks = [data[i:i + 7] for i in range(0, len(data), 7)]
    assert list(iter_gzip_lines(iter(chunks))) == [b"ligne 1", b"ligne 2", b"ligne 3"]


def test_csv_row_to_product_converts_lists_and_ints():
    p = csv_row_to_product({"code": "123", "product_name": "Thé glacé yuzu", "categories_tags": "en:beverages,en:teas",
                            "countries_tags": "en:japan", "created_t": "1794230299", "ingredients_text": "",
                            "unused_column": "x"})
    assert p == {"code": "123", "product_name": "Thé glacé yuzu", "categories_tags": ["en:beverages", "en:teas"],
                 "countries_tags": ["en:japan"], "created_t": 1794230299}


def test_usable_and_filters():
    p = {"code": "1", "product_name": "Chips", "categories_tags": ["en:snacks"], "countries_tags": ["en:mexico"]}
    assert is_usable(p) and not is_usable({"code": "2"})
    assert matches(p, [], [])                          # vide = monde entier, tous aliments
    assert matches(p, ["en:snacks"], ["en:mexico"])
    assert not matches(p, ["en:beverages"], [])


@respx.mock
def test_delta_imports_only_new_usable_products(settings):
    files = ["openfoodfacts_products_1_2.json.gz", "openfoodfacts_products_2_3.json.gz"]
    respx.get(DELTA_BASE + "index.txt").mock(return_value=httpx.Response(200, text="\n".join(reversed(files))))
    respx.get(DELTA_BASE + files[0]).mock(return_value=httpx.Response(200, content=_jsonl_gz([
        {"code": "a", "product_name": "Kimchi chips", "countries_tags": ["en:south-korea"], "nutriments": {"x": 1}},
        {"code": "b"},                                   # sans nom ni ingrédients : ignoré
    ])))
    respx.get(DELTA_BASE + files[1]).mock(return_value=httpx.Response(200, content=_jsonl_gz([
        {"code": "c", "ingredients_text": "eau, yuzu", "countries_tags": ["en:france"]},
    ])))
    col = OpenFoodFactsDelta(conn=FakeConn(), settings=settings, http=HttpClient("test", max_attempts=1))
    items = list(col.fetch(categories=[], countries=[]))
    assert [i.external_id for i in items] == ["a", "c"]
    assert "nutriments" not in items[0].payload        # seuls les champs utiles sont gardés
    assert [name for name, _ in col._done] == files


def test_dump_reads_local_csv_gz(tmp_path, settings):
    header = "code\tproduct_name\tcategories_tags\tcountries_tags\tcreated_t"
    rows = ["1\tPocky matcha\ten:biscuits\ten:japan\t1600000000",
            "2\t\t\ten:france\t1600000000",                 # inutilisable
            "3\tSirop d'érable\ten:syrups\ten:canada\t1500000000"]
    path = tmp_path / "products.csv.gz"
    path.write_bytes(gzip.compress(("\n".join([header] + rows)).encode()))
    col = OpenFoodFactsDump(conn=None, settings=settings, http=HttpClient("test"))
    items = list(col.fetch(categories=[], countries=["en:japan", "en:canada"], path=path))
    assert [i.external_id for i in items] == ["1", "3"]
    assert items[1].payload["categories_tags"] == ["en:syrups"]
