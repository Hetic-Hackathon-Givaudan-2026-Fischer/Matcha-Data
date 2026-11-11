from datetime import datetime, timezone

import pytest

from flavortrends.cleaning.mappers import Context
from flavortrends.config import Settings


@pytest.fixture
def settings():
    return Settings(database_url="postgresql://unused", contact="test@example.org",
                    pseudonymization_salt="test-salt-0123456789", youtube_api_key="FAKEKEY",
                    youtube_unit_budget=1000, bluesky_handle="tester.bsky.social", bluesky_app_password="xxxx",
                    off_categories=["en:beverages"], off_countries=["en:france"], langs=["fr", "en"])


@pytest.fixture
def ctx():
    return Context(salt="test-salt-0123456789", alias_index={"yuzu": "yuzu", "vanille": "vanilla"},
                   now=datetime(2026, 11, 10, 12, tzinfo=timezone.utc))


def raw_row(source_id, payload, **kw):
    return {"id": kw.get("id", 1), "source_id": source_id, "external_id": kw.get("external_id", "x1"),
            "query": kw.get("query"), "flavor_id": kw.get("flavor_id"), "payload": payload,
            "fetched_at": datetime(2026, 11, 10, 3, tzinfo=timezone.utc)}
