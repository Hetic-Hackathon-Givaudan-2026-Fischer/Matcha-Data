"""Test de bout en bout sur une vraie base PostgreSQL.

Lancé seulement si TEST_DATABASE_URL est défini, et seulement sur une base dont le nom finit par _test
(les schémas raw et core y sont supprimés puis recréés).
"""
import os
from datetime import datetime, timezone

import psycopg
import pytest
from psycopg.rows import dict_row

from flavortrends.cleaning.pipeline import run_cleaning
from flavortrends.collectors.base import Collector, RawItem
from flavortrends.config import Settings
from flavortrends.db import migrate
from flavortrends import taxonomy

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL non défini")


@pytest.fixture
def conn():
    if not URL.rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
        pytest.fail("TEST_DATABASE_URL doit pointer vers une base dont le nom finit par _test")
    c = psycopg.connect(URL, row_factory=dict_row)
    c.execute("DROP SCHEMA IF EXISTS core CASCADE; DROP SCHEMA IF EXISTS raw CASCADE; "
              "DROP TABLE IF EXISTS public.schema_migrations")
    c.commit()
    migrate(c)
    taxonomy.sync_to_db(c, taxonomy.read_csv())
    yield c
    c.close()


class FakeRss(Collector):
    source_id = "rss"

    def __init__(self, conn, settings, items):
        super().__init__(conn, settings, http=object())
        self.items = items

    def fetch(self):
        yield from self.items


def article(i, title, day=8, summary="Article sur les nouvelles boissons aromatisées en France"):
    return RawItem(f"id{i}", {"title": title, "summary": summary, "link": f"https://ex.com/{i}",
                              "published_iso": datetime(2026, 11, day, tzinfo=timezone.utc).isoformat(),
                              "feed_lang": "fr"}, query="Test")


SETTINGS = Settings(URL, "t@example.org", "salt-for-tests-123456", "", 0, "", "", [], [], ["fr"])


def test_freshness_levels(conn):
    from flavortrends.freshness import check

    FakeRss(conn, SETTINGS, [article(1, "Le yuzu arrive en rayon")]).run()
    by_source = {i["source_id"]: i for i in check(conn, SETTINGS)}
    assert by_source["rss"]["level"] == "ok"                      # collecté à l'instant
    assert by_source["wikipedia_pageviews"]["level"] == "alert"   # jamais collecté
    assert by_source["youtube"]["level"] == "info"                # pas de clé : non configuré

    # Collecté il y a 7 h mais jamais nettoyé : avertissement
    conn.execute("UPDATE raw.raw_document SET fetched_at = now() - interval '7 hours' WHERE source_id = 'rss'")
    conn.commit()
    assert {i["source_id"]: i for i in check(conn, SETTINGS)}["rss"]["level"] == "warning"

    run_cleaning(conn, SETTINGS)
    assert {i["source_id"]: i for i in check(conn, SETTINGS)}["rss"]["level"] == "ok"

    conn.execute("UPDATE raw.collection_run SET finished_at = now() - interval '7 hours' WHERE source_id = 'rss'")
    conn.commit()
    late = {i["source_id"]: i for i in check(conn, SETTINGS)}["rss"]
    assert late["level"] == "alert" and "en retard" in late["message"]


def test_raw_purge_keeps_clean_data_and_later_updates(conn):
    from flavortrends.maintenance import ALL_FAMILIES, purge_raw

    FakeRss(conn, SETTINGS, [article(1, "Le yuzu arrive en rayon")]).run()
    run_cleaning(conn, SETTINGS)
    conn.execute("UPDATE raw.raw_document SET fetched_at = now() - interval '10 days'")
    conn.commit()
    assert purge_raw(conn, 7, ALL_FAMILIES) == 1
    row = conn.execute("SELECT raw_id, title FROM core.document WHERE external_id = 'id1'").fetchone()
    assert row["raw_id"] is None and row["title"] == "Le yuzu arrive en rayon"   # la donnée propre reste

    # Une nouvelle version arrivée après la purge met bien à jour la ligne propre
    FakeRss(conn, SETTINGS, [article(1, "Le yuzu arrive en rayon (mise à jour)")]).run()
    run_cleaning(conn, SETTINGS)
    assert "mise à jour" in conn.execute(
        "SELECT title FROM core.document WHERE external_id = 'id1'").fetchone()["title"]


def test_storage_alert(conn):
    from dataclasses import replace
    from flavortrends.freshness import check

    tiny = replace(SETTINGS, db_size_limit_mb=1)    # 1 Mo : la base de test dépasse forcément
    item = {i["source_id"]: i for i in check(conn, tiny)}["base_de_donnees"]
    assert item["level"] == "alert" and "presque pleine" in item["message"]


