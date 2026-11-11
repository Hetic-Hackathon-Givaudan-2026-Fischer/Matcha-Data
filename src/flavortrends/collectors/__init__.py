"""Collecteurs : une classe par source, tous écrivent dans raw.raw_document."""
from .bluesky import Bluesky
from .gdelt import Gdelt
from .google_trends import GoogleTrendsAuto, GoogleTrendsImport
from .openfoodfacts import OpenFoodFacts, OpenFoodFactsDelta, OpenFoodFactsDump
from .pinterest import PinterestManualImport, PinterestTrendsApi
from .rss import GoogleNews, RssFeeds
from .wikipedia import WikipediaPageviews
from .youtube import YouTube

__all__ = ["Bluesky", "Gdelt", "GoogleNews", "GoogleTrendsAuto", "GoogleTrendsImport", "OpenFoodFacts", "OpenFoodFactsDelta",
           "OpenFoodFactsDump", "PinterestManualImport", "PinterestTrendsApi", "RssFeeds",
           "WikipediaPageviews", "YouTube"]
