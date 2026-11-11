"""Open Food Facts : produits alimentaires du monde entier (licence ODbL).

Trois façons de collecter, selon le besoin :

1. OpenFoodFactsDelta (commande `collect off`, chaque jour)
   Open Food Facts publie chaque jour un fichier des produits modifiés dans le monde
   (https://static.openfoodfacts.org/data/delta/). On importe les fichiers pas encore importés.
   Aucune limite de débit, couverture mondiale complète.

2. OpenFoodFactsDump (commande `import-off-dump`, une seule fois)
   Export complet (CSV, environ 1,5 Go compressé, plus de 4 millions de produits) pour l'historique.

3. OpenFoodFacts (commande `collect off-api`, ponctuel)
   API de recherche, limitée à 10 requêtes/minute : utile pour une catégorie ou un pays précis.

Filtres : OFF_CATEGORIES et OFF_COUNTRIES dans .env. Vides = tous les aliments, monde entier.
Les produits sans nom ni ingrédients sont ignorés dès la collecte (inexploitables).
OFF_ONLY_FLAVOR_MATCHES=true : ne garde que les produits qui citent un de nos arômes (gain de place).
"""
from __future__ import annotations

import csv
import json
import logging
import sys
import zlib
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from .base import Collector, RawItem

log = logging.getLogger(__name__)

SEARCH = "https://world.openfoodfacts.org/api/v2/search"
DELTA_BASE = "https://static.openfoodfacts.org/data/delta/"
DUMP_CSV = "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz"
FIELDS = [
    "code", "product_name", "product_name_fr", "product_name_en", "generic_name", "generic_name_fr",
    "brands", "categories_tags", "ingredients_text", "ingredients_text_fr", "ingredients_text_en",
    "ingredients_tags", "countries_tags", "lang", "created_t", "last_modified_t", "labels_tags",
]
TAG_FIELDS = {"categories_tags", "ingredients_tags", "countries_tags", "labels_tags"}
INT_FIELDS = {"created_t", "last_modified_t"}


def subset(p: dict[str, Any]) -> dict[str, Any]:
    """Ne garde que les champs utiles au projet (un produit complet pèse plusieurs Ko)."""
    return {k: p[k] for k in FIELDS if p.get(k) not in (None, "", [])}


def is_usable(p: dict[str, Any]) -> bool:
    return bool(p.get("code")) and any(
        p.get(k) for k in ("product_name", "product_name_fr", "product_name_en", "ingredients_text",
                           "ingredients_text_fr", "ingredients_text_en"))


def matches(p: dict[str, Any], categories: list[str], countries: list[str]) -> bool:
    if categories and not set(categories) & set(p.get("categories_tags") or []):
        return False
    if countries and not set(countries) & set(p.get("countries_tags") or []):
        return False
    return True


TEXT_FIELDS = ("product_name", "product_name_fr", "product_name_en", "generic_name", "generic_name_fr",
               "ingredients_text", "ingredients_text_fr", "ingredients_text_en")


def keep(p: dict[str, Any], categories: list[str], countries: list[str], matcher=None) -> bool:
    """Produit à garder ? Utilisable, dans le périmètre, et (option OFF_ONLY_FLAVOR_MATCHES)
    mentionnant au moins un de nos arômes dans son nom ou ses ingrédients."""
    if not is_usable(p) or not matches(p, categories, countries):
        return False
    return matcher is None or matcher.matches(*(p.get(k) for k in TEXT_FIELDS))


def iter_gzip_lines(chunks: Iterator[bytes]) -> Iterator[bytes]:
    """Décompresse un flux gzip morceau par morceau et renvoie les lignes (sans tout charger en mémoire)."""
    d = zlib.decompressobj(31)
    rest = b""
    for chunk in chunks:
        rest += d.decompress(chunk)
        *lines, rest = rest.split(b"\n")
        yield from lines
    rest += d.flush()
    if rest:
        yield from rest.split(b"\n")


def csv_row_to_product(row: dict[str, str]) -> dict[str, Any]:
    """Une ligne de l'export CSV (tabulations, listes séparées par des virgules) -> même forme que l'API."""
    p: dict[str, Any] = {}
    for k in FIELDS:
        v = (row.get(k) or "").strip()
        if not v:
            continue
        if k in TAG_FIELDS:
            p[k] = [t for t in v.split(",") if t]
        elif k in INT_FIELDS:
            try:
                p[k] = int(float(v))
            except ValueError:
                continue
        else:
            p[k] = v
    return p