def test_pinterest_manual_import_end_to_end(conn, tmp_path):
    from flavortrends.collectors.pinterest import PinterestManualImport

    f = tmp_path / "veille.csv"
    f.write_text("date;region;keyword;growth_mom_pct\n10/11/2026;FR;Yuzu lemonade;120\n"
                 "10/11/2026;FR;salade de kumquat rôti;50\n", encoding="utf-8")
    assert PinterestManualImport(conn, SETTINGS).run(paths=[f]).n_inserted == 2
    assert run_cleaning(conn, SETTINGS)["external_trends"] == 2
    rows = {r["keyword"]: r["flavor_id"] for r in conn.execute("SELECT keyword, flavor_id FROM core.external_trend")}
    assert rows == {"yuzu lemonade": "yuzu", "salade de kumquat rôti": None}


def test_export_orange(conn, tmp_path):
    import csv as _csv
    from flavortrends.exports import export_orange

    FakeRss(conn, SETTINGS, [article(1, "Le yuzu arrive en rayon", summary="Une limonade au yuzu et au gingembre")]).run()
    run_cleaning(conn, SETTINGS)
    counts = export_orange(conn, tmp_path)
    assert counts["aromes_indicateurs.csv"] == 102
    rows = {r["mS#arome_id"]: r for r in _csv.DictReader(open(tmp_path / "aromes_indicateurs.csv", encoding="utf-8"))}
    assert rows["yuzu"]["C#mentions_presse_30j"] == "1" and rows["ginger"]["C#mentions_presse_30j"] == "1"
    docs = list(_csv.DictReader(open(tmp_path / "documents_textes.csv", encoding="utf-8")))
    assert docs[0]["mS#aromes_detectes"] == "ginger,yuzu"


def test_concurrent_collection_and_cleaning_are_skipped(conn):
    # Un autre programme tient les verrous (battement de cœur récent) : collecte et nettoyage sont ignorés
    conn.execute("INSERT INTO raw.job_lock (lock_name, holder) VALUES ('collect:rss', 'autre'), ('clean', 'autre')")
    conn.commit()
    assert FakeRss(conn, SETTINGS, [article(1, "Le yuzu arrive en rayon")]).run().status == "skipped"
    assert run_cleaning(conn, SETTINGS).get("locked") == 1
    # Le programme est mort : plus de battement de cœur depuis 20 min -> le verrou est repris
    conn.execute("UPDATE raw.job_lock SET heartbeat_at = now() - interval '20 minutes'")
    conn.commit()
    assert FakeRss(conn, SETTINGS, [article(1, "Le yuzu arrive en rayon")]).run().status == "success"
    assert conn.execute("SELECT count(*) AS n FROM raw.job_lock WHERE lock_name = 'collect:rss'").fetchone()["n"] == 0


def test_collect_is_idempotent_and_cleaning_dedups(conn):
    s = Settings(URL, "t@example.org", "salt-for-tests-123456", "", 0, "", "", [], [], ["fr"])
    long = "Le yuzu s'impose dans les boissons pétillantes peu sucrées vendues en grande surface cette année"
    items = [
        article(1, "Le yuzu s'impose", day=7, summary=long),
        article(2, "Le yuzu s'impose !", day=8, summary=long),                 # doublon exact (ponctuation)
        article(3, "Le yuzu s'impose", day=9, summary=long + " en France"),    # quasi-doublon
        article(4, "La vanille reste stable", day=8,
                summary="La vanille de Madagascar reste l'arôme préféré des yaourts selon une étude publiée mardi"),
    ]
    first = FakeRss(conn, s, items).run()
    again = FakeRss(conn, s, items).run()
    assert (first.n_inserted, again.n_inserted) == (4, 0)

    stats = run_cleaning(conn, s)
    assert stats["documents"] == 4 and stats["errors"] == 0

    rows = {r["external_id"]: r for r in conn.execute(
        "SELECT external_id, doc_id, dup_of, dup_method FROM core.document")}
    assert rows["id1"]["dup_of"] is None
    assert rows["id2"]["dup_of"] == rows["id1"]["doc_id"] and rows["id2"]["dup_method"] == "exact"
    assert rows["id3"]["dup_of"] == rows["id1"]["doc_id"] and rows["id3"]["dup_method"] == "near"
    assert rows["id4"]["dup_of"] is None

    # Une nouvelle version d'un document remplace l'ancienne dans la couche propre, sans doublon.
    changed = [article(4, "La vanille reste stable (mise à jour)", day=8,
                       summary="La vanille de Madagascar reste l'arôme préféré des yaourts selon une étude publiée mardi")]
    assert FakeRss(conn, s, changed).run().n_inserted == 1
    run_cleaning(conn, s)
    assert conn.execute("SELECT count(*) AS n FROM core.document").fetchone()["n"] == 4
    assert "mise à jour" in conn.execute(
        "SELECT title FROM core.document WHERE external_id = 'id4'").fetchone()["title"]
