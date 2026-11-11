"""Transformation d'un document brut en enregistrement propre, source par source.

Chaque fonction reçoit une ligne de raw.raw_document et renvoie un Mapped :
- kind = 'document' (core.document), 'product' (core.product), 'interest' (core.search_interest)
- kind = 'skip' avec une raison quand le document est inutilisable (texte vide, date absente...).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from . import language
from .dedup import minhash, to_bytes
from .privacy import pseudonymize
from .sponsored import is_sponsored
from .text import clean_text, content_hash, normalize_key, text_for_analysis

MIN_TEXT_CHARS = 10
FUTURE_TOLERANCE = timedelta(days=1)


@dataclass
class Mapped:
    kind: str
    record: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


@dataclass
class Context:
    salt: str
    alias_index: dict[str, str]
    finder: object | None = None   # taxonomy.FlavorFinder
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def parse_dt(value: Any) -> datetime | None:
    """Accepte ISO 8601, '20261110T081500Z' (GDELT) et les timestamps Unix ; renvoie une date UTC."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    s = str(value).strip()
    if re.fullmatch(r"\d{8}T\d{6}Z", s):
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    if s.isdigit():
        return datetime.fromtimestamp(int(s), tz=timezone.utc)
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _document(row: dict, ctx: Context, *, doc_type: str, published: datetime | None, title: str | None,
              body: str | None, url: str | None, author_id: str | None, source_lang: str | None,
              engagement: dict[str, Any], country: str | None = None) -> Mapped:
    flags: list[str] = []
    if published is None:
        return Mapped("skip", reason="date de publication absente")
    if published > ctx.now + FUTURE_TOLERANCE:
        flags.append("future_date")
        published = row["fetched_at"]
    title_c, body_c = clean_text(title), clean_text(body)
    analysis = text_for_analysis(title_c, body_c)
    if len(analysis) < MIN_TEXT_CHARS:
        return Mapped("skip", reason="texte vide ou trop court")
    lang, lang_src = language.resolve(source_lang, analysis)
    if lang_src == "unknown":
        flags.append("lang_unknown")
    mh = minhash(analysis)
    return Mapped("document", {
        "source_id": row["source_id"], "external_id": row["external_id"], "raw_id": row["id"],
        "doc_type": doc_type, "published_at": published, "lang": lang, "lang_source": lang_src,
        "country": country, "title": title_c or None, "body": body_c or None, "text_clean": analysis,
        "url": url, "author_hash": pseudonymize(row["source_id"], author_id, ctx.salt),
        "engagement": {k: v for k, v in engagement.items() if v is not None},
        "query": row.get("query"), "flavor_hint": row.get("flavor_id"),
        "content_hash": content_hash(analysis), "minhash": to_bytes(mh) if mh else None,
        "is_sponsored": is_sponsored(title_c, body_c), "quality_flags": flags,
    })


def map_youtube(row: dict, ctx: Context) -> Mapped:
    p = row["payload"]
    sn, st = p.get("snippet", {}), p.get("statistics", {})
    return _document(
        row, ctx, doc_type="video", published=parse_dt(sn.get("publishedAt")),
        title=sn.get("title"), body=sn.get("description"),
        url=f"https://www.youtube.com/watch?v={p['id']}", author_id=sn.get("channelId"),
        source_lang=sn.get("defaultAudioLanguage") or sn.get("defaultLanguage"),
        engagement={"views": _int(st.get("viewCount")), "likes": _int(st.get("likeCount")),
                    "comments": _int(st.get("commentCount"))},
    )


def map_bluesky(row: dict, ctx: Context) -> Mapped:
    p = row["payload"]
    rec = p.get("record", {})
    langs = rec.get("langs") or []
    published = parse_dt(rec.get("createdAt")) or parse_dt(p.get("indexedAt"))
    # Pas d'URL ni de pseudo en couche propre : l'auteur est une personne (RGPD).
    return _document(
        row, ctx, doc_type="post", published=published, title=None, body=rec.get("text"),
        url=None, author_id=(p.get("author") or {}).get("did"),
        source_lang=langs[0] if len(langs) == 1 else None,
        engagement={"likes": p.get("likeCount"), "reposts": p.get("repostCount"),
                    "replies": p.get("replyCount"), "quotes": p.get("quoteCount")},
    )


def map_gdelt(row: dict, ctx: Context) -> Mapped:
    p = row["payload"]
    return _document(
        row, ctx, doc_type="article", published=parse_dt(p.get("seendate")), title=p.get("title"),
        body=None, url=p.get("url"), author_id=None, source_lang=p.get("language"),
        engagement={}, country=p.get("sourcecountry") or None,
    )


def map_rss(row: dict, ctx: Context) -> Mapped:
    p = row["payload"]
    return _document(
        row, ctx, doc_type="article", published=parse_dt(p.get("published_iso")), title=p.get("title"),
        body=p.get("summary"), url=p.get("link"), author_id=None, source_lang=p.get("feed_lang"),
        engagement={}, country=p.get("country"),
    )


