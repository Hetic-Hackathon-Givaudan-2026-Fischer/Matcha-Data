"""Collecteurs testés contre des réponses d'API simulées (respx) : aucun appel réseau."""
import httpx
import pytest
import respx

from flavortrends.collectors.bluesky import Bluesky
from flavortrends.collectors.gdelt import Gdelt, build_query
from flavortrends.collectors.google_trends import TrendsFormatError, parse_trends_csv
from flavortrends.collectors.wikipedia import WikipediaPageviews
from flavortrends.collectors.youtube import YouTube
from flavortrends.http import HttpClient
from flavortrends.taxonomy import Flavor

YUZU = Flavor("yuzu", "Yuzu", "Yuzu", "agrumes", "Yuzu", "Yuzu", {"fr": ("yuzu",), "en": ("yuzu",)})
PASSION = Flavor("passion_fruit", "Fruit de la passion", "Passion fruit", "fruits_exotiques", "Fruit de la passion",
                 "Passion fruit", {"fr": ("fruit de la passion", "maracuja"), "en": ("passion fruit",)})


def fast_http():
    return HttpClient("test-agent", max_attempts=2, backoff_min=0, backoff_max=0)


@respx.mock
def test_youtube_search_then_stats(settings):
    search = respx.get("https://www.googleapis.com/youtube/v3/search").mock(return_value=httpx.Response(
        200, json={"items": [{"id": {"videoId": "v1"}}, {"id": {"videoId": "v2"}}]}))
    videos = respx.get("https://www.googleapis.com/youtube/v3/videos").mock(return_value=httpx.Response(
        200, json={"items": [{"id": "v1", "snippet": {}, "statistics": {}}, {"id": "v2", "snippet": {}, "statistics": {}}]}))
    yt = YouTube(conn=None, settings=settings, http=fast_http())
    items = list(yt.fetch(flavors=[YUZU], langs=["fr"]))
    assert [i.external_id for i in items] == ["v1", "v2"]
    assert items[0].flavor_id == "yuzu" and items[0].query == "yuzu saveur"
    assert search.calls[0].request.url.params["relevanceLanguage"] == "fr"
    assert videos.calls[0].request.url.params["id"] == "v1,v2"


@respx.mock
def test_youtube_respects_unit_budget(settings):
    respx.get("https://www.googleapis.com/youtube/v3/search").mock(return_value=httpx.Response(200, json={"items": []}))
    yt = YouTube(conn=None, settings=settings, http=fast_http())  # budget = 1000 unités -> 9 recherches max
    list(yt.fetch(flavors=[YUZU] * 20, langs=["fr"]))
    assert respx.calls.call_count == 9
    assert yt.truncated is False      # arrêt prévu par la rotation : collecte réussie, pas partielle


@respx.mock
def test_youtube_rotation_covers_every_flavor(settings, monkeypatch):
    import datetime as dt
    from flavortrends.collectors import youtube as yt_module

    route = respx.get("https://www.googleapis.com/youtube/v3/search").mock(
        return_value=httpx.Response(200, json={"items": []}))
    flavors = [Flavor(f"f{i}", f"Arome{i}", f"Flavor{i}", "x", aliases={"fr": (f"arome{i}",)}) for i in range(20)]
    seen = set()
    for day in range(3):  # budget 1000 -> 9 recherches/jour : 20 arômes couverts en 3 jours
        class FakeDate(dt.date):
            @classmethod
            def today(cls, _d=day):
                return dt.date(2026, 11, 10) + dt.timedelta(days=_d)
        monkeypatch.setattr(yt_module, "date", FakeDate)
        list(YouTube(conn=None, settings=settings, http=fast_http()).fetch(flavors=flavors, langs=["fr"]))
    seen = {c.request.url.params["q"] for c in route.calls}
    assert seen == {f"arome{i} saveur" for i in range(20)}


@respx.mock
def test_youtube_stops_on_quota_exceeded(settings):
    respx.get("https://www.googleapis.com/youtube/v3/search").mock(return_value=httpx.Response(
        403, json={"error": {"errors": [{"reason": "quotaExceeded"}]}}))
    yt = YouTube(conn=None, settings=settings, http=fast_http())
    assert list(yt.fetch(flavors=[YUZU, PASSION], langs=["fr"])) == []
    assert yt.truncated is True and respx.calls.call_count == 1


@respx.mock
def test_bluesky_login_and_pagination(settings):
    respx.post("https://bsky.social/xrpc/com.atproto.server.createSession").mock(
        return_value=httpx.Response(200, json={"accessJwt": "jwt"}))
    route = respx.get("https://bsky.social/xrpc/app.bsky.feed.searchPosts").mock(side_effect=[
        httpx.Response(200, json={"posts": [{"uri": "at://a/1"}], "cursor": "c1"}),
        httpx.Response(200, json={"posts": [{"uri": "at://a/2"}]}),
    ])
    bs = Bluesky(conn=None, settings=settings, http=fast_http())
    items = list(bs.fetch(flavors=[YUZU], langs=["fr"]))
    assert [i.external_id for i in items] == ["at://a/1", "at://a/2"]
    assert route.calls[0].request.headers["Authorization"] == "Bearer jwt"
    assert route.calls[1].request.url.params["cursor"] == "c1"


