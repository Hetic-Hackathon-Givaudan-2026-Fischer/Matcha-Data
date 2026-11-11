"""Pinterest : import de la veille manuelle, rattachement aux arômes, API (réponses simulées)."""
import httpx
import pytest
import respx

from flavortrends.cleaning.mappers import MAPPERS, Context
from flavortrends.collectors.pinterest import PinterestFormatError, PinterestTrendsApi, parse_manual_csv
from flavortrends.http import HttpClient
from flavortrends.taxonomy import FlavorFinder, read_csv
from tests.conftest import raw_row


def test_manual_csv_comma():
    rows = parse_manual_csv("date,region,keyword,trend_type,rank,growth_mom_pct,note\n"
                            "2026-11-10,fr,Yuzu Lemonade,growing,3,+120%,vu sur la page d'accueil Trends\n")
    assert rows == [{"observed_on": "2026-11-10", "region": "FR", "keyword": "yuzu lemonade", "trend_type": "growing",
                     "note": "vu sur la page d'accueil Trends", "url": None, "rank": 3.0, "growth_wow_pct": None,
                     "growth_mom_pct": 120.0, "growth_yoy_pct": None}]


def test_manual_csv_semicolon_and_french_date():
    rows = parse_manual_csv("date;region;keyword;growth_yoy_pct\n10/11/2026;US;Ube cheesecake;45,5\n")
    assert rows[0]["observed_on"] == "2026-11-10" and rows[0]["growth_yoy_pct"] == 45.5


def test_manual_csv_errors_are_clear():
    with pytest.raises(PinterestFormatError, match="colonnes obligatoires"):
        parse_manual_csv("jour,mot\n2026-11-10,yuzu\n")
    with pytest.raises(PinterestFormatError, match="ligne 2"):
        parse_manual_csv("date,region,keyword\nhier,FR,yuzu\n")


def test_flavor_finder():
    f = FlavorFinder(read_csv())
    assert f.find("Yuzu lemonade recipe") == ["yuzu"]
    assert set(f.find("matcha and black sesame latte")) >= {"matcha", "black_sesame"}
    assert f.find("cottagecore picnic ideas") == []


def test_mapper_links_keyword_to_flavor_or_marks_candidate(ctx):
    ctx = Context(salt=ctx.salt, alias_index={}, finder=FlavorFinder(read_csv()), now=ctx.now)
    known = raw_row("pinterest", {"kind": "trend", "observed_on": "2026-11-10", "region": "FR",
                                  "keyword": "ube cheesecake", "trend_type": "growing", "rank": 1,
                                  "growth_mom_pct": 80})
    unknown = raw_row("pinterest", {"kind": "trend", "observed_on": "2026-11-10", "region": "FR",
                                    "keyword": "salade de kumquat rôti", "trend_type": "growing"})
    r1, r2 = MAPPERS["pinterest"](known, ctx).record, MAPPERS["pinterest"](unknown, ctx).record
    assert r1["flavor_id"] in ("ube", "cheesecake") and r1["pct_growth_mom"] == 80.0
    assert r2["flavor_id"] is None            # candidat à ajouter à la liste


def test_mapper_series_goes_to_search_interest(ctx):
    row = raw_row("pinterest", {"kind": "series", "term": "yuzu", "geo": "US", "week_end": "2026-11-08",
                                "value": 87, "batch_id": "pinterest:2026-11-10"})
    m = MAPPERS["pinterest"](row, Context(salt="s" * 20, alias_index={"yuzu": "yuzu"}))
    assert m.kind == "interest" and m.record["granularity"] == "week" and m.record["flavor_id"] == "yuzu"


@respx.mock
def test_api_collects_trends_and_weekly_series(settings):
    from dataclasses import replace
    s = replace(settings, pinterest_access_token="tok")
    route = respx.get(url__regex=r"https://api\.pinterest\.com/v5/trends/keywords/(FR|US)/top/growing").mock(
        return_value=httpx.Response(200, json={"trends": [
            {"keyword": "Yuzu Lemonade", "pct_growth_wow": 30, "pct_growth_mom": 100, "pct_growth_yoy": 10,
             "time_series": {"2026-11-01": 80, "2026-11-08": 100}}]}))
    items = list(PinterestTrendsApi(conn=None, settings=s, http=HttpClient("t", max_attempts=1)).fetch(
        regions=["FR", "US"], trend_types=["growing"], interests=["food_and_drinks"]))
    assert route.call_count == 2
    assert route.calls[0].request.headers["Authorization"] == "Bearer tok"
    assert route.calls[0].request.url.params["interests"] == "food_and_drinks"
    trends = [i for i in items if i.payload["kind"] == "trend"]
    series = [i for i in items if i.payload["kind"] == "series"]
    assert len(trends) == 2 and len(series) == 4 and trends[0].payload["keyword"] == "yuzu lemonade"


@respx.mock
def test_api_stops_when_access_refused(settings):
    from dataclasses import replace
    s = replace(settings, pinterest_access_token="tok")
    route = respx.get(url__regex=r"https://api\.pinterest\.com/.*").mock(return_value=httpx.Response(401, json={}))
    col = PinterestTrendsApi(conn=None, settings=s, http=HttpClient("t", max_attempts=1))
    assert list(col.fetch(regions=["FR", "US"], trend_types=["growing"], interests=[])) == []
    assert route.call_count == 1 and col.errors == 1
