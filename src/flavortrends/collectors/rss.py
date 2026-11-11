"""Flux RSS : presse spécialisée (config/rss_feeds.csv) et Google News par arôme.

On ne conserve que le titre, le résumé et le lien des articles, jamais le texte intégral.
"""
from __future__ import annotations

import calendar
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import feedparser

from ..config import ROOT
from ..taxonomy import Flavor
from .base import Collector, RawItem, sha1

log = logging.getLogger(__name__)

FEEDS_FILE = ROOT / "config" / "rss_feeds.csv"
GNEWS = "https://news.google.com/rss/search"
GNEWS_LOCALE = {"fr": ("fr", "FR", "FR:fr"), "en": ("en-US", "US", "US:en")}
GNEWS_CONTEXT = {
    "fr": "(boisson OR saveur OR recette OR dessert OR arôme)",
    "en": "(drink OR flavor OR recipe OR dessert OR snack)",
}


def _iso(struct) -> str | None:
    if not struct:
        return None
    return datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc).isoformat()


def entry_payload(entry: Any, feed_title: str | None, feed_lang: str | None) -> dict[str, Any]:
    src = entry.get("source") or {}
    return {
        "id": entry.get("id"),
        "title": entry.get("title"),
        "link": entry.get("link"),
        "summary": entry.get("summary"),
        "published": entry.get("published") or entry.get("updated"),
        "published_iso": _iso(entry.get("published_parsed") or entry.get("updated_parsed")),
        "author": entry.get("author"),
        "tags": [t.get("term") for t in entry.get("tags", []) if t.get("term")],
        "source_title": src.get("title") if hasattr(src, "get") else None,
        "feed_title": feed_title,
        "feed_lang": feed_lang,
    }


class RssFeeds(Collector):
    source_id = "rss"
    min_interval = 1.0

    def fetch(self, feeds_file: Path = FEEDS_FILE) -> Iterator[RawItem]:
        with open(feeds_file, encoding="utf-8-sig", newline="") as fh:
            feeds = [r for r in csv.DictReader(fh) if r.get("url", "").strip() and not r["name"].startswith("#")]
        for feed in feeds:
            try:
                resp = self.http.get(feed["url"].strip())
            except Exception as exc:
                log.error("[rss] %s : %s", feed["name"], exc)
                self.errors += 1
                continue
            parsed = feedparser.parse(resp.content)
            if not parsed.entries:
                log.warning("[rss] %s : aucun article lisible (%s)", feed["name"], parsed.get("bozo_exception"))
                self.errors += 1
                continue
            title = parsed.feed.get("title") or feed["name"]
            for e in parsed.entries:
                ext = e.get("id") or e.get("link")
                if not ext:
                    continue
                payload = entry_payload(e, title, feed.get("lang") or parsed.feed.get("language"))
                payload["country"] = feed.get("country") or None
                yield RawItem(external_id=sha1(ext), payload=payload, query=feed["name"])


class GoogleNews(Collector):
    source_id = "google_news"
    min_interval = 2.0

    def fetch(self, flavors: list[Flavor], langs: list[str], days: int = 7) -> Iterator[RawItem]:
        for lang in langs:
            if lang not in GNEWS_LOCALE:
                continue
            hl, gl, ceid = GNEWS_LOCALE[lang]
            for f in flavors:
                q = f'"{f.term(lang)}" {GNEWS_CONTEXT[lang]} when:{days}d'
                try:
                    resp = self.http.get(GNEWS, params={"q": q, "hl": hl, "gl": gl, "ceid": ceid})
                except Exception as exc:
                    log.error("[google_news] %s : %s", q, exc)
                    self.errors += 1
                    continue
                parsed = feedparser.parse(resp.content)
                for e in parsed.entries:
                    ext = e.get("id") or e.get("link")
                    if not ext:
                        continue
                    payload = entry_payload(e, None, lang)
                    payload["country"] = gl
                    yield RawItem(external_id=sha1(ext), payload=payload, query=q, flavor_id=f.flavor_id)