def map_google_news(row: dict, ctx: Context) -> Mapped:
    p = row["payload"]
    title = p.get("title") or ""
    src = p.get("source_title")
    if src and title.endswith(f" - {src}"):
        title = title[: -len(src) - 3]  # « Titre - Le Monde » -> « Titre », pour repérer les reprises entre sources
    # Le résumé Google News ne contient que des liens : on ne garde que le titre.
    return _document(
        row, ctx, doc_type="article", published=parse_dt(p.get("published_iso")), title=title,
        body=None, url=p.get("link"), author_id=None, source_lang=p.get("feed_lang"),
        engagement={}, country=p.get("country"),
    )


def _split_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return []


def map_open_food_facts(row: dict, ctx: Context) -> Mapped:
    p = row["payload"]
    name = clean_text(p.get("product_name") or p.get("product_name_fr") or p.get("product_name_en"))
    ingredients = clean_text(p.get("ingredients_text") or p.get("ingredients_text_fr") or p.get("ingredients_text_en"))
    brands = [b.strip() for b in clean_text(p.get("brands")).split(",") if b.strip()]
    flags = []
    if not name:
        flags.append("missing_name")
    if not ingredients:
        flags.append("missing_ingredients")
    if not name and not ingredients:
        return Mapped("skip", reason="produit sans nom ni ingrédients")
    return Mapped("product", {
        "code": str(p["code"]), "raw_id": row["id"], "name": name or None,
        "generic_name": clean_text(p.get("generic_name") or p.get("generic_name_fr")) or None,
        "brands": brands, "brand_main": brands[0].title() if brands else None,
        "categories": _split_tags(p.get("categories_tags")), "ingredients_text": ingredients or None,
        "ingredients_tags": _split_tags(p.get("ingredients_tags")), "countries": _split_tags(p.get("countries_tags")),
        "lang": language.normalize_code(p.get("lang")),
        "added_at": parse_dt(_int(p.get("created_t"))), "last_modified_at": parse_dt(_int(p.get("last_modified_t"))),
        "quality_flags": flags,
    })


def map_wikipedia(row: dict, ctx: Context) -> Mapped:
    p = row["payload"]
    day = datetime.strptime(p["timestamp"][:8], "%Y%m%d").date()
    return Mapped("interest", {
        "source_id": row["source_id"], "term": p["article"], "geo": f"{p['lang']}.wikipedia", "day": day,
        "batch_id": "", "flavor_id": row.get("flavor_id"), "value": float(p["views"]),
        "granularity": "day", "is_censored": False, "raw_id": row["id"],
    })


def map_google_trends(row: dict, ctx: Context) -> Mapped:
    p = row["payload"]
    return Mapped("interest", {
        "source_id": row["source_id"], "term": p["term"], "geo": p.get("geo") or "", "day": date.fromisoformat(p["date"]),
        "batch_id": p["batch_id"], "flavor_id": ctx.alias_index.get(normalize_key(p["term"])),
        "value": float(p["value"]), "granularity": p["granularity"], "is_censored": bool(p.get("censored")),
        "raw_id": row["id"],
    })


def map_pinterest(row: dict, ctx: Context) -> Mapped:
    p = row["payload"]
    if p.get("kind") == "series":   # courbe hebdomadaire de l'API -> même table que Google Trends
        kw = p["term"]
        return Mapped("interest", {
            "source_id": row["source_id"], "term": kw, "geo": p["geo"], "day": date.fromisoformat(p["week_end"]),
            "batch_id": p["batch_id"], "flavor_id": _flavor_of(kw, ctx), "value": float(p["value"]),
            "granularity": "week", "is_censored": False, "raw_id": row["id"],
        })
    kw = p["keyword"]

    def num(k):
        v = p.get(k)
        return float(v) if v is not None else None

    return Mapped("trend", {
        "source_id": row["source_id"], "observed_on": date.fromisoformat(p["observed_on"]), "region": p["region"],
        "keyword": kw, "trend_type": p.get("trend_type") or "", "flavor_id": _flavor_of(kw, ctx),
        "rank": int(p["rank"]) if p.get("rank") is not None else None,
        "pct_growth_wow": num("growth_wow_pct"), "pct_growth_mom": num("growth_mom_pct"),
        "pct_growth_yoy": num("growth_yoy_pct"), "note": p.get("note"), "url": p.get("url"), "raw_id": row["id"],
    })


def _flavor_of(keyword: str, ctx: Context) -> str | None:
    """Arôme cité dans le mot-clé (« yuzu lemonade » -> yuzu), sinon None : candidat à ajouter à la liste."""
    exact = ctx.alias_index.get(normalize_key(keyword))
    if exact:
        return exact
    found = ctx.finder.find(keyword) if ctx.finder else []
    return found[0] if found else None


MAPPERS: dict[str, Callable[[dict, Context], Mapped]] = {
    "youtube": map_youtube,
    "bluesky": map_bluesky,
    "gdelt": map_gdelt,
    "rss": map_rss,
    "google_news": map_google_news,
    "open_food_facts": map_open_food_facts,
    "wikipedia_pageviews": map_wikipedia,
    "google_trends": map_google_trends,
    "pinterest": map_pinterest,
}