class OpenFoodFactsDelta(Collector):
    source_id = "open_food_facts"
    min_interval = 1.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._done: list[tuple[str, int]] = []

    def fetch(self, categories: list[str], countries: list[str], max_files: int = 14,
              matcher=None) -> Iterator[RawItem]:
        index = self.http.get(DELTA_BASE + "index.txt").text.split()
        files = sorted(f for f in index if f.endswith(".json.gz"))  # noms horodatés : tri = ordre chronologique
        done = {r["file_name"] for r in self.conn.execute("SELECT file_name FROM raw.off_delta_file")}
        todo = [f for f in files if f not in done][-max_files:]
        log.info("[off] %s fichiers delta disponibles, %s à importer", len(files), len(todo))
        for name in todo:
            n_kept = n_read = 0
            try:
                with self.http.client.stream("GET", DELTA_BASE + name) as resp:
                    resp.raise_for_status()
                    for line in iter_gzip_lines(resp.iter_raw()):
                        if not line.strip():
                            continue
                        n_read += 1
                        p = json.loads(line)
                        if not keep(p, categories, countries, matcher):
                            continue
                        n_kept += 1
                        yield RawItem(external_id=str(p["code"]), payload=subset(p), query=f"delta:{name}")
            except Exception as exc:
                log.error("[off] %s : %s (le fichier sera retenté à la prochaine collecte)", name, exc)
                self.errors += 1
                continue
            log.info("[off] %s : %s produits lus, %s gardés", name, n_read, n_kept)
            self._done.append((name, n_kept))

    def after_success(self, run_id: int) -> None:
        for name, n in self._done:
            self.conn.execute(
                "INSERT INTO raw.off_delta_file (file_name, run_id, n_products) VALUES (%s, %s, %s) "
                "ON CONFLICT (file_name) DO NOTHING", (name, run_id, n))
        self.conn.commit()


class OpenFoodFactsDump(Collector):
    """Import unique de l'export complet. Peut prendre de 30 à 60 minutes."""

    source_id = "open_food_facts"
    flush_every = 2000

    def fetch(self, categories: list[str], countries: list[str], path: Path | None = None,
              limit: int | None = None, matcher=None) -> Iterator[RawItem]:
        csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
        tag = f"dump:{date.today().isoformat()}"
        if path:
            def chunks():
                with open(path, "rb") as fh:
                    while block := fh.read(1 << 20):
                        yield block
            lines = iter_gzip_lines(chunks())
            yield from self._rows(lines, categories, countries, limit, tag, matcher)
        else:
            log.info("[off] téléchargement en continu de l'export complet (≈1,5 Go)…")
            with self.http.client.stream("GET", DUMP_CSV, timeout=None) as resp:
                resp.raise_for_status()
                yield from self._rows(iter_gzip_lines(resp.iter_raw()), categories, countries, limit, tag, matcher)

    def _rows(self, lines: Iterator[bytes], categories, countries, limit, tag, matcher=None) -> Iterator[RawItem]:
        text = (ln.decode("utf-8", errors="replace") for ln in lines)
        reader = csv.reader(text, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(reader)
        n_read = n_kept = 0
        for values in reader:
            n_read += 1
            p = csv_row_to_product(dict(zip(header, values)))
            if keep(p, categories, countries, matcher):
                n_kept += 1
                yield RawItem(external_id=str(p["code"]), payload=p, query=tag)
                if limit and n_kept >= limit:
                    break
            if n_read % 200_000 == 0:
                log.info("[off] export : %s lignes lues, %s produits gardés", n_read, n_kept)
        log.info("[off] export terminé : %s lignes lues, %s produits gardés", n_read, n_kept)


class OpenFoodFacts(Collector):
    """API de recherche (10 requêtes/minute) : pour une collecte ciblée sur une catégorie ou un pays."""

    source_id = "open_food_facts"
    min_interval = 6.5

    def watermark(self, scope: str) -> int | None:
        row = self.conn.execute(
            """SELECT max((payload->>'last_modified_t')::bigint) AS lm FROM raw.raw_document
               WHERE source_id = %s AND query = %s""",
            (self.source_id, scope),
        ).fetchone()
        return row["lm"] if row else None

    def fetch(self, categories: list[str], countries: list[str], max_pages: int = 20,
              page_size: int = 100, full: bool = False, matcher=None) -> Iterator[RawItem]:
        for cat in categories or [None]:
            for country in countries or [None]:
                scope = f"{cat or 'all'}|{country or 'all'}"
                mark = None if full else self.watermark(scope)
                if mark:
                    log.info("[off] %s : reprise après last_modified_t=%s", scope, mark)
                for page in range(1, max_pages + 1):
                    params = {"fields": ",".join(FIELDS), "page_size": page_size, "page": page,
                              "sort_by": "last_modified_t"}
                    if cat:
                        params["categories_tags"] = cat
                    if country:
                        params["countries_tags"] = country
                    try:
                        data = self.http.get(SEARCH, params=params).json()
                    except Exception as exc:
                        log.error("[off] %s page %s : %s", scope, page, exc)
                        self.errors += 1
                        break
                    products = data.get("products") or []
                    if not products:
                        break
                    reached_mark = False
                    for p in products:
                        lm = int(p.get("last_modified_t") or 0)
                        if mark and lm < mark:
                            reached_mark = True
                            continue
                        if not keep(p, [], [], matcher):
                            continue
                        yield RawItem(external_id=str(p["code"]), payload=subset(p), query=scope)
                    if reached_mark or page * page_size >= int(data.get("count") or 0):
                        break
                else:
                    log.info("[off] %s : limite de %s pages atteinte. Pour un historique plus profond : "
                             "flavortrends import-off-dump", scope, max_pages)