@respx.mock
def test_wikipedia_resolves_redirects():
    respx.get("https://en.wikipedia.org/w/api.php").mock(return_value=httpx.Response(200, json={"query": {
        "normalized": [{"from": "passion fruit", "to": "Passion fruit"}],
        "redirects": [{"from": "Passion fruit", "to": "Passiflora edulis"}],
        "pages": [{"title": "Passiflora edulis"}, {"title": "Nope", "missing": True}],
    }}))
    wp = WikipediaPageviews(conn=None, settings=None, http=fast_http())
    assert wp.resolve_titles("en", ["passion fruit", "Nope"]) == {"passion fruit": "Passiflora edulis"}


@respx.mock
def test_gdelt_text_error_is_counted_not_fatal():
    respx.get("https://api.gdeltproject.org/api/v2/doc/doc").mock(side_effect=[
        httpx.Response(200, text="Your search contained a phrase that was too short."),
        httpx.Response(200, json={"articles": [{"url": "https://ex.com/1", "title": "t"}]}),
    ])
    g = Gdelt(conn=None, settings=None, http=fast_http())
    g.min_interval = 0
    items = list(g.fetch(flavors=[YUZU], langs=["fr", "en"]))
    assert len(items) == 1 and g.errors == 1


@respx.mock
def test_gdelt_stops_after_repeated_429():
    route = respx.get("https://api.gdeltproject.org/api/v2/doc/doc").mock(
        return_value=httpx.Response(429, text="Please limit requests"))
    g = Gdelt(conn=None, settings=None, http=fast_http())
    assert list(g.fetch(flavors=[YUZU, PASSION, YUZU], langs=["fr", "en"])) == []
    assert g.truncated is True
    assert route.call_count == 2 * 2  # 2 requêtes x 2 tentatives, puis arrêt


def test_gdelt_query_groups_flavors():
    q = build_query(["yuzu", "passion fruit", "za'atar"], "en")
    assert q.startswith("(yuzu OR \"passion fruit\" OR \"za'atar\") (drink OR flavor")
    assert q.endswith("sourcelang:english")
    assert build_query(["yuzu"], "fr").startswith("yuzu (boisson")


@respx.mock
def test_gdelt_groups_and_links_articles_to_flavors():
    route = respx.get("https://api.gdeltproject.org/api/v2/doc/doc").mock(return_value=httpx.Response(200, json={
        "articles": [{"url": "https://ex.com/1", "title": "Le maracuja, star des desserts d'été"},
                     {"url": "https://ex.com/2", "title": "Yuzu and matcha drinks are booming"},
                     {"url": "https://ex.com/3", "title": "Food trends of the year"}]}))
    flavors = [YUZU, PASSION] + [Flavor(f"f{i}", f"A{i}", f"F{i}", "x") for i in range(10)]   # 12 arômes
    g = Gdelt(conn=None, settings=None, http=fast_http())
    items = list(g.fetch(flavors=flavors, langs=["fr"]))
    assert route.call_count == 2                      # 12 arômes -> 2 groupes -> 2 requêtes
    by_url = {i.payload["url"]: i for i in items}
    assert len(items) == 3                            # le même article dans 2 groupes n'est gardé qu'une fois
    assert by_url["https://ex.com/1"].flavor_id == "passion_fruit"
    assert by_url["https://ex.com/2"].payload["_matched_flavors"] == ["yuzu"]
    assert by_url["https://ex.com/3"].flavor_id is None


def test_google_trends_csv_english_export():
    text = "Category: All categories\n\nWeek,yuzu: (France),vanille: (France)\n2025-11-09,12,80\n2025-11-16,<1,78\n"
    rows = parse_trends_csv(text)
    assert len(rows) == 4
    assert rows[0] == {"term": "yuzu", "geo": "France", "date": "2025-11-09", "value": 12.0, "value_raw": "12",
                       "censored": False, "granularity": "week", "terms_in_batch": ["yuzu", "vanille"]}
    assert rows[2]["censored"] is True and rows[2]["value"] == 0.5


def test_google_trends_csv_french_export_daily():
    text = "Catégorie : Toutes catégories\n\nJour,matcha: (France)\n2026-10-01,40\n2026-10-02,42\n"
    rows = parse_trends_csv(text)
    assert [r["granularity"] for r in rows] == ["day", "day"]


def test_google_trends_plan_uses_anchor_in_every_batch():
    from flavortrends.collectors.google_trends import build_plan, explore_url
    from flavortrends.taxonomy import read_csv

    flavors = read_csv()
    plan = build_plan(flavors, "fr", "vanilla")
    assert all(len(b) <= 5 and b[-1] == "vanille" for b in plan)
    covered = {t for b in plan for t in b[:-1]}
    assert len(covered) == len(flavors) - 1
    url = explore_url(["citron vert", "yuzu", "vanille"], "FR", "fr")
    assert url == ("https://trends.google.com/trends/explore?date=today%205-y&geo=FR"
                   "&q=citron%20vert,yuzu,vanille&hl=fr")


def test_google_trends_csv_rejects_other_files():
    with pytest.raises(TrendsFormatError):
        parse_trends_csv("Région,yuzu\nIle-de-France,100\n")
