from datetime import date, datetime, timezone

from flavortrends.cleaning.mappers import MAPPERS, parse_dt
from tests.conftest import raw_row


def test_parse_dt_formats():
    assert parse_dt("20261110T081500Z") == datetime(2026, 11, 10, 8, 15, tzinfo=timezone.utc)
    assert parse_dt("2026-11-10T08:15:00Z") == datetime(2026, 11, 10, 8, 15, tzinfo=timezone.utc)
    assert parse_dt("2026-11-10T09:15:00+01:00") == datetime(2026, 11, 10, 8, 15, tzinfo=timezone.utc)
    assert parse_dt(1794230299).tzinfo == timezone.utc
    assert parse_dt("pas une date") is None
    assert parse_dt(None) is None


def test_youtube(ctx):
    p = {"id": "abc123", "snippet": {"publishedAt": "2026-11-08T10:00:00Z", "channelId": "UC42",
                                     "title": "Je teste 5 boissons au yuzu", "description": "Code promo YUZU10 en description",
                                     "defaultAudioLanguage": "fr"},
         "statistics": {"viewCount": "1520", "likeCount": "88", "commentCount": "12"}}
    m = MAPPERS["youtube"](raw_row("youtube", p, flavor_id="yuzu", query="yuzu saveur"), ctx)
    r = m.record
    assert m.kind == "document" and r["doc_type"] == "video"
    assert r["url"] == "https://www.youtube.com/watch?v=abc123"
    assert r["engagement"] == {"views": 1520, "likes": 88, "comments": 12}
    assert r["lang"] == "fr" and r["lang_source"] == "source"
    assert r["is_sponsored"] is True
    assert r["author_hash"] and "UC42" not in r["author_hash"]
    assert r["flavor_hint"] == "yuzu"


def test_bluesky_has_no_url_and_handles_future_date(ctx):
    p = {"uri": "at://did:plc:xyz/app.bsky.feed.post/3k", "author": {"did": "did:plc:xyz", "handle": "alice.bsky.social"},
         "record": {"text": "Le matcha latte au sésame noir est incroyable", "createdAt": "2030-01-01T00:00:00Z", "langs": ["fr"]},
         "likeCount": 4, "repostCount": 1, "replyCount": 0, "quoteCount": 0}
    r = MAPPERS["bluesky"](raw_row("bluesky", p), ctx).record
    assert r["url"] is None
    assert "alice" not in str(r)
    assert "future_date" in r["quality_flags"]
    assert r["published_at"] == datetime(2026, 11, 10, 3, tzinfo=timezone.utc)


def test_gdelt(ctx):
    p = {"url": "https://ex.com/a", "title": "Yuzu drinks are booming", "seendate": "20261109T120000Z",
         "language": "English", "sourcecountry": "United States", "domain": "ex.com"}
    r = MAPPERS["gdelt"](raw_row("gdelt", p), ctx).record
    assert r["lang"] == "en" and r["country"] == "United States"
    assert r["published_at"] == datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


def test_google_news_strips_source_suffix(ctx):
    p = {"title": "Le yuzu débarque dans les rayons - Le Monde", "source_title": "Le Monde",
         "link": "https://news.google.com/x", "published_iso": "2026-11-08T07:00:00+00:00", "feed_lang": "fr", "country": "FR"}
    r = MAPPERS["google_news"](raw_row("google_news", p), ctx).record
    assert r["title"] == "Le yuzu débarque dans les rayons"


def test_rss_skips_empty_text(ctx):
    p = {"title": "", "summary": "<p> </p>", "link": "https://ex.com", "published_iso": "2026-11-08T07:00:00+00:00"}
    m = MAPPERS["rss"](raw_row("rss", p), ctx)
    assert m.kind == "skip"


def test_rss_skips_missing_date(ctx):
    p = {"title": "Nouvelle boisson au yuzu", "summary": "Lancement", "link": "https://ex.com", "published_iso": None}
    assert MAPPERS["rss"](raw_row("rss", p), ctx).kind == "skip"


def test_open_food_facts(ctx):
    p = {"code": "3760000000000", "product_name": "Boisson pétillante Yuzu &amp; Menthe", "brands": "marque bio, Groupe X",
         "categories_tags": ["en:beverages"], "ingredients_text": "Eau gazéifiée, jus de yuzu (2 %)",
         "ingredients_tags": ["en:water", "en:yuzu-juice"], "countries_tags": ["en:france"], "lang": "fr",
         "created_t": 1794230299, "last_modified_t": 1794353500}
    m = MAPPERS["open_food_facts"](raw_row("open_food_facts", p), ctx)
    r = m.record
    assert m.kind == "product"
    assert r["name"] == "Boisson pétillante Yuzu & Menthe"
    assert r["brands"] == ["marque bio", "Groupe X"] and r["brand_main"] == "Marque Bio"
    assert r["added_at"].year == 2026 and r["quality_flags"] == []


def test_open_food_facts_without_name_and_ingredients_is_skipped(ctx):
    assert MAPPERS["open_food_facts"](raw_row("open_food_facts", {"code": "1"}), ctx).kind == "skip"


def test_wikipedia(ctx):
    p = {"lang": "fr", "article": "Yuzu", "timestamp": "2026110900", "views": 274}
    r = MAPPERS["wikipedia_pageviews"](raw_row("wikipedia_pageviews", p, flavor_id="yuzu"), ctx).record
    assert r["day"] == date(2026, 11, 9) and r["geo"] == "fr.wikipedia" and r["value"] == 274.0
    assert r["flavor_id"] == "yuzu"


def test_google_trends_links_term_to_flavor(ctx):
    p = {"term": "Vanille", "geo": "France", "date": "2026-11-02", "value": 0.5, "censored": True,
         "granularity": "week", "batch_id": "abc"}
    r = MAPPERS["google_trends"](raw_row("google_trends", p), ctx).record
    assert r["flavor_id"] == "vanilla" and r["is_censored"] is True and r["batch_id"] == "abc"
